"""
Qdrant Hybrid Vector Indexer (Dense `BAAI/bge-small-en-v1.5` + Sparse `BM25`)
for BimaSense AI (Milestone 1).

Manages the three logical collections defined in Master Plan Section 4:
1. `insurer_policies`
2. `irdai_regulations`
3. `non_payable_consumables`

Supports:
- Qdrant Server (Docker / Cloud) with Named Dense + Sparse Vectors & Payload Indexes.
- Qdrant In-Memory mode (`QdrantClient(":memory:")`).
- Built-in Deterministic Hybrid Fallback Store (`LocalHybridStore`) persisted to disk
  (`data/local_hybrid_index.json`) so incremental user uploads preserve all pre-loaded collections.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from pathlib import Path
from typing import Any

from app.config import LOCAL_INDEX_PATH, settings
from app.schemas.api_models import (
    InsurerPolicyPayload,
    IrdaiRegulationPayload,
    NonPayableConsumablePayload,
)


def _tokenize(text: str) -> list[str]:
    """Lightweight tokenizer for BM25 sparse vectors and keyword matching."""
    return re.findall(r"[a-z0-9_]+", text.lower())


def _compute_sparse_bm25_tf(text: str) -> dict[str, float]:
    """Computes normalized term-frequency weights for sparse lexical indexing."""
    tokens = _tokenize(text)
    if not tokens:
        return {}
    counts = Counter(tokens)
    max_tf = max(counts.values())
    return {term: round(0.5 + 0.5 * (freq / max_tf), 4) for term, freq in counts.items()}


def _deterministic_dense_embedding(text: str, dim: int = 384) -> list[float]:
    """
    Lightweight, deterministic char/word n-gram feature hashing embedding (384-d L2-normalized).
    Used only as an offline fallback when `fastembed` (`BAAI/bge-small-en-v1.5`) is not installed.
    """
    vec = [0.0] * dim
    tokens = _tokenize(text)
    for i, tok in enumerate(tokens):
        features = [tok]
        if i + 1 < len(tokens):
            features.append(f"{tok}_{tokens[i + 1]}")
        for feat in features:
            h = int(hashlib.md5(feat.encode("utf-8")).hexdigest(), 16)
            idx = h % dim
            sign = 1.0 if ((h >> 16) & 1) == 0 else -1.0
            vec[idx] += sign

    norm = math.sqrt(sum(v * v for a in vec for v in [a])) or 1.0
    return [round(v / norm, 6) for v in vec]


class HybridEmbedder:
    """
    Generates Dense (`BAAI/bge-small-en-v1.5`, 384-d) and Sparse (`BM25`) embeddings.
    Uses `fastembed` when installed and automatically falls back to deterministic
    384-d feature hashing + BM25 term weights in restricted environments.
    """

    def __init__(self) -> None:
        self.dense_model_name = settings.dense_embedding_model
        self.sparse_model_name = settings.sparse_embedding_model
        self._dense_model: Any = None
        self._sparse_model: Any = None
        self.backend_mode = "deterministic_fallback"
        self._init_models()

    def _init_models(self) -> None:
        try:
            from fastembed import SparseTextEmbedding, TextEmbedding  # type: ignore

            self._dense_model = TextEmbedding(model_name=self.dense_model_name)
            self._sparse_model = SparseTextEmbedding(model_name=self.sparse_model_name)
            self.backend_mode = "fastembed"
        except Exception:
            self.backend_mode = "deterministic_fallback"

    def embed_dense(self, texts: list[str]) -> list[list[float]]:
        if self._dense_model is not None:
            return [vec.tolist() for vec in self._dense_model.embed(texts)]
        return [_deterministic_dense_embedding(t, settings.dense_embedding_dim) for t in texts]

    def embed_sparse(self, texts: list[str]) -> list[dict[str, Any]]:
        if self._sparse_model is not None:
            results: list[dict[str, Any]] = []
            for sp in self._sparse_model.embed(texts):
                results.append(
                    {
                        "indices": sp.indices.tolist(),
                        "values": sp.values.tolist(),
                    }
                )
            return results

        fallback_results: list[dict[str, Any]] = []
        for t in texts:
            tf_map = _compute_sparse_bm25_tf(t)
            indices = [int(hashlib.md5(term.encode("utf-8")).hexdigest()[:8], 16) % 100_003 for term in tf_map]
            values = list(tf_map.values())
            fallback_results.append({"indices": indices, "values": values, "terms": tf_map})
        return fallback_results


class BimaSenseHybridIndexer:
    """
    Indexes parsed & chunked insurance documents into Qdrant (with Dense + Sparse BM25 vectors)
    and persists a synchronized local hybrid index snapshot (`data/local_hybrid_index.json`).
    """

    def __init__(self, index_file_path: Path = LOCAL_INDEX_PATH, reset_existing: bool = False) -> None:
        self.embedder = HybridEmbedder()
        self.index_file_path = index_file_path
        self._qdrant_client: Any = None
        self.storage_backend = "local_hybrid_json"
        self._collections_store: dict[str, list[dict[str, Any]]] = {
            settings.collection_insurer_policies: [],
            settings.collection_irdai_regulations: [],
            settings.collection_non_payable_consumables: [],
        }
        if not reset_existing:
            self._load_existing_snapshot()
        self._init_qdrant()

    def _load_existing_snapshot(self) -> None:
        """Loads previously indexed collections from disk so incremental user uploads do not overwrite global data."""
        if not self.index_file_path.exists():
            return
        try:
            data = json.loads(self.index_file_path.read_text(encoding="utf-8"))
            existing_cols = data.get("collections", {})
            for col_name in self._collections_store:
                if col_name in existing_cols and isinstance(existing_cols[col_name], list):
                    self._collections_store[col_name] = existing_cols[col_name]
        except Exception:
            pass

    def _init_qdrant(self) -> None:
        """Connects to Qdrant Docker/Cloud or Qdrant in-memory if `qdrant-client` is installed."""
        try:
            from qdrant_client import QdrantClient  # type: ignore

            try:
                client = QdrantClient(
                    url=settings.qdrant_url,
                    api_key=settings.qdrant_api_key or None,
                    timeout=3.0,
                )
                client.get_collections()
                self._qdrant_client = client
                self.storage_backend = f"qdrant_server ({settings.qdrant_url})"
            except Exception:
                if settings.qdrant_use_in_memory_fallback:
                    self._qdrant_client = QdrantClient(":memory:")
                    self.storage_backend = "qdrant_in_memory"
        except ImportError:
            self._qdrant_client = None
            self.storage_backend = "local_hybrid_json"

        if self._qdrant_client is not None:
            self._ensure_qdrant_collections()

    def _ensure_qdrant_collections(self) -> None:
        """Creates the 3 Qdrant collections with Dense (Cosine, 384-d) and Sparse (BM25) vector configs."""
        from qdrant_client.http import models as qmodels  # type: ignore

        collections = [
            settings.collection_insurer_policies,
            settings.collection_irdai_regulations,
            settings.collection_non_payable_consumables,
        ]
        existing = {c.name for c in self._qdrant_client.get_collections().collections}

        for col_name in collections:
            if col_name not in existing:
                self._qdrant_client.create_collection(
                    collection_name=col_name,
                    vectors_config={
                        "dense": qmodels.VectorParams(
                            size=settings.dense_embedding_dim,
                            distance=qmodels.Distance.COSINE,
                        )
                    },
                    sparse_vectors_config={
                        "sparse-bm25": qmodels.SparseVectorParams(
                            index=qmodels.SparseIndexParams(on_disk=False)
                        )
                    },
                )

    def _upsert_records(self, collection_name: str, payloads: list[dict[str, Any]]) -> int:
        if not payloads:
            return 0

        texts = [p["text"] for p in payloads]
        dense_vecs = self.embedder.embed_dense(texts)
        sparse_vecs = self.embedder.embed_sparse(texts)

        # 1. Upsert into Qdrant if available
        if self._qdrant_client is not None:
            from qdrant_client.http import models as qmodels  # type: ignore

            points = []
            for payload, d_vec, s_vec in zip(payloads, dense_vecs, sparse_vecs):
                points.append(
                    qmodels.PointStruct(
                        id=payload["chunk_id"],
                        vector={
                            "dense": d_vec,
                            "sparse-bm25": qmodels.SparseVector(
                                indices=s_vec["indices"],
                                values=s_vec["values"],
                            ),
                        },
                        payload=payload,
                    )
                )
            self._qdrant_client.upsert(collection_name=collection_name, points=points)

        # 2. Update local hybrid store (deduplicated by chunk_id)
        existing_by_id = {item["chunk_id"]: item for item in self._collections_store[collection_name]}
        for payload, d_vec, s_vec in zip(payloads, dense_vecs, sparse_vecs):
            existing_by_id[payload["chunk_id"]] = {
                "chunk_id": payload["chunk_id"],
                "payload": payload,
                "dense_vector": d_vec,
                "sparse_vector": s_vec,
            }
        self._collections_store[collection_name] = list(existing_by_id.values())
        self._persist_local_snapshot()
        return len(payloads)

    def index_insurer_policies(self, chunks: list[InsurerPolicyPayload]) -> int:
        """Indexes policy wording chunks into `insurer_policies`."""
        return self._upsert_records(
            settings.collection_insurer_policies,
            [c.model_dump() for c in chunks],
        )

    def index_irdai_regulations(self, chunks: list[IrdaiRegulationPayload]) -> int:
        """Indexes IRDAI Master Circular chunks into `irdai_regulations`."""
        return self._upsert_records(
            settings.collection_irdai_regulations,
            [c.model_dump() for c in chunks],
        )

    def index_non_payable_consumables(self, chunks: list[NonPayableConsumablePayload]) -> int:
        """Indexes IRDAI Annexure-I 68 Non-Payable items into `non_payable_consumables`."""
        return self._upsert_records(
            settings.collection_non_payable_consumables,
            [c.model_dump() for c in chunks],
        )

    def _persist_local_snapshot(self) -> None:
        self.index_file_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot = {
            "storage_backend": self.storage_backend,
            "embedding_backend": self.embedder.backend_mode,
            "dense_model": self.embedder.dense_model_name,
            "sparse_model": self.embedder.sparse_model_name,
            "collections": {
                name: [
                    {
                        "chunk_id": rec["chunk_id"],
                        "payload": rec["payload"],
                        "dense_vector": rec["dense_vector"],
                        "sparse_vector": rec["sparse_vector"],
                    }
                    for rec in records
                ]
                for name, records in self._collections_store.items()
            },
        }
        self.index_file_path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")

    def get_collection_stats(self) -> dict[str, int]:
        return {name: len(records) for name, records in self._collections_store.items()}
