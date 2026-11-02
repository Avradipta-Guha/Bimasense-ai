"""
Pydantic data models and schemas for BimaSense AI.
Strictly enforces the Qdrant collection payload schemas (Section 4),
the FastAPI <-> Android API contracts (Section 6), and the Phase 2
Autonomous Agent schemas (Section 7 / Milestone 7).
Compatible with both Pydantic v2 (`model_dump`) and v1 (`dict`).
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class BimaSenseBaseModel(BaseModel):
    """Base model providing unified serialization across Pydantic v1 and v2."""

    def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
        if hasattr(super(), "model_dump"):
            return super().model_dump(*args, **kwargs)  # type: ignore[misc]
        return self.dict(*args, **kwargs)


# ==============================================================================
# 1. Qdrant Vector Payload Schemas (Master Plan Section 4)
# ==============================================================================

SectionCategory = Literal[
    "waiting_periods",
    "exclusions",
    "room_rent",
    "inclusions",
    "claim_procedure",
    "restoration_and_bonuses",
    "general_terms",
]

DocumentType = Literal["policy_wording", "customer_information_sheet", "policy_schedule"]

IrdaiTopic = Literal[
    "moratorium_period",
    "cashless_turnaround",
    "portability",
    "grievance_redressal",
    "claim_settlement",
]

PayableStatus = Literal[
    "non_payable_unless_rider",
    "subsumed_in_room_charges",
    "subsumed_in_procedure_charges",
    "payable_when_part_of_discharge",
]


class InsurerPolicyPayload(BimaSenseBaseModel):
    """Metadata payload schema for the `insurer_policies` Qdrant collection."""

    chunk_id: str = Field(..., description="Deterministic UUID or hash for the chunk")
    insurer_name: str = Field(..., description="Insurer name, e.g., HDFC ERGO, Star Health, Niva Bupa")
    plan_name: str = Field(..., description="Plan name, e.g., Optima Secure, Star Comprehensive, ReAssure 2.0")
    document_type: DocumentType = Field(default="policy_wording")
    section_category: SectionCategory = Field(..., description="Classified clause category")
    section_heading: str = Field(default="", description="Markdown heading breadcrumb")
    page_number: int = Field(..., ge=1, description="1-indexed source PDF page number")
    contains_table: bool = Field(default=False, description="True if chunk contains a Markdown table")
    is_user_uploaded: bool = Field(default=False)
    user_id: str = Field(default="global", description="'global' for pre-loaded plans or user UUID")
    text: str = Field(..., min_length=1, description="Chunk Markdown text content")
    source_file: str = Field(default="", description="Original PDF filename")


class IrdaiRegulationPayload(BimaSenseBaseModel):
    """Metadata payload schema for the `irdai_regulations` Qdrant collection."""

    chunk_id: str
    circular_ref: str = Field(..., description="Circular reference, e.g., IRDAI/HLT/CIR/PRO/84/05/2024")
    topic: IrdaiTopic
    effective_year: int = Field(default=2024, ge=2000)
    page_number: int = Field(..., ge=1)
    section_heading: str = Field(default="")
    text: str = Field(..., min_length=1)
    source_file: str = Field(default="")


class NonPayableConsumablePayload(BimaSenseBaseModel):
    """Metadata payload schema for the `non_payable_consumables` Qdrant collection."""

    chunk_id: str
    item_number: int = Field(..., ge=1, le=250, description="IRDAI Annexure-I item number")
    item_name: str = Field(..., description="Item name, e.g., Surgical Gloves, Nebulization Kit")
    category: str = Field(default="Annexure-I Standard Non-Payable List")
    payable_status: PayableStatus
    page_number: int = Field(default=1, ge=1)
    text: str = Field(..., min_length=1, description="Full description and regulatory rule for the item")
    source_file: str = Field(default="")


# ==============================================================================
# 2. Ingestion & Chunking Intermediate Models
# ==============================================================================

class ParsedPage(BimaSenseBaseModel):
    """Represents a single extracted PDF page in Markdown format."""

    page_number: int = Field(..., ge=1)
    markdown_text: str
    has_tables: bool = False
    table_count: int = 0
    extraction_engine: Literal["pymupdf4llm", "pdfplumber"] = "pymupdf4llm"


class ParsedDocument(BimaSenseBaseModel):
    """Complete parsed representation of a PDF document."""

    file_name: str
    file_path: str
    total_pages: int
    pages: list[ParsedPage]
    metadata: dict[str, Any] = Field(default_factory=dict)


# ==============================================================================
# 3. FastAPI <-> Android API Models (Master Plan Section 5, 6 & 7)
# ==============================================================================

class CitationItem(BimaSenseBaseModel):
    """Page-level clickable citation returned to the Android client."""

    source_title: str = Field(..., description="Source title, e.g., HDFC ERGO Optima Secure")
    page_number: int = Field(..., ge=1)
    section_heading: str = Field(default="")
    section_category: str = Field(default="")
    snippet: str = Field(..., description="Verbatim supporting excerpt from the policy/circular")
    relevance_score: float = Field(default=1.0)


class ComparisonMetricRow(BimaSenseBaseModel):
    """Single row in a side-by-side plan comparison matrix."""

    criterion: str = Field(..., description="Comparison criterion, e.g., Room Rent Limit")
    plan_a_value: str
    plan_b_value: str
    winner_or_verdict: str = Field(default="", description="Brief analytical highlight")


class ChatRequest(BimaSenseBaseModel):
    """Request body for `POST /api/v1/chat/stream` and `POST /api/v1/chat/query`."""

    query: str = Field(..., min_length=2, description="User natural language insurance question")
    user_id: str = Field(default="global", description="User identifier for personal policy isolation")
    selected_plan: str | None = Field(default=None, description="Optional active plan filter, e.g., Optima Secure")
    compare_plans: list[str] = Field(default_factory=list, description="Optional list of plans to compare")


class ChatResponsePayload(BimaSenseBaseModel):
    """Structured output generated by ResponseSynthesizerNode."""

    intent: Literal["policy_qa", "plan_comparison", "claim_calculation", "regulatory_grievance"]
    answer_markdown: str
    citations: list[CitationItem] = Field(default_factory=list)
    comparison_table: list[ComparisonMetricRow] | None = None
    follow_up_suggestions: list[str] = Field(default_factory=list)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)


class PolicySummaryCard(BimaSenseBaseModel):
    """Summary card displayed on the Android Home & Policy Vault Screen."""

    policy_id: str
    insurer_name: str
    plan_name: str
    uin: str = ""
    sum_insured_options: list[str] = Field(default_factory=list)
    room_rent_rule: str
    ped_waiting_period: str
    restoration_rule: str
    consumables_coverage: str
    co_payment_rule: str
    is_user_uploaded: bool = False
    user_id: str = "global"
    file_name: str = ""
    total_pages: int = 1


class PolicyListResponse(BimaSenseBaseModel):
    """Response schema for `GET /api/v1/policies/list`."""

    total_count: int
    policies: list[PolicySummaryCard]


class PolicyUploadResponse(BimaSenseBaseModel):
    """Response schema for `POST /api/v1/policies/upload`."""

    status: str = "indexed"
    policy_id: str
    insurer_name: str
    plan_name: str
    user_id: str
    file_name: str
    pages_parsed: int
    tables_extracted: int
    chunks_indexed: int


class ComparePlansRequest(BimaSenseBaseModel):
    """Request body for `POST /api/v1/compare`."""

    plan_a: str = Field(..., description="First plan name, e.g., Star Comprehensive")
    plan_b: str = Field(..., description="Second plan name, e.g., ReAssure 2.0")
    criteria: list[str] = Field(
        default_factory=lambda: [
            "Room Rent & ICU Limit",
            "PED Waiting Period (Excl01)",
            "Maternity Waiting & Sub-Limit",
            "Restoration Benefit",
            "Non-Payable Consumables (68 Items)",
            "Senior Citizen Co-Payment",
        ]
    )
    custom_question: str | None = Field(default=None)
    user_id: str = Field(default="global")


class ComparePlansResponse(BimaSenseBaseModel):
    """Structured response for `POST /api/v1/compare`."""

    plan_a: str
    plan_b: str
    summary_markdown: str
    comparison_table: list[ComparisonMetricRow]
    citations: list[CitationItem] = Field(default_factory=list)


class BilledConsumableInput(BimaSenseBaseModel):
    """Line item for consumable auditing in `POST /api/v1/calculator/estimate`."""

    name: str
    cost: float = Field(..., ge=0.0)


class ClaimEstimateRequest(BimaSenseBaseModel):
    """Request body for `POST /api/v1/calculator/estimate`."""

    plan_name: str = Field(default="Star Comprehensive")
    sum_insured: float = Field(default=1_000_000.0, gt=0.0)
    total_bill: float = Field(..., gt=0.0)
    allowed_room_rent: float | None = Field(default=None, ge=0.0)
    actual_room_rent: float | None = Field(default=None, ge=0.0)
    associated_medical_expenses: float | None = Field(default=None, ge=0.0)
    exempt_expenses_medicines_implants_icu: float = Field(default=0.0, ge=0.0)
    consumables_amount: float = Field(default=0.0, ge=0.0)
    has_consumables_rider: bool = Field(default=False)
    deductible: float = Field(default=0.0, ge=0.0)
    co_pay_percent: float = Field(default=0.0, ge=0.0, le=100.0)
    billed_consumables: list[BilledConsumableInput] = Field(default_factory=list)


class ClaimEstimateResponse(BimaSenseBaseModel):
    """Response body for `POST /api/v1/calculator/estimate`."""

    plan_name: str
    sum_insured: float
    total_hospital_bill: float
    proportionate_multiplier: float
    proportionate_deduction_amount: float
    non_payable_consumables_deduction: float
    deductible_applied: float
    co_payment_percentage: float
    co_payment_deduction_amount: float
    final_payable_claim_amount: float
    total_out_of_pocket_cost: float
    itemized_notes: list[str]
    consumable_audit: dict[str, Any] | None = None
    policy_rule_citations: list[CitationItem] = Field(default_factory=list)


class GrievanceVerifyRequest(BimaSenseBaseModel):
    """Request body for `POST /api/v1/grievance/verify` (Claim Rejection & IRDAI Helper Screen)."""

    insurer_name: str = Field(default="Health Insurer")
    plan_name: str = Field(default="")
    continuous_policy_months: int = Field(default=0, ge=0)
    rejection_reason: str = Field(default="")
    cashless_preauth_wait_minutes: int | None = Field(default=None, ge=0)
    discharge_wait_hours: float | None = Field(default=None, ge=0.0)
    rejected_by_tpa_directly: bool = Field(default=False)
    ombudsman_award_days_overdue: int | None = Field(default=None, ge=0)


class GrievanceVerifyResponse(BimaSenseBaseModel):
    """Response body for `POST /api/v1/grievance/verify`."""

    circular_ref: str
    is_rejection_or_action_illegal: bool
    violations_detected: list[dict[str, str]]
    ombudsman_penalty_inr: int
    recommended_escalation_path: list[str]
    gro_escalation_email_draft: str
    citations: list[CitationItem] = Field(default_factory=list)


# ==============================================================================
# 4. Phase 2 Autonomous Agent Schemas (Milestone 7)
# ==============================================================================

class HospitalBillAuditRequest(BimaSenseBaseModel):
    """Request body for `POST /api/v1/agent/audit-bill` (Multimodal Hospital Bill Auditor)."""

    plan_name: str = Field(default="Optima Secure")
    has_consumables_rider: bool | None = Field(default=None)
    raw_bill_text: str | None = Field(
        default=None,
        description="Optional OCR-extracted discharge bill text (`Item Name: Rs. 1,200`)",
    )
    line_items: list[BilledConsumableInput] = Field(default_factory=list)


class HospitalBillAuditResponse(BimaSenseBaseModel):
    """Response body for `POST /api/v1/agent/audit-bill`."""

    plan_name: str
    has_consumables_rider: bool
    total_hospital_bill: float
    core_medical_admissible_total: float
    insurer_payable_consumables_total: float
    total_insurer_payable: float
    illegal_hospital_overcharge_total: float
    patient_non_payable_consumables_total: float
    audited_line_items: list[dict[str, Any]]
    dispute_summary: str


class OmbudsmanForm6Request(BimaSenseBaseModel):
    """Request body for `POST /api/v1/agent/ombudsman-form6`."""

    complainant_name: str = Field(default="Policyholder")
    city: str = Field(default="Bhubaneswar")
    insurer_name: str = Field(default="Star Health and Allied Insurance Co. Ltd.")
    plan_name: str = Field(default="Star Comprehensive")
    policy_number: str = Field(default="P/191100/01/2023/009482")
    claim_number: str = Field(default="CLI/2026/191100/0482910")
    claimed_amount_inr: float = Field(default=185_000.0, gt=0.0)
    continuous_policy_months: int = Field(default=42, ge=0)
    rejection_reason: str = Field(
        default="Claim repudiated citing alleged non-disclosure of hypertension prior to policy inception"
    )
    discharge_wait_hours: float | None = Field(default=6.5)
    rejected_by_tpa_directly: bool = Field(default=True)
    ombudsman_award_days_overdue: int | None = Field(default=None)


class OmbudsmanForm6Response(BimaSenseBaseModel):
    """Response body for `POST /api/v1/agent/ombudsman-form6`."""

    is_rejection_illegal: bool
    violations_detected: list[dict[str, str]]
    form_vi_payload: dict[str, Any]
    gro_legal_notice: str
