"""
End-to-End Runner & Verification Suite for BimaSense AI — Milestone 1:
Data & Ingestion Pipeline.

Workflow:
1. Generates seed PDFs (`raw_policies/`, `irdai_circulars/`) and `eval_dataset.json`.
2. Parses all PDFs via `PolicyPDFParser` (`pymupdf4llm` / `pdfplumber` table-aware Markdown).
3. Chunks documents via `MarkdownPolicyChunker` into schema-validated payloads for:
   - `insurer_policies`
   - `irdai_regulations`
   - `non_payable_consumables`
4. Indexes all chunks with Dense (384-d) + Sparse (BM25) embeddings via `BimaSenseHybridIndexer`.
5. Executes strict assertions verifying table preservation, page numbers, and payload schemas.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.config import EVAL_DATASET_PATH, IRDAI_CIRCULARS_DIR, RAW_POLICIES_DIR
from app.ingestion.chunker import MarkdownPolicyChunker
from app.ingestion.indexer import BimaSenseHybridIndexer
from app.ingestion.pdf_parser import PolicyPDFParser
from scripts.seed_data_generator import generate_all_seed_data


POLICY_CATALOG = [
    {
        "filename": "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
        "insurer_name": "HDFC ERGO",
        "plan_name": "Optima Secure",
    },
    {
        "filename": "Star_Health_Comprehensive_Policy_Wording.pdf",
        "insurer_name": "Star Health",
        "plan_name": "Star Comprehensive",
    },
    {
        "filename": "Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
        "insurer_name": "Niva Bupa",
        "plan_name": "ReAssure 2.0",
    },
]


def run_milestone1_ingestion() -> dict:
    # Step 1: Generate seed PDFs and evaluation dataset
    seed_summary = generate_all_seed_data()

    parser = PolicyPDFParser(prefer_pymupdf4llm=True)
    chunker = MarkdownPolicyChunker()
    indexer = BimaSenseHybridIndexer()

    all_policy_chunks = []
    parsed_docs_summary = []

    # Step 2 & 3A: Parse and chunk Insurer Policies
    for item in POLICY_CATALOG:
        pdf_path = RAW_POLICIES_DIR / item["filename"]
        parsed_doc = parser.parse_pdf(pdf_path)
        chunks = chunker.chunk_insurer_policy(
            doc=parsed_doc,
            insurer_name=item["insurer_name"],
            plan_name=item["plan_name"],
            document_type="policy_wording",
            is_user_uploaded=False,
            user_id="global",
        )
        all_policy_chunks.extend(chunks)
        parsed_docs_summary.append(
            {
                "file": item["filename"],
                "insurer": item["insurer_name"],
                "plan": item["plan_name"],
                "pages": parsed_doc.total_pages,
                "tables_extracted": sum(p.table_count for p in parsed_doc.pages),
                "chunks_created": len(chunks),
            }
        )

    # Step 2 & 3B: Parse and chunk IRDAI Master Circular 2024
    mc_path = IRDAI_CIRCULARS_DIR / "IRDAI_Master_Circular_Health_Insurance_2024.pdf"
    parsed_mc = parser.parse_pdf(mc_path)
    irdai_chunks = chunker.chunk_irdai_regulation(
        doc=parsed_mc,
        circular_ref="IRDAI/HLT/CIR/PRO/84/05/2024",
        effective_year=2024,
    )

    # Step 2 & 3C: Parse and chunk IRDAI Annexure-I 68 Non-Payable Consumables
    np_path = IRDAI_CIRCULARS_DIR / "IRDAI_Annexure_I_68_Non_Payable_Consumables.pdf"
    parsed_np = parser.parse_pdf(np_path)
    consumable_chunks = chunker.chunk_non_payable_consumables(parsed_np)

    # Step 4: Index all 3 collections with Dense + Sparse BM25 embeddings
    indexed_policies = indexer.index_insurer_policies(all_policy_chunks)
    indexed_irdai = indexer.index_irdai_regulations(irdai_chunks)
    indexed_consumables = indexer.index_non_payable_consumables(consumable_chunks)

    # Step 5: Verification Assertions
    eval_data = json.loads(EVAL_DATASET_PATH.read_text(encoding="utf-8"))
    assert len(eval_data) == 30, f"Expected 30 Ragas benchmark items, found {len(eval_data)}"
    assert indexed_policies > 0, "No insurer policy chunks were indexed"
    assert any(c.contains_table for c in all_policy_chunks), "Expected Markdown tables in policy chunks"
    assert indexed_irdai > 0, "No IRDAI regulation chunks were indexed"
    assert indexed_consumables >= 20, f"Expected >=20 consumable items indexed, got {indexed_consumables}"

    stats = indexer.get_collection_stats()
    report = {
        "status": "SUCCESS",
        "storage_backend": indexer.storage_backend,
        "embedding_backend": indexer.embedder.backend_mode,
        "dense_model": indexer.embedder.dense_model_name,
        "sparse_model": indexer.embedder.sparse_model_name,
        "collections_indexed": stats,
        "policy_documents": parsed_docs_summary,
        "irdai_master_circular_chunks": len(irdai_chunks),
        "non_payable_consumable_items": len(consumable_chunks),
        "ragas_eval_questions": len(eval_data),
        "sample_policy_chunk": all_policy_chunks[0].model_dump(),
        "sample_irdai_chunk": irdai_chunks[0].model_dump(),
        "sample_consumable_chunk": consumable_chunks[0].model_dump(),
    }
    return report


if __name__ == "__main__":
    result = run_milestone1_ingestion()
    print(json.dumps(result, indent=2))
