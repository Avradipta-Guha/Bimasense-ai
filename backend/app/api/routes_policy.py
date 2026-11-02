"""
Policy Vault & PDF Upload Endpoints (`routes_policy.py`) for BimaSense AI (Milestone 4).
Exposes:
- `GET /api/v1/policies/list`: Returns pre-loaded Indian insurance plans + user-uploaded policies
  with rich summary cards for the Android Home & Policy Vault Screen.
- `POST /api/v1/policies/upload`: Accepts a user-uploaded Policy PDF via multipart form upload,
  parses layout & tables via `PolicyPDFParser`, chunks via `MarkdownPolicyChunker`, and indexes
  into Qdrant under `user_id`.
- `GET /api/v1/policies/{policy_id}/pdf`: Serves the underlying PDF file for the Android in-app
  `PdfRenderer` citation viewer bottom sheet.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.agent.nodes import _RETRIEVER
from app.config import RAW_POLICIES_DIR
from app.ingestion.chunker import MarkdownPolicyChunker
from app.ingestion.indexer import BimaSenseHybridIndexer
from app.ingestion.pdf_parser import PolicyPDFParser
from app.schemas.api_models import (
    PolicyListResponse,
    PolicySummaryCard,
    PolicyUploadResponse,
)

router = APIRouter(prefix="/api/v1/policies", tags=["Policy Vault & Ingestion"])

# Pre-loaded Indian Health Insurance Plans catalog
PRELOADED_POLICY_CARDS: list[PolicySummaryCard] = [
    PolicySummaryCard(
        policy_id="hdfc-optima-secure",
        insurer_name="HDFC ERGO",
        plan_name="Optima Secure",
        uin="HDFHLIP24092V032324",
        sum_insured_options=["5L", "10L", "20L", "50L", "1Cr"],
        room_rent_rule="At Actuals (Any Room, No ICU Cap)",
        ped_waiting_period="36 Months (Code Excl01)",
        restoration_rule="100% Automatic Restore + 2X Day-1 Secure Benefit",
        consumables_coverage="100% In-Built (Protect Benefit covers all 68 items)",
        co_payment_rule="0% Mandatory Co-Payment across all ages",
        is_user_uploaded=False,
        user_id="global",
        file_name="HDFC_ERGO_Optima_Secure_Policy_Wording.pdf",
        total_pages=3,
    ),
    PolicySummaryCard(
        policy_id="star-comprehensive",
        insurer_name="Star Health",
        plan_name="Star Comprehensive",
        uin="SHAHLIP22028V072122",
        sum_insured_options=["5L", "7.5L", "10L", "25L", "50L", "1Cr"],
        room_rent_rule="Single Private A/C Room (Proportionate Deduction above)",
        ped_waiting_period="36 Months (12 Months with Buy-Back PED Rider)",
        restoration_rule="100% Automatic Restoration once per policy year",
        consumables_coverage="Excluded unless optional Star Extra Protect Rider purchased",
        co_payment_rule="10% Mandatory Co-Pay if entry age >= 61 years",
        is_user_uploaded=False,
        user_id="global",
        file_name="Star_Health_Comprehensive_Policy_Wording.pdf",
        total_pages=3,
    ),
    PolicySummaryCard(
        policy_id="niva-bupa-reassure-2",
        insurer_name="Niva Bupa",
        plan_name="ReAssure 2.0",
        uin="NBHLIP23155V012223",
        sum_insured_options=["5L", "10L", "15L", "25L", "50L", "1Cr"],
        room_rent_rule="All Rooms at Actuals (Except Suite/Presidential Suite)",
        ped_waiting_period="36 Months continuous coverage (Code Excl01)",
        restoration_rule="Unlimited Restoration (ReAssure Forever) from 1st claim",
        consumables_coverage="Covered via Safeguard+ Rider (also protects Booster+)",
        co_payment_rule="0% Mandatory Co-Payment",
        is_user_uploaded=False,
        user_id="global",
        file_name="Niva_Bupa_ReAssure_2_0_Policy_Wording.pdf",
        total_pages=2,
    ),
]

# Runtime registry for user-uploaded policies
_USER_UPLOADED_CARDS: list[PolicySummaryCard] = []


@router.get("/list", response_model=PolicyListResponse)
async def list_policies(
    user_id: str = Query(default="global", description="User ID to include personal uploaded policies"),
) -> PolicyListResponse:
    """Lists all pre-loaded Indian health insurance policies plus any personal PDFs uploaded by `user_id`."""
    user_cards = [
        c for c in _USER_UPLOADED_CARDS if c.user_id in ("global", user_id)
    ]
    combined = PRELOADED_POLICY_CARDS + user_cards
    return PolicyListResponse(total_count=len(combined), policies=combined)


@router.post("/upload", response_model=PolicyUploadResponse)
async def upload_policy_pdf(
    file: UploadFile = File(..., description="Policy Wording or Policy Schedule PDF"),
    insurer_name: str = Form(default="Custom Insurer"),
    plan_name: str = Form(default="Uploaded Health Plan"),
    user_id: str = Form(default="user_default"),
) -> PolicyUploadResponse:
    """
    Uploads a user's personal Policy PDF from the Android app, extracts layout-aware
    Markdown and tables, chunks clauses, and indexes them into Qdrant under `user_id`.
    """
    filename = file.filename or "uploaded_policy.pdf"
    if not filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files (.pdf) are supported.")

    content = await file.read()
    if len(content) < 100:
        raise HTTPException(status_code=400, detail="Uploaded PDF file is empty or corrupted.")

    user_dir = RAW_POLICIES_DIR / "user_uploads" / user_id
    user_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(filename).name
    saved_path = user_dir / safe_name
    saved_path.write_bytes(content)

    parser = PolicyPDFParser(prefer_pymupdf4llm=True)
    chunker = MarkdownPolicyChunker()
    indexer = BimaSenseHybridIndexer()

    parsed_doc = parser.parse_pdf(saved_path)
    chunks = chunker.chunk_insurer_policy(
        doc=parsed_doc,
        insurer_name=insurer_name,
        plan_name=plan_name,
        document_type="policy_wording",
        is_user_uploaded=True,
        user_id=user_id,
    )
    indexed_count = indexer.index_insurer_policies(chunks)

    # Refresh global retriever cache so newly uploaded chunks are immediately searchable
    import app.agent.nodes as agent_nodes

    agent_nodes._RETRIEVER = None

    policy_id = "user-" + hashlib.md5(f"{user_id}:{insurer_name}:{plan_name}:{safe_name}".encode("utf-8")).hexdigest()[:10]
    tables_count = sum(p.table_count for p in parsed_doc.pages)

    card = PolicySummaryCard(
        policy_id=policy_id,
        insurer_name=insurer_name,
        plan_name=plan_name,
        uin="USER-UPLOADED",
        sum_insured_options=["As per Policy Schedule"],
        room_rent_rule="Indexed from Uploaded PDF",
        ped_waiting_period="Indexed from Uploaded PDF",
        restoration_rule="Indexed from Uploaded PDF",
        consumables_coverage="Indexed from Uploaded PDF",
        co_payment_rule="Indexed from Uploaded PDF",
        is_user_uploaded=True,
        user_id=user_id,
        file_name=safe_name,
        total_pages=parsed_doc.total_pages,
    )
    _USER_UPLOADED_CARDS[:] = [c for c in _USER_UPLOADED_CARDS if c.policy_id != policy_id] + [card]

    return PolicyUploadResponse(
        status="indexed",
        policy_id=policy_id,
        insurer_name=insurer_name,
        plan_name=plan_name,
        user_id=user_id,
        file_name=safe_name,
        pages_parsed=parsed_doc.total_pages,
        tables_extracted=tables_count,
        chunks_indexed=indexed_count,
    )


@router.get("/{policy_id}/pdf")
async def download_policy_pdf(policy_id: str) -> FileResponse:
    """
    Serves the raw Policy PDF file so the Android app's `PdfRenderer` bottom sheet
    can jump directly to the cited page number when a user taps a `[Page X]` chip.
    """
    all_cards = PRELOADED_POLICY_CARDS + _USER_UPLOADED_CARDS
    matched = next((c for c in all_cards if c.policy_id == policy_id), None)
    if matched is None:
        raise HTTPException(status_code=404, detail=f"Policy ID '{policy_id}' not found.")

    if matched.is_user_uploaded:
        pdf_path = RAW_POLICIES_DIR / "user_uploads" / matched.user_id / matched.file_name
    else:
        pdf_path = RAW_POLICIES_DIR / matched.file_name

    if not pdf_path.exists():
        raise HTTPException(status_code=404, detail=f"PDF file '{matched.file_name}' not found on disk.")

    return FileResponse(
        path=str(pdf_path),
        media_type="application/pdf",
        filename=matched.file_name,
    )
