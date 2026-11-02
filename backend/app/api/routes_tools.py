"""
Deterministic Tools, Plan Comparator, Claim Calculator, IRDAI Grievance &
Phase 2 Autonomous Agent Endpoints (`routes_tools.py`) for BimaSense AI (Milestone 4 & 7).

Exposes:
- `POST /api/v1/compare`: Side-by-Side Plan Comparator (Pillar 2)
- `POST /api/v1/calculator/estimate`: Deterministic Out-of-Pocket & Room-Rent Calculator (Pillar 3)
- `POST /api/v1/grievance/verify`: IRDAI Rights & Claim Rejection Assistant (Pillar 4)
- `POST /api/v1/agent/audit-bill`: Multimodal Hospital Bill Auditor Agent (Milestone 7)
- `POST /api/v1/agent/ombudsman-form6`: Autonomous GRO & Insurance Ombudsman Form VI Agent (Milestone 7)
"""

from __future__ import annotations

from fastapi import APIRouter

from app.agent.autonomous_agents import (
    AutonomousOmbudsmanFilingAgent,
    MultimodalHospitalBillAuditorAgent,
)
from app.agent.graph import build_bimasense_graph
from app.agent.nodes import _get_reranker, _get_retriever
from app.agent.tools import (
    calculate_proportionate_deduction,
    check_consumable_deduction,
    verify_irdai_moratorium_and_tat,
)
from app.config import settings
from app.retrieval.qdrant_client import MetadataFilter
from app.schemas.api_models import (
    ClaimEstimateRequest,
    ClaimEstimateResponse,
    ComparePlansRequest,
    ComparePlansResponse,
    GrievanceVerifyRequest,
    GrievanceVerifyResponse,
    HospitalBillAuditRequest,
    HospitalBillAuditResponse,
    OmbudsmanForm6Request,
    OmbudsmanForm6Response,
)

router = APIRouter(prefix="/api/v1", tags=["Comparator, Claim Calculator & Autonomous Agents"])

_AGENT_GRAPH = build_bimasense_graph()
_BILL_AUDITOR_AGENT = MultimodalHospitalBillAuditorAgent()
_OMBUDSMAN_AGENT = AutonomousOmbudsmanFilingAgent()


@router.post("/compare", response_model=ComparePlansResponse)
async def compare_insurance_plans(request: ComparePlansRequest) -> ComparePlansResponse:
    """
    Compares two insurance plans (`plan_a` vs. `plan_b`) across structured criteria
    using parallel metadata-filtered Qdrant retrievals and returns a side-by-side matrix.
    """
    criteria_str = ", ".join(request.criteria)
    query_text = request.custom_question or (
        f"Compare {request.plan_a} and {request.plan_b} across {criteria_str}."
    )

    final_state = _AGENT_GRAPH.invoke(
        {
            "user_query": query_text,
            "user_id": request.user_id,
            "compare_plans": [request.plan_a, request.plan_b],
        }
    )

    all_rows = final_state.get("comparison_table") or []
    if request.criteria:
        requested_lower = {c.lower() for c in request.criteria}
        filtered_rows = [
            r for r in all_rows
            if any(req in r.criterion.lower() or r.criterion.lower() in req for req in requested_lower)
        ]
        rows_to_return = filtered_rows or all_rows
    else:
        rows_to_return = all_rows

    return ComparePlansResponse(
        plan_a=request.plan_a,
        plan_b=request.plan_b,
        summary_markdown=final_state.get("answer_markdown", ""),
        comparison_table=rows_to_return,
        citations=final_state.get("citations", []),
    )


@router.post("/calculator/estimate", response_model=ClaimEstimateResponse)
async def estimate_claim_payout(request: ClaimEstimateRequest) -> ClaimEstimateResponse:
    """
    Runs deterministic claim payout math (`calculate_proportionate_deduction`),
    optional Annexure-I consumable auditing (`check_consumable_deduction`),
    and retrieves the governing room-rent / co-payment citations for `plan_name`.
    """
    consumable_audit = None
    consumables_total = request.consumables_amount

    if request.billed_consumables:
        consumable_audit = check_consumable_deduction(
            billed_items=[item.model_dump() for item in request.billed_consumables],
            has_consumables_rider=request.has_consumables_rider,
        )
        if consumables_total == 0.0:
            consumables_total = float(consumable_audit["patient_non_payable_total"]) + float(
                consumable_audit["insurer_payable_consumables_total"]
            )

    calc = calculate_proportionate_deduction(
        total_bill=request.total_bill,
        allowed_room_rent=request.allowed_room_rent,
        actual_room_rent=request.actual_room_rent,
        associated_medical_expenses=request.associated_medical_expenses,
        exempt_expenses_medicines_implants_icu=request.exempt_expenses_medicines_implants_icu,
        consumables_amount=consumables_total,
        has_consumables_rider=request.has_consumables_rider,
        deductible=request.deductible,
        co_pay_percent=request.co_pay_percent,
        sum_insured=request.sum_insured,
        plan_name=request.plan_name,
    )

    retriever = _get_retriever()
    reranker = _get_reranker()
    rule_query = f"Room rent limit proportionate deduction co-payment consumables in {request.plan_name}"
    cands = retriever.retrieve(
        query=rule_query,
        collection_name=settings.collection_insurer_policies,
        filters=MetadataFilter(plan_name=request.plan_name),
        top_k=5,
    )
    reranked = reranker.rerank(query=rule_query, candidates=cands, top_k=2)
    citations = [c.to_citation() for c in reranked]

    return ClaimEstimateResponse(
        plan_name=calc.plan_name,
        sum_insured=calc.sum_insured,
        total_hospital_bill=calc.total_hospital_bill,
        proportionate_multiplier=calc.proportionate_multiplier,
        proportionate_deduction_amount=calc.proportionate_deduction_amount,
        non_payable_consumables_deduction=calc.non_payable_consumables_deduction,
        deductible_applied=calc.deductible_applied,
        co_payment_percentage=calc.co_payment_percentage,
        co_payment_deduction_amount=calc.co_payment_deduction_amount,
        final_payable_claim_amount=calc.final_payable_claim_amount,
        total_out_of_pocket_cost=calc.total_out_of_pocket_cost,
        itemized_notes=calc.itemized_notes,
        consumable_audit=consumable_audit,
        policy_rule_citations=citations,
    )


@router.post("/grievance/verify", response_model=GrievanceVerifyResponse)
async def verify_claim_rejection_and_draft_grievance(
    request: GrievanceVerifyRequest,
) -> GrievanceVerifyResponse:
    """
    Verifies a claim rejection or cashless delay against the IRDAI Master Circular 2024
    (`IRDAI/HLT/CIR/PRO/84/05/2024`) and generates a legally cited GRO escalation email.
    """
    audit = verify_irdai_moratorium_and_tat(
        continuous_policy_months=request.continuous_policy_months,
        rejection_reason=request.rejection_reason,
        cashless_preauth_wait_minutes=request.cashless_preauth_wait_minutes,
        discharge_wait_hours=request.discharge_wait_hours,
        rejected_by_tpa_directly=request.rejected_by_tpa_directly,
        ombudsman_award_days_overdue=request.ombudsman_award_days_overdue,
    )

    retriever = _get_retriever()
    reranker = _get_reranker()
    reg_query = f"IRDAI Master Circular {request.rejection_reason} moratorium cashless discharge TPA ombudsman"
    cands = retriever.retrieve(
        query=reg_query,
        collection_name=settings.collection_irdai_regulations,
        top_k=5,
    )
    reranked = reranker.rerank(query=reg_query, candidates=cands, top_k=3)
    citations = [c.to_citation() for c in reranked]

    violations = audit["violations_detected"]
    if violations:
        v_summary = "\n".join(f"- {v['clause']} ({v['circular_ref']}): {v['finding']}" for v in violations)
        email_draft = (
            f"Subject: Formal Representation Against Claim Action — {request.insurer_name} {request.plan_name} "
            f"(Ref: IRDAI/HLT/CIR/PRO/84/05/2024)\n\n"
            f"To,\nThe Grievance Redressal Officer (GRO),\n{request.insurer_name}\n\n"
            f"Dear Sir/Madam,\n\n"
            f"I am writing to formally contest the action taken on my health insurance claim under {request.plan_name} "
            f"(continuous policy tenure: {request.continuous_policy_months} months). Based on the mandatory provisions of the "
            f"IRDAI Master Circular on Health Insurance Business 2024 (Ref: IRDAI/HLT/CIR/PRO/84/05/2024), the following "
            f"statutory breaches apply to my case:\n\n"
            f"{v_summary}\n\n"
            f"I request an immediate review by the Insurer's Claims Review Committee (CRC) and full settlement of the "
            f"admissible claim amount within 15 days, failing which I will escalate this complaint to the IRDAI Bima Bharosa "
            f"Portal and file Form VI before the Office of the Insurance Ombudsman.\n\n"
            f"Sincerely,\nPolicyholder"
        )
    else:
        email_draft = (
            f"Subject: Request for Detailed Claim Review — {request.insurer_name} {request.plan_name}\n\n"
            f"Dear Grievance Redressal Officer (GRO),\n\n"
            f"Please provide the written findings of the Insurer's three-member Claims Review Committee (CRC) as mandated "
            f"under Clause 3.1 of IRDAI Master Circular IRDAI/HLT/CIR/PRO/84/05/2024 regarding my claim.\n\n"
            f"Sincerely,\nPolicyholder"
        )

    return GrievanceVerifyResponse(
        circular_ref=audit["circular_ref"],
        is_rejection_or_action_illegal=audit["is_rejection_or_action_illegal"],
        violations_detected=violations,
        ombudsman_penalty_inr=audit["ombudsman_penalty_inr"],
        recommended_escalation_path=audit["recommended_escalation_path"],
        gro_escalation_email_draft=email_draft,
        citations=citations,
    )


@router.post("/agent/audit-bill", response_model=HospitalBillAuditResponse)
async def audit_hospital_discharge_bill_endpoint(
    request: HospitalBillAuditRequest,
) -> HospitalBillAuditResponse:
    """
    Phase 2 Autonomous Agent Endpoint: Audits an itemized hospital discharge bill
    (from CameraX OCR text or structured line items) against IRDAI Annexure-I (68 items)
    and flags illegal hospital room/OT-subsumed charges.
    """
    result = _BILL_AUDITOR_AGENT.audit_hospital_bill(
        plan_name=request.plan_name,
        has_consumables_rider=request.has_consumables_rider,
        line_items=[item.model_dump() for item in request.line_items] if request.line_items else None,
        raw_bill_text=request.raw_bill_text,
    )
    return HospitalBillAuditResponse(**result)


@router.post("/agent/ombudsman-form6", response_model=OmbudsmanForm6Response)
async def generate_ombudsman_form6_endpoint(
    request: OmbudsmanForm6Request,
) -> OmbudsmanForm6Response:
    """
    Phase 2 Autonomous Agent Endpoint: Performs a multi-step IRDAI compliance check
    and generates a complete Council for Insurance Ombudsmen (CIO) Form VI dossier
    plus a final GRO legal notice.
    """
    result = _OMBUDSMAN_AGENT.generate_ombudsman_form_vi_package(
        complainant_name=request.complainant_name,
        city=request.city,
        insurer_name=request.insurer_name,
        plan_name=request.plan_name,
        policy_number=request.policy_number,
        claim_number=request.claim_number,
        claimed_amount_inr=request.claimed_amount_inr,
        continuous_policy_months=request.continuous_policy_months,
        rejection_reason=request.rejection_reason,
        discharge_wait_hours=request.discharge_wait_hours,
        rejected_by_tpa_directly=request.rejected_by_tpa_directly,
        ombudsman_award_days_overdue=request.ombudsman_award_days_overdue,
    )
    return OmbudsmanForm6Response(**result)
