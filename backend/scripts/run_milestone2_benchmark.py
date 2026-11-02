"""
Milestone 2 Verification & 15-Query Tricky Insurance Retrieval Benchmark.

Tests:
1. Metadata-filtered Hybrid Search (Dense `BAAI/bge-small-en-v1.5` + Sparse `BM25` RRF).
2. Cross-Encoder Reranking (`FlashRank` `ms-marco-MiniLM-L-12-v2`).
3. 15 tricky Indian medical insurance queries spanning colloquial medical terms,
   proportionate deduction exemptions, senior co-pay, IRDAI moratorium rules,
   cashless discharge turnaround penalties, and Annexure-I non-payable consumables.
4. Parallel Multi-Insurer Comparison retrieval (`retrieve_for_plan_comparison`).
5. Corrective RAG guardrail confidence check (`score < 0.35`) on an out-of-scope query.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import settings
from app.retrieval.qdrant_client import BimaSenseHybridRetriever, MetadataFilter
from app.retrieval.reranker import FlashRankReranker
from scripts.run_milestone1_pipeline import run_milestone1_ingestion


TRICKY_15_QUERIES: list[dict[str, Any]] = [
    {
        "id": "Q01",
        "query": "What is the waiting period for sugar and BP in HDFC ERGO Optima Secure?",
        "filters": {"plan_name": "Optima Secure"},
        "expected_source_file": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
        "expected_page": 2,
        "expected_keywords": ["36 months", "diabetes", "hypertension"],
    },
    {
        "id": "Q02",
        "query": "If I pick a Deluxe room in HDFC Optima Secure for a 10L policy, will proportionate deduction apply?",
        "filters": {"plan_name": "Optima Secure", "section_category": "room_rent"},
        "expected_source_file": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
        "expected_page": 1,
        "expected_keywords": ["no room rent capping", "proportionate deduction"],
    },
    {
        "id": "Q03",
        "query": "Does HDFC ERGO Optima Secure pay for surgical gloves and nebulization kits without buying a separate rider?",
        "filters": {"plan_name": "Optima Secure"},
        "expected_source_file": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
        "expected_page": 1,
        "expected_keywords": ["protect benefit", "68"],
    },
    {
        "id": "Q04",
        "query": "Under Star Health Comprehensive, if I upgrade to a Suite room, are pharmacy medicines and stents also subject to proportionate deduction?",
        "filters": {"plan_name": "Star Comprehensive", "section_category": "room_rent"},
        "expected_source_file": "Star_Health_Comprehensive_Policy_Wording.pdf",
        "expected_page": 1,
        "expected_keywords": ["not be applied", "pharmacy/medicines", "implants/stents"],
    },
    {
        "id": "Q05",
        "query": "How can I reduce the 36-month pre-existing disease waiting period in Star Comprehensive?",
        "filters": {"plan_name": "Star Comprehensive", "section_category": "waiting_periods"},
        "expected_source_file": "Star_Health_Comprehensive_Policy_Wording.pdf",
        "expected_page": 2,
        "expected_keywords": ["buy-back ped", "12 months"],
    },
    {
        "id": "Q06",
        "query": "What is the normal delivery and C-section maternity sub-limit in Star Health Comprehensive?",
        "filters": {"plan_name": "Star Comprehensive", "section_category": "waiting_periods"},
        "expected_source_file": "Star_Health_Comprehensive_Policy_Wording.pdf",
        "expected_page": 2,
        "expected_keywords": ["24 months", "30,000", "1,00,000"],
    },
    {
        "id": "Q07",
        "query": "My father joined Star Health Comprehensive at age 63. Is there any mandatory senior citizen co-payment on claims?",
        "filters": {"plan_name": "Star Comprehensive"},
        "expected_source_file": "Star_Health_Comprehensive_Policy_Wording.pdf",
        "expected_page": 3,
        "expected_keywords": ["10% co-payment", "61 years"],
    },
    {
        "id": "Q08",
        "query": "Does Niva Bupa ReAssure 2.0 restore sum insured for the SAME illness multiple times in a year?",
        "filters": {"plan_name": "ReAssure 2.0"},
        "expected_source_file": "Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
        "expected_page": 1,
        "expected_keywords": ["unlimited restoration", "same illnesses"],
    },
    {
        "id": "Q09",
        "query": "How does Safeguard+ protect my Booster+ bonus in Niva Bupa ReAssure 2.0?",
        "filters": {"plan_name": "ReAssure 2.0"},
        "expected_source_file": "Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
        "expected_page": 2,
        "expected_keywords": ["safeguard+", "1,00,000"],
    },
    {
        "id": "Q10",
        "query": "Can an insurer reject my claim for non-disclosure of a pre-existing condition after 4 years of continuous policy renewal?",
        "filters": None,
        "expected_source_file": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
        "expected_page": 1,
        "expected_keywords": ["36", "moratorium", "non-disclosure"],
    },
    {
        "id": "Q11",
        "query": "The insurer delayed cashless discharge approval for 7 hours and the hospital charged extra bed rent. Who must pay under IRDAI rules?",
        "filters": None,
        "expected_source_file": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
        "expected_page": 2,
        "expected_keywords": ["3 hours", "shareholders' fund"],
    },
    {
        "id": "Q12",
        "query": "Can a TPA directly reject my health insurance claim without insurer committee approval?",
        "filters": None,
        "expected_source_file": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
        "expected_page": 3,
        "expected_keywords": ["claims review committee", "tpa"],
    },
    {
        "id": "Q13",
        "query": "What daily penalty must an insurer pay if it does not comply with an Insurance Ombudsman award within 30 days?",
        "filters": None,
        "expected_source_file": "IRDAI_Master_Circular_Health_Insurance_2024.pdf",
        "expected_page": 3,
        "expected_keywords": ["5,000 per day", "30 days"],
    },
    {
        "id": "Q14",
        "query": "Can a hospital bill me separately for laundry charges and patient gown during hospitalization?",
        "filters": None,
        "expected_source_file": "IRDAI_Annexure_I_68_Non_Payable_Consumables.pdf",
        "expected_page": 1,
        "expected_keywords": ["subsumed_in_room_charges"],
    },
    {
        "id": "Q15",
        "query": "Are hospital admission kit and file charges (Item 68) payable by the patient?",
        "filters": None,
        "expected_source_file": "IRDAI_Annexure_I_68_Non_Payable_Consumables.pdf",
        "expected_page": 2,
        "expected_keywords": ["68", "subsumed_in_room_charges"],
    },
]


def run_milestone2_evaluation() -> dict[str, Any]:
    # Refresh index so latest chunker improvements are active
    run_milestone1_ingestion()

    retriever = BimaSenseHybridRetriever()
    reranker = FlashRankReranker()

    top1_hits = 0
    top3_hits = 0
    query_logs: list[dict[str, Any]] = []

    for item in TRICKY_15_QUERIES:
        m_filter = MetadataFilter(**item["filters"]) if item["filters"] else None
        candidates = retriever.retrieve_across_all_collections(
            query=item["query"],
            filters=m_filter,
            top_k=settings.retrieval_top_k,
        )
        reranked = reranker.rerank(
            query=item["query"],
            candidates=candidates,
            top_k=settings.rerank_top_k,
        )

        # Evaluate Top-1 and Top-3 accuracy against expected source PDF, page number, and keywords
        def is_match(chunk: Any) -> bool:
            if chunk.source_file != item["expected_source_file"]:
                return False
            if chunk.page_number != item["expected_page"]:
                return False
            normalized_text = re.sub(r"\s+", " ", chunk.text.lower())
            return all(kw.lower() in normalized_text for kw in item["expected_keywords"])

        hit_top1 = bool(reranked and is_match(reranked[0]))
        hit_top3 = any(is_match(c) for c in reranked[:3])

        if hit_top1:
            top1_hits += 1
        if hit_top3:
            top3_hits += 1

        top_chunk = reranked[0] if reranked else None
        query_logs.append(
            {
                "id": item["id"],
                "query": item["query"],
                "top1_match": hit_top1,
                "top3_match": hit_top3,
                "top1_source": top_chunk.source_title if top_chunk else None,
                "top1_page": top_chunk.page_number if top_chunk else None,
                "top1_section": top_chunk.section_heading if top_chunk else None,
                "top1_rerank_score": top_chunk.rerank_score if top_chunk else 0.0,
                "top1_rrf_score": top_chunk.rrf_score if top_chunk else 0.0,
                "citation_preview": top_chunk.to_citation().model_dump() if top_chunk else None,
            }
        )

    # Test Multi-Insurer Side-by-Side Comparison Retrieval
    comp_results = retriever.retrieve_for_plan_comparison(
        query="Compare maternity waiting period and restoration benefits",
        plan_a="Star Comprehensive",
        plan_b="ReAssure 2.0",
        top_k_per_plan=3,
    )

    # Test Out-of-Scope Corrective RAG Threshold (< 0.35)
    oos_query = "Does this policy pay for robotic hair transplant and dental veneers in Zurich?"
    oos_candidates = retriever.retrieve_across_all_collections(oos_query, top_k=5)
    oos_reranked = reranker.rerank(oos_query, oos_candidates, top_k=3)
    oos_max_score = oos_reranked[0].rerank_score if oos_reranked else 0.0

    total_q = len(TRICKY_15_QUERIES)
    summary = {
        "status": "SUCCESS",
        "reranker_backend": reranker.backend_mode,
        "total_benchmark_queries": total_q,
        "top1_accuracy": round(top1_hits / total_q, 4),
        "top3_accuracy": round(top3_hits / total_q, 4),
        "top1_hits": f"{top1_hits}/{total_q}",
        "top3_hits": f"{top3_hits}/{total_q}",
        "comparison_test": {
            "Star Comprehensive chunks": len(comp_results["Star Comprehensive"]),
            "ReAssure 2.0 chunks": len(comp_results["ReAssure 2.0"]),
        },
        "corrective_rag_guardrail_test": {
            "out_of_scope_query": oos_query,
            "max_rerank_score": oos_max_score,
            "threshold": settings.relevance_score_threshold,
            "correctly_flagged_low_confidence": oos_max_score < settings.relevance_score_threshold,
        },
        "query_results": query_logs,
    }
    return summary


if __name__ == "__main__":
    report = run_milestone2_evaluation()
    print(json.dumps(report, indent=2))
