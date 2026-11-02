"""
Qdrant Hybrid Retriever (Dense `BAAI/bge-small-en-v1.5` + Sparse `BM25` with RRF)
and Strict Metadata Filtering for BimaSense AI (Milestone 2).

Supports:
1. Metadata-filtered search on `insurer_policies` (`plan_name`, `insurer_name`,
   `section_category`, `user_id` with automatic inclusion of `'global'` policies).
2. Topic-filtered search on `irdai_regulations` (`topic`, `circular_ref`).
3. Item/Status search on `non_payable_consumables` (`item_number`, `payable_status`).
4. Parallel multi-plan retrieval for side-by-side plan comparisons.
5. Medical & Indian health insurance domain synonym expansion (e.g., "sugar" -> "diabetes",
   "BP" -> "hypertension", "cashless delay" -> "3 hours discharge authorization").
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from pydantic import Field

from app.config import LOCAL_INDEX_PATH, settings
from app.ingestion.indexer import HybridEmbedder, _compute_sparse_bm25_tf, _tokenize
from app.schemas.api_models import BimaSenseBaseModel, CitationItem


# Domain-specific query expansion map for Indian health insurance colloquialisms
INSURANCE_SYNONYM_MAP: dict[str, list[str]] = {
    "sugar": ["diabetes", "mellitus", "pre-existing", "ped", "excl01", "36 months"],
    "diabetes": ["diabetes", "mellitus", "pre-existing", "ped", "excl01", "36 months"],
    "bp": ["hypertension", "pre-existing", "ped", "excl01", "36 months"],
    "blood pressure": ["hypertension", "pre-existing", "ped", "excl01", "36 months"],
    "hypertension": ["hypertension", "pre-existing", "ped", "excl01", "36 months"],
    "ped": ["pre-existing", "disease", "excl01", "36 months", "waiting", "moratorium"],
    "moratorium": ["moratorium", "36 months", "non-disclosure", "contestable", "fraud"],
    "non-disclosure": ["moratorium", "36 months", "non-disclosure", "misrepresentation"],
    "pregnancy": ["maternity", "childbirth", "delivery", "caesarean", "newborn", "24 months"],
    "baby": ["maternity", "newborn", "baby food", "childbirth"],
    "room cap": ["room rent", "single private", "proportionate deduction", "at actuals"],
    "room limit": ["room rent", "single private", "proportionate deduction", "at actuals"],
    "deduction": ["proportionate deduction", "room rent", "co-payment", "non-payable"],
    "senior": ["61 years", "co-payment", "10%", "mandatory", "entry age"],
    "elderly": ["61 years", "co-payment", "10%", "mandatory", "entry age"],
    "parents": ["61 years", "co-payment", "10%", "mandatory", "entry age"],
    "restore": ["restoration", "reassure forever", "restore benefit", "100%"],
    "refill": ["restoration", "reassure forever", "restore benefit", "100%"],
    "bonus": ["no-claim bonus", "cumulative bonus", "booster+", "plus benefit", "secure benefit"],
    "consumables": ["protect benefit", "safeguard+", "extra protect", "68", "annexure-i", "non-payable"],
    "gloves": ["surgical gloves", "item 56", "non_payable_unless_rider", "protect benefit"],
    "nebulizer": ["nebulization kit", "item 42", "non_payable_unless_rider"],
    "nebulization": ["nebulization kit", "item 42", "non_payable_unless_rider"],
    "gown": ["patient gown", "item 24", "subsumed_in_room_charges"],
    "laundry": ["laundry charges", "item 38", "subsumed_in_room_charges"],
    "admission kit": ["admission kit", "file charges", "item 68", "subsumed_in_room_charges"],
    "discharge delay": ["3 hours", "discharge", "shareholders", "cashless", "1 hour"],
    "tpa": ["claims review committee", "crc", "repudiated", "1 hour", "3 hours", "cashless"],
    "ombudsman": ["ombudsman", "5,000", "30 days", "penal interest", "award"],
}


def expand_insurance_query(query: str) -> str:
    """
    Expands colloquial insurance/medical terms into canonical policy & IRDAI terminology
    without losing the user's original query phrasing.
    """
    q_lower = query.lower()
    expansions: list[str] = []
    for trigger, terms in INSURANCE_SYNONYM_MAP.items():
        if re.search(rf"\b{re.escape(trigger)}\b", q_lower):
            for term in terms:
                if term not in q_lower and term not in expansions:
                    expansions.append(term)
    if not expansions:
        return query
    return f"{query} ({' '.join(expansions)})"


class MetadataFilter(BimaSenseBaseModel):
    """Structured metadata filter criteria across Qdrant collections."""

    insurer_name: str | None = Field(default=None, description="Exact or partial insurer name")
    plan_name: str | None = Field(default=None, description="Exact or partial plan name")
    section_category: str | None = Field(default=None, description="Clause category filter")
    user_id: str = Field(default="global", description="Includes 'global' + user's uploaded policies")
    topic: str | None = Field(default=None, description="IRDAI circular topic filter")
    item_number: int | None = Field(default=None, description="Annexure-I consumable item number")
    payable_status: str | None = Field(default=None, description="Consumable payable status")


class RetrievedChunk(BimaSenseBaseModel):
    """Unified representation of a retrieved chunk with hybrid and reranker scores."""

    chunk_id: str
    collection: str
    text: str
    page_number: int = 1
    source_title: str = ""
    source_file: str = ""
    section_heading: str = ""
    section_category: str = ""
    dense_score: float = 0.0
    sparse_score: float = 0.0
    rrf_score: float = 0.0
    rerank_score: float = 0.0
    payload: dict[str, Any] = Field(default_factory=dict)

    def to_citation(self) -> CitationItem:
        """Converts this retrieved chunk into a FastAPI/Android `CitationItem`."""
        lines = [
            ln.strip()
            for ln in self.text.splitlines()
            if ln.strip() and not (ln.strip().startswith("[") and ln.strip().endswith("]"))
        ]
        snippet = " ".join(lines)[:280]
        return CitationItem(
            source_title=self.source_title,
            page_number=self.page_number,
            section_heading=self.section_heading,
            section_category=self.section_category,
            snippet=snippet,
            relevance_score=round(self.rerank_score or self.rrf_score, 4),
        )


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a)) or 1.0
    norm_b = math.sqrt(sum(b * b for b in vec_b)) or 1.0
    return max(0.0, dot / (norm_a * norm_b))


class BimaSenseHybridRetriever:
    """
    Executes Hybrid Search (Dense `BAAI/bge-small-en-v1.5` + Sparse `BM25`)
    with Reciprocal Rank Fusion (RRF) and strict metadata filtering.
    """

    def __init__(self, index_file_path: Path = LOCAL_INDEX_PATH) -> None:
        self.index_file_path = index_file_path
        self.embedder = HybridEmbedder()
        self._qdrant_client: Any = None
        self._local_collections: dict[str, list[dict[str, Any]]] = {}
        self._idf_cache: dict[str, dict[str, float]] = {}
        self._load_stores()

    def _load_stores(self) -> None:
        """Loads the local hybrid index snapshot and connects to Qdrant if running."""
        if self.index_file_path.exists():
            data = json.loads(self.index_file_path.read_text(encoding="utf-8"))
            self._local_collections = data.get("collections", {})
            self._build_idf_tables()

        try:
            from qdrant_client import QdrantClient  # type: ignore

            client = QdrantClient(
                url=settings.qdrant_url,
                api_key=settings.qdrant_api_key or None,
                timeout=2.0,
            )
            client.get_collections()
            self._qdrant_client = client
        except Exception:
            self._qdrant_client = None

    def _build_idf_tables(self) -> None:
        """Precomputes BM25 Inverse Document Frequency (IDF) weights per collection."""
        for col_name, records in self._local_collections.items():
            n_docs = max(1, len(records))
            df_counts: dict[str, int] = {}
            for rec in records:
                terms = set(_tokenize(rec["payload"].get("text", "")))
                for t in terms:
                    df_counts[t] = df_counts.get(t, 0) + 1
            self._idf_cache[col_name] = {
                t: math.log(1.0 + (n_docs - df + 0.5) / (df + 0.5))
                for t, df in df_counts.items()
            }

    def _matches_filter(self, payload: dict[str, Any], filters: MetadataFilter | None) -> bool:
        """Evaluates metadata filter constraints against a chunk payload."""
        if filters is None:
            return True

        # User isolation filter: allow 'global' pre-loaded documents or user's own uploads
        if "user_id" in payload:
            allowed_users = {"global", filters.user_id}
            if payload.get("user_id") not in allowed_users:
                return False

        if filters.insurer_name:
            ins = payload.get("insurer_name", "").lower()
            if filters.insurer_name.lower() not in ins and ins not in filters.insurer_name.lower():
                return False

        if filters.plan_name:
            plan = payload.get("plan_name", "").lower()
            target = filters.plan_name.lower()
            if target not in plan and plan not in target:
                return False

        if filters.section_category:
            if payload.get("section_category") != filters.section_category:
                return False

        if filters.topic:
            if payload.get("topic") != filters.topic:
                return False

        if filters.item_number is not None:
            if payload.get("item_number") != filters.item_number:
                return False

        if filters.payable_status:
            if payload.get("payable_status") != filters.payable_status:
                return False

        return True

    def _format_source_title(self, collection_name: str, payload: dict[str, Any]) -> str:
        if collection_name == settings.collection_insurer_policies:
            return f"{payload.get('insurer_name', '')} {payload.get('plan_name', '')}".strip()
        if collection_name == settings.collection_irdai_regulations:
            return f"IRDAI Circular ({payload.get('circular_ref', '2024')})"
        if collection_name == settings.collection_non_payable_consumables:
            return f"IRDAI Annexure-I (Item #{payload.get('item_number', '')}: {payload.get('item_name', '')})"
        return payload.get("source_file", collection_name)

    def retrieve(
        self,
        query: str,
        collection_name: str = settings.collection_insurer_policies,
        filters: MetadataFilter | None = None,
        top_k: int = settings.retrieval_top_k,
        use_query_expansion: bool = True,
    ) -> list[RetrievedChunk]:
        """
        Executes hybrid Dense + Sparse BM25 search with Reciprocal Rank Fusion (RRF)
        on the target collection and returns the top-K candidates.
        """
        effective_query = expand_insurance_query(query) if use_query_expansion else query
        q_dense = self.embedder.embed_dense([effective_query])[0]
        q_tf = _compute_sparse_bm25_tf(effective_query)

        records = self._local_collections.get(collection_name, [])
        filtered_records = [r for r in records if self._matches_filter(r["payload"], filters)]
        if not filtered_records:
            return []

        idf_map = self._idf_cache.get(collection_name, {})

        scored_items: list[dict[str, Any]] = []
        for rec in filtered_records:
            payload = rec["payload"]
            d_score = _cosine_similarity(q_dense, rec.get("dense_vector", []))

            # Compute BM25 lexical score over sparse vector terms + exact number/clause matches
            doc_terms = rec.get("sparse_vector", {}).get("terms")
            if not doc_terms:
                doc_terms = _compute_sparse_bm25_tf(payload.get("text", ""))

            s_score = 0.0
            for term, q_weight in q_tf.items():
                if term in doc_terms:
                    idf = idf_map.get(term, 1.2)
                    s_score += q_weight * doc_terms[term] * idf

            scored_items.append(
                {
                    "record": rec,
                    "dense_score": d_score,
                    "sparse_score": s_score,
                }
            )

        # Rank independently by Dense and Sparse scores, then fuse via Reciprocal Rank Fusion (RRF)
        dense_ranked = sorted(scored_items, key=lambda x: x["dense_score"], reverse=True)
        sparse_ranked = sorted(scored_items, key=lambda x: x["sparse_score"], reverse=True)

        dense_rank_map = {item["record"]["chunk_id"]: rank for rank, item in enumerate(dense_ranked, start=1)}
        sparse_rank_map = {item["record"]["chunk_id"]: rank for rank, item in enumerate(sparse_ranked, start=1)}

        rrf_k = 15.0  # Tuned RRF constant for compact policy collections
        results: list[RetrievedChunk] = []

        for item in scored_items:
            rec = item["record"]
            cid = rec["chunk_id"]
            payload = rec["payload"]
            d_rank = dense_rank_map[cid]
            s_rank = sparse_rank_map[cid]

            # Weight sparse BM25 slightly higher when exact medical/clause terms match
            sparse_weight = 1.25 if item["sparse_score"] > 0 else 0.25
            rrf_score = (1.0 / (rrf_k + d_rank)) + (sparse_weight / (rrf_k + s_rank))

            section_cat = (
                payload.get("section_category")
                or payload.get("topic")
                or payload.get("payable_status")
                or ""
            )
            section_head = (
                payload.get("section_heading")
                or payload.get("item_name")
                or f"Page {payload.get('page_number', 1)}"
            )

            results.append(
                RetrievedChunk(
                    chunk_id=cid,
                    collection=collection_name,
                    text=payload.get("text", ""),
                    page_number=int(payload.get("page_number", 1)),
                    source_title=self._format_source_title(collection_name, payload),
                    source_file=payload.get("source_file", ""),
                    section_heading=section_head,
                    section_category=section_cat,
                    dense_score=round(item["dense_score"], 4),
                    sparse_score=round(item["sparse_score"], 4),
                    rrf_score=round(rrf_score, 4),
                    payload=payload,
                )
            )

        results.sort(key=lambda x: (x.rrf_score, x.sparse_score, x.dense_score), reverse=True)
        return results[:top_k]

    def retrieve_across_all_collections(
        self,
        query: str,
        filters: MetadataFilter | None = None,
        top_k: int = settings.retrieval_top_k,
    ) -> list[RetrievedChunk]:
        """
        Queries `insurer_policies`, `irdai_regulations`, and `non_payable_consumables`
        and returns a unified pool of candidates for cross-encoder reranking.
        """
        candidates: list[RetrievedChunk] = []
        candidates.extend(
            self.retrieve(
                query=query,
                collection_name=settings.collection_insurer_policies,
                filters=filters,
                top_k=top_k,
            )
        )
        # Include regulatory & consumable collections when not restricted to a single policy section
        if filters is None or not filters.section_category:
            irdai_filter = MetadataFilter(topic=filters.topic) if filters and filters.topic else None
            candidates.extend(
                self.retrieve(
                    query=query,
                    collection_name=settings.collection_irdai_regulations,
                    filters=irdai_filter,
                    top_k=max(5, top_k // 2),
                )
            )
            consumable_filter = (
                MetadataFilter(item_number=filters.item_number, payable_status=filters.payable_status)
                if filters and (filters.item_number is not None or filters.payable_status)
                else None
            )
            candidates.extend(
                self.retrieve(
                    query=query,
                    collection_name=settings.collection_non_payable_consumables,
                    filters=consumable_filter,
                    top_k=max(5, top_k // 2),
                )
            )
        return candidates

    def retrieve_for_plan_comparison(
        self,
        query: str,
        plan_a: str,
        plan_b: str,
        top_k_per_plan: int = 5,
    ) -> dict[str, list[RetrievedChunk]]:
        """
        Executes parallel metadata-filtered retrievals for Plan A and Plan B
        to power Pillar 2 (Multi-Insurer Side-by-Side Comparator).
        """
        plan_a_chunks = self.retrieve(
            query=query,
            collection_name=settings.collection_insurer_policies,
            filters=MetadataFilter(plan_name=plan_a),
            top_k=top_k_per_plan,
        )
        plan_b_chunks = self.retrieve(
            query=query,
            collection_name=settings.collection_insurer_policies,
            filters=MetadataFilter(plan_name=plan_b),
            top_k=top_k_per_plan,
        )
        return {
            plan_a: plan_a_chunks,
            plan_b: plan_b_chunks,
        }
