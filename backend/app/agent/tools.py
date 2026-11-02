"""
Deterministic Python Tools for BimaSense AI (Milestone 3):
1. `calculate_proportionate_deduction`: Computes exact room-rent proportionate deductions,
   exempt items (Pharmacy, Stents/Implants, Diagnostics, ICU), consumable deductions,
   aggregate deductibles, and senior citizen co-payments.
2. `check_consumable_deduction`: Audits billed hospital consumables against the IRDAI
   Annexure-I 68 Non-Payable & Subsumed items list and policy consumable riders.
3. `verify_irdai_moratorium_and_tat`: Evaluates claim rejections and cashless turnaround
   delays against the IRDAI Master Circular 2024 (`IRDAI/HLT/CIR/PRO/84/05/2024`).
"""

from __future__ import annotations

from typing import Any
from pydantic import Field
from app.schemas.api_models import BimaSenseBaseModel


# Canonical IRDAI Annexure-I Consumables Lookup Table for Deterministic Auditing
ANNEXURE_I_CONSUMABLES_DB: dict[str, dict[str, Any]] = {
    "baby food": {"item_number": 1, "item_name": "Baby Food", "status": "non_payable_unless_rider"},
    "baby utilities": {"item_number": 2, "item_name": "Baby Utilities Charges", "status": "non_payable_unless_rider"},
    "beauty services": {"item_number": 3, "item_name": "Beauty Services", "status": "non_payable_unless_rider"},
    "belts": {"item_number": 4, "item_name": "Belts / Braces", "status": "payable_when_part_of_discharge"},
    "braces": {"item_number": 4, "item_name": "Belts / Braces", "status": "payable_when_part_of_discharge"},
    "cotton swabs": {"item_number": 5, "item_name": "Buds / Cotton Swabs", "status": "subsumed_in_procedure_charges"},
    "crepe bandage": {"item_number": 12, "item_name": "Crepe Bandage", "status": "non_payable_unless_rider"},
    "diapers": {"item_number": 14, "item_name": "Diapers / Underpads / Adult Diapers", "status": "non_payable_unless_rider"},
    "eye pad": {"item_number": 18, "item_name": "Eye Pad / Eye Shield", "status": "subsumed_in_procedure_charges"},
    "shoe cover": {"item_number": 21, "item_name": "Foot Cover / Shoe Cover", "status": "subsumed_in_room_charges"},
    "patient gown": {"item_number": 24, "item_name": "Gown / Patient Gown", "status": "subsumed_in_room_charges"},
    "gown": {"item_number": 24, "item_name": "Gown / Patient Gown", "status": "subsumed_in_room_charges"},
    "laundry": {"item_number": 38, "item_name": "Laundry Charges", "status": "subsumed_in_room_charges"},
    "laundry charges": {"item_number": 38, "item_name": "Laundry Charges", "status": "subsumed_in_room_charges"},
    "nebulization kit": {"item_number": 42, "item_name": "Nebulization Kit", "status": "non_payable_unless_rider"},
    "nebulizer": {"item_number": 42, "item_name": "Nebulization Kit", "status": "non_payable_unless_rider"},
    "oxygen cylinder": {"item_number": 45, "item_name": "Oxygen Cylinder (Outside Hospital)", "status": "non_payable_unless_rider"},
    "pulse oximeter": {"item_number": 47, "item_name": "Pulse Oximeter Probe", "status": "subsumed_in_room_charges"},
    "oximeter probe": {"item_number": 47, "item_name": "Pulse Oximeter Probe", "status": "subsumed_in_room_charges"},
    "sanitizer": {"item_number": 51, "item_name": "Sanitizer / Hand Wash / Betadine", "status": "subsumed_in_room_charges"},
    "betadine": {"item_number": 51, "item_name": "Sanitizer / Hand Wash / Betadine", "status": "subsumed_in_room_charges"},
    "surgical blades": {"item_number": 54, "item_name": "Surgical Blades / Scalpel", "status": "subsumed_in_procedure_charges"},
    "surgical gloves": {"item_number": 56, "item_name": "Surgical Gloves / Examination Gloves", "status": "non_payable_unless_rider"},
    "gloves": {"item_number": 56, "item_name": "Surgical Gloves / Examination Gloves", "status": "non_payable_unless_rider"},
    "syringes": {"item_number": 59, "item_name": "Syringes / IV Cannula / Infusion Set", "status": "subsumed_in_procedure_charges"},
    "thermometer": {"item_number": 63, "item_name": "Thermometer", "status": "subsumed_in_room_charges"},
    "admission kit": {"item_number": 68, "item_name": "Admission Kit / Discharge Kit / File Charges", "status": "subsumed_in_room_charges"},
    "file charges": {"item_number": 68, "item_name": "Admission Kit / Discharge Kit / File Charges", "status": "subsumed_in_room_charges"},
}


class ClaimBreakdownResult(BimaSenseBaseModel):
    """Structured output of `calculate_proportionate_deduction`."""

    plan_name: str = "Custom Policy"
    sum_insured: float
    total_hospital_bill: float
    allowed_room_rent_per_day: float | None
    actual_room_rent_per_day: float | None
    proportionate_multiplier: float = Field(
        ..., description="Min(1.0, Allowed Room Rent / Actual Room Rent)"
    )
    proportionate_deduction_amount: float
    non_payable_consumables_deduction: float
    deductible_applied: float
    co_payment_percentage: float
    co_payment_deduction_amount: float
    sum_insured_cap_deduction: float = 0.0
    final_payable_claim_amount: float
    total_out_of_pocket_cost: float
    itemized_notes: list[str] = Field(default_factory=list)
    formula_used: str = (
        "Payable Claim = [ (Proportionate-Subject Items * (Allowed Room Cap / Actual Room Rent)) "
        "+ Exempt Items (Medicines/Implants/ICU) + Payable Consumables - Deductible ] * (1 - CoPay%)"
    )


def calculate_proportionate_deduction(
    total_bill: float,
    allowed_room_rent: float | None = None,
    actual_room_rent: float | None = None,
    associated_medical_expenses: float | None = None,
    exempt_expenses_medicines_implants_icu: float = 0.0,
    consumables_amount: float = 0.0,
    has_consumables_rider: bool = False,
    deductible: float = 0.0,
    co_pay_percent: float = 0.0,
    sum_insured: float = 1_000_000.0,
    plan_name: str = "Custom Policy",
) -> ClaimBreakdownResult:
    """
    Deterministic calculator implementing Master Plan Section 3 (Pillar 3):
        Payable = Sum_eligible(Item_Cost * (Allowed_Room_Cap / Actual_Room_Rent)) - Deductibles
    while accounting for:
    - Clause 1.1.3 Exemptions (Pharmacy/Medicines, Implants/Stents, Diagnostics, ICU are NOT subject
      to proportionate deduction).
    - Non-payable consumables (deducted unless `has_consumables_rider=True`, e.g., HDFC Protect Benefit
      or Niva Bupa Safeguard+).
    - Aggregate deductible and mandatory senior citizen co-payment percentage.
    """
    notes: list[str] = []

    # 1. Determine Room Rent Proportionate Multiplier (preserve exact ratio before rounding product)
    if (
        allowed_room_rent is not None
        and actual_room_rent is not None
        and allowed_room_rent > 0
        and actual_room_rent > allowed_room_rent
    ):
        exact_ratio = allowed_room_rent / actual_room_rent
        notes.append(
            f"Room Rent Exceeded: Allowed cap is Rs. {allowed_room_rent:,.0f}/day vs. Actual Rs. {actual_room_rent:,.0f}/day "
            f"(Proportionate factor = {exact_ratio:.2%})."
        )
    else:
        exact_ratio = 1.0
        notes.append("No Room Rent Proportionate Deduction: Room chosen is within eligible limit (Multiplier = 100%).")

    # 2. Split Bill into Subject-to-Proportionate, Exempt (Medicines/Stents/ICU), and Consumables
    if associated_medical_expenses is None:
        subject_amount = max(0.0, total_bill - exempt_expenses_medicines_implants_icu - consumables_amount)
    else:
        subject_amount = max(0.0, associated_medical_expenses)

    payable_subject = round(subject_amount * exact_ratio, 2)
    prop_deduction = round(subject_amount - payable_subject, 2)

    if prop_deduction > 0:
        notes.append(
            f"Associated Medical Expenses (Surgeon, OT, Room, Nursing = Rs. {subject_amount:,.0f}) reduced by "
            f"Rs. {prop_deduction:,.0f} to Rs. {payable_subject:,.0f}."
        )

    if exempt_expenses_medicines_implants_icu > 0:
        notes.append(
            f"Exempt Items (Pharmacy/Medicines, Implants/Stents, ICU = Rs. {exempt_expenses_medicines_implants_icu:,.0f}) "
            f"are paid at 100% without proportionate deduction (Clause 1.1.3)."
        )

    # 3. Consumables Audit
    if consumables_amount > 0:
        if has_consumables_rider:
            payable_consumables = consumables_amount
            consumable_deduction = 0.0
            notes.append(
                f"Consumables (Rs. {consumables_amount:,.0f}) are 100% payable via active Consumables Rider "
                f"(Protect Benefit / Safeguard+ / Extra Protect)."
            )
        else:
            payable_consumables = 0.0
            consumable_deduction = round(consumables_amount, 2)
            notes.append(
                f"Consumables (Rs. {consumables_amount:,.0f}) deducted as non-payable under IRDAI Annexure-I "
                f"(no consumables rider active)."
            )
    else:
        payable_consumables = 0.0
        consumable_deduction = 0.0

    gross_admissible = payable_subject + exempt_expenses_medicines_implants_icu + payable_consumables

    # 4. Subtract Aggregate Deductible
    applied_deductible = min(gross_admissible, max(0.0, deductible))
    after_deductible = max(0.0, gross_admissible - applied_deductible)
    if applied_deductible > 0:
        notes.append(f"Aggregate Deductible of Rs. {applied_deductible:,.0f} subtracted.")

    # 5. Apply Mandatory Co-Payment (e.g., 10% for entry age >= 61 in Star Comprehensive)
    copay_rate = max(0.0, min(100.0, co_pay_percent)) / 100.0
    copay_deduction = round(after_deductible * copay_rate, 2)
    after_copay = round(after_deductible - copay_deduction, 2)
    if copay_deduction > 0:
        notes.append(
            f"Mandatory Co-Payment ({co_pay_percent:.0f}%) deducted: Rs. {copay_deduction:,.0f}."
        )

    # 6. Cap at Sum Insured
    if after_copay > sum_insured:
        si_cap_deduction = round(after_copay - sum_insured, 2)
        final_payable = round(sum_insured, 2)
        notes.append(f"Capped at Policy Sum Insured of Rs. {sum_insured:,.0f}.")
    else:
        si_cap_deduction = 0.0
        final_payable = after_copay

    out_of_pocket = round(max(0.0, total_bill - final_payable), 2)

    return ClaimBreakdownResult(
        plan_name=plan_name,
        sum_insured=sum_insured,
        total_hospital_bill=total_bill,
        allowed_room_rent_per_day=allowed_room_rent,
        actual_room_rent_per_day=actual_room_rent,
        proportionate_multiplier=round(exact_ratio, 4),
        proportionate_deduction_amount=prop_deduction,
        non_payable_consumables_deduction=consumable_deduction,
        deductible_applied=applied_deductible,
        co_payment_percentage=co_pay_percent,
        co_payment_deduction_amount=copay_deduction,
        sum_insured_cap_deduction=si_cap_deduction,
        final_payable_claim_amount=final_payable,
        total_out_of_pocket_cost=out_of_pocket,
        itemized_notes=notes,
    )


def check_consumable_deduction(
    billed_items: list[dict[str, Any]],
    has_consumables_rider: bool = False,
) -> dict[str, Any]:
    """
    Audits a list of billed hospital consumables (`[{"name": "Surgical Gloves", "cost": 1200}, ...]`)
    against the IRDAI Annexure-I 68 Non-Payable & Subsumed items database.
    Flags illegal hospital overcharges (items subsumed in room/procedure tariffs) vs. rider-payable items.
    """
    audited_rows: list[dict[str, Any]] = []
    illegal_hospital_billing_total = 0.0
    insurer_payable_total = 0.0
    patient_out_of_pocket_total = 0.0

    for item in billed_items:
        raw_name = str(item.get("name", "")).strip()
        cost = float(item.get("cost", 0.0))
        name_lower = raw_name.lower()

        matched_entry = None
        for key, entry in ANNEXURE_I_CONSUMABLES_DB.items():
            if key in name_lower or name_lower in key:
                matched_entry = entry
                break

        if matched_entry is None:
            status = "non_payable_unless_rider"
            item_no = 0
            canonical_name = raw_name
        else:
            status = matched_entry["status"]
            item_no = matched_entry["item_number"]
            canonical_name = matched_entry["item_name"]

        if status in ("subsumed_in_room_charges", "subsumed_in_procedure_charges"):
            verdict = "ILLEGAL SEPARATE BILLING (Subsumed in Room/OT Tariff — Hospital Must Waive)"
            illegal_hospital_billing_total += cost
        elif status == "payable_when_part_of_discharge":
            verdict = "PAYABLE BY INSURER (Prescribed Post-Surgical Stabilization Aid)"
            insurer_payable_total += cost
        else:
            if has_consumables_rider:
                verdict = "PAYABLE BY INSURER (Covered under Active Consumables Rider)"
                insurer_payable_total += cost
            else:
                verdict = "NON-PAYABLE BY INSURER (Patient Out-of-Pocket without Consumables Rider)"
                patient_out_of_pocket_total += cost

        audited_rows.append(
            {
                "billed_name": raw_name,
                "annexure_i_item_number": item_no,
                "canonical_item_name": canonical_name,
                "cost": cost,
                "irdai_status": status,
                "audit_verdict": verdict,
            }
        )

    return {
        "has_consumables_rider": has_consumables_rider,
        "audited_items": audited_rows,
        "illegal_hospital_overcharge_total": round(illegal_hospital_billing_total, 2),
        "insurer_payable_consumables_total": round(insurer_payable_total, 2),
        "patient_non_payable_total": round(patient_out_of_pocket_total, 2),
    }


def verify_irdai_moratorium_and_tat(
    continuous_policy_months: int | None = None,
    rejection_reason: str = "",
    cashless_preauth_wait_minutes: int | None = None,
    discharge_wait_hours: float | None = None,
    rejected_by_tpa_directly: bool = False,
    ombudsman_award_days_overdue: int | None = None,
) -> dict[str, Any]:
    """
    Evaluates a policyholder's claim rejection or cashless delay against
    IRDAI Master Circular `IRDAI/HLT/CIR/PRO/84/05/2024` and outputs legal violations + penalties.
    """
    violations: list[dict[str, str]] = []
    is_rejection_illegal = False

    # 1. Check 36-Month Moratorium Rule (Clause 1.1)
    if continuous_policy_months is not None and continuous_policy_months >= 36:
        if any(k in rejection_reason.lower() for k in ["non-disclosure", "pre-existing", "ped", "misrepresentation", "suppression"]):
            is_rejection_illegal = True
            violations.append(
                {
                    "clause": "Clause 1.1 (36-Month Moratorium Period)",
                    "circular_ref": "IRDAI/HLT/CIR/PRO/84/05/2024, Page 1",
                    "finding": (
                        f"ILLEGAL REJECTION: Policy has completed {continuous_policy_months} continuous months "
                        f"(>= 36 months moratorium threshold). Under IRDAI Master Circular 2024, no claim can be "
                        f"repudiated on grounds of non-disclosure or misrepresentation of a Pre-Existing Disease "
                        f"after 36 continuous months unless the insurer proves established fraud."
                    ),
                }
            )

    # 2. Check Direct TPA Rejection Ban (Clause 3.1)
    if rejected_by_tpa_directly:
        is_rejection_illegal = True
        violations.append(
            {
                "clause": "Clause 3.1 (Ban on TPA Claim Repudiation)",
                "circular_ref": "IRDAI/HLT/CIR/PRO/84/05/2024, Page 3",
                "finding": (
                    "ILLEGAL REJECTION PROCEDURE: A Third Party Administrator (TPA) has zero statutory authority "
                    "to reject a claim on its own. Every claim repudiation requires explicit sign-off from the "
                    "Insurer's three-member Claims Review Committee (CRC)."
                ),
            }
        )

    # 3. Check 1-Hour Cashless Pre-Authorization Mandate (Clause 2.1)
    if cashless_preauth_wait_minutes is not None and cashless_preauth_wait_minutes > 60:
        violations.append(
            {
                "clause": "Clause 2.1 (1-Hour Cashless Pre-Authorization TAT)",
                "circular_ref": "IRDAI/HLT/CIR/PRO/84/05/2024, Page 2",
                "finding": (
                    f"REGULATORY TAT BREACH: Pre-authorization took {cashless_preauth_wait_minutes} minutes, "
                    f"violating IRDAI's mandatory 60-minute (1-hour) cashless authorization limit."
                ),
            }
        )

    # 4. Check 3-Hour Final Discharge Mandate (Clause 2.2 & 2.3)
    if discharge_wait_hours is not None and discharge_wait_hours > 3.0:
        violations.append(
            {
                "clause": "Clause 2.2 & 2.3 (3-Hour Discharge Mandate & Shareholders' Fund Liability)",
                "circular_ref": "IRDAI/HLT/CIR/PRO/84/05/2024, Page 2",
                "finding": (
                    f"REGULATORY TAT BREACH: Final discharge took {discharge_wait_hours} hours (exceeding the "
                    f"3-hour mandate). Any extra hospital room/bed charges levied for the delay must be borne "
                    f"directly by the Insurer from its Shareholders' Fund and cannot be billed to the patient."
                ),
            }
        )

    # 5. Check Insurance Ombudsman Award Penalty (Clause 3.3)
    ombudsman_penalty_rs = 0
    if ombudsman_award_days_overdue is not None and ombudsman_award_days_overdue > 0:
        ombudsman_penalty_rs = ombudsman_award_days_overdue * 5000
        violations.append(
            {
                "clause": "Clause 3.3 (Insurance Ombudsman Award Non-Compliance Penalty)",
                "circular_ref": "IRDAI/HLT/CIR/PRO/84/05/2024, Page 3",
                "finding": (
                    f"STATUTORY PENALTY TRIGGERED: Insurer is {ombudsman_award_days_overdue} days past the 30-day "
                    f"Ombudsman compliance window, accruing a mandatory penalty of Rs. 5,000/day "
                    f"(Total: Rs. {ombudsman_penalty_rs:,.0f}) plus 2% penal interest above bank rate."
                ),
            }
        )

    return {
        "circular_ref": "IRDAI/HLT/CIR/PRO/84/05/2024",
        "is_rejection_or_action_illegal": is_rejection_illegal or len(violations) > 0,
        "violations_detected": violations,
        "ombudsman_penalty_inr": ombudsman_penalty_rs,
        "recommended_escalation_path": [
            "Step 1: Send formal legal notice to Insurer's Grievance Redressal Officer (GRO) citing IRDAI/HLT/CIR/PRO/84/05/2024.",
            "Step 2: If unresolved within 15 days, escalate on IRDAI Bima Bharosa Portal (https://bimabharosa.irdai.gov.in).",
            "Step 3: File Form VI complaint before the Office of the Insurance Ombudsman (for claims up to Rs. 50 Lakhs).",
        ],
    }
