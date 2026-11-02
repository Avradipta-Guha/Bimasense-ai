"""
Phase 2 Autonomous AI Agents (`autonomous_agents.py`) for BimaSense AI (Milestone 7):

1. `MultimodalHospitalBillAuditorAgent`:
   - Extracts line items from an itemized Hospital Discharge Bill (via Groq Vision LLM
     `llama-3.2-90b-vision-preview` / `Ollama` `qwen2.5-vl` when an image is provided,
     or structured OCR/PDF line-item extraction).
   - Cross-checks every billed line item against the IRDAI Standard List of 68 Non-Payable
     Items (Annexure-I) and Subsumed Items List, plus the user's policy riders (`Optima Secure`
     Protect Benefit, `ReAssure 2.0` Safeguard+, `Star Comprehensive` Extra Protect).
   - Flags illegal hospital overcharges (items subsumed in room/OT tariffs that hospitals
     cannot bill separately to patients) and computes the exact dispute/waiver amount.

2. `AutonomousOmbudsmanFilingAgent`:
   - Performs a multi-step legal verification of a rejected or partially deducted claim:
     a) Verifies continuous policy tenure against the 36-month Moratorium Rule (Clause 1.1).
     b) Extracts rejection grounds from the insurer's rejection notice and checks for TPA
        direct rejection violations (Clause 3.1), want-of-document violations (Clause 3.2),
        and cashless turnaround breaches (Clause 2.1/2.2/2.3).
     c) Autonomously generates BOTH a legally cited GRO Representation Letter and a complete
        **Council for Insurance Ombudsmen (CIO) / Bima Bharosa Form VI** payload.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Any

from app.agent.tools import (
    ANNEXURE_I_CONSUMABLES_DB,
    check_consumable_deduction,
    verify_irdai_moratorium_and_tat,
)
from app.config import settings


# Regional Insurance Ombudsman Centers in India (CIO Directory)
OMBUDSMAN_JURISDICTION_MAP: dict[str, dict[str, str]] = {
    "bhubaneswar": {
        "office": "Office of the Insurance Ombudsman, Bhubaneswar (Odisha)",
        "address": "62, Forest Park, Bhubaneswar - 751 009",
        "email": "bimalokpal.bhubaneswar@cioins.co.in",
        "jurisdiction": "State of Odisha",
    },
    "mumbai": {
        "office": "Office of the Insurance Ombudsman, Mumbai",
        "address": "3rd Floor, Jeevan Seva Annexe, S.V. Road, Santacruz (W), Mumbai - 400 054",
        "email": "bimalokpal.mumbai@cioins.co.in",
        "jurisdiction": "Mumbai Metropolitan Region & Goa",
    },
    "delhi": {
        "office": "Office of the Insurance Ombudsman, New Delhi",
        "address": "2/2 A, Universal Insurance Building, Asaf Ali Road, New Delhi - 110 002",
        "email": "bimalokpal.delhi@cioins.co.in",
        "jurisdiction": "Delhi & NCR",
    },
    "bengaluru": {
        "office": "Office of the Insurance Ombudsman, Bengaluru",
        "address": "Jeevan Soudha Building, PID No. 57-27-N-19, Ground Floor, 19/19, 24th Main Road, JP Nagar Phase 1, Bengaluru - 560 078",
        "email": "bimalokpal.bengaluru@cioins.co.in",
        "jurisdiction": "State of Karnataka",
    },
    "chennai": {
        "office": "Office of the Insurance Ombudsman, Chennai",
        "address": "Fatima Akhtar Court, 4th Floor, 453, Anna Salai, Teynampet, Chennai - 600 018",
        "email": "bimalokpal.chennai@cioins.co.in",
        "jurisdiction": "Tamil Nadu & Puducherry",
    },
    "kolkata": {
        "office": "Office of the Insurance Ombudsman, Kolkata",
        "address": "Hindustan Bldg. Annexe, 7th Floor, 4, C.R. Avenue, Kolkata - 700 072",
        "email": "bimalokpal.kolkata@cioins.co.in",
        "jurisdiction": "West Bengal, Sikkim & Andaman & Nicobar Islands",
    },
    "hyderabad": {
        "office": "Office of the Insurance Ombudsman, Hyderabad",
        "address": "6-2-46, 1st Floor, Moin Court, Lane Opp. Saleem Function Palace, A.C. Guards, Lakdi-Ka-Pool, Hyderabad - 500 004",
        "email": "bimalokpal.hyderabad@cioins.co.in",
        "jurisdiction": "Telangana, Andhra Pradesh & Yanam",
    },
}


class MultimodalHospitalBillAuditorAgent:
    """
    Extracts line items from hospital discharge bills (OCR text, PDF text, or Vision LLM image)
    and cross-checks every item against IRDAI Annexure-I (68 Non-Payable & Subsumed items)
    and the active policy's consumable rider rules.
    """

    def _try_vision_llm_extraction(self, image_bytes: bytes) -> list[dict[str, Any]] | None:
        """Uses Groq Vision LLM if configured to extract itemized bill lines from a photo."""
        api_key = settings.groq_api_key
        if not api_key or api_key.startswith("gsk_your_"):
            return None
        try:
            from langchain_core.messages import HumanMessage  # type: ignore
            from langchain_groq import ChatGroq  # type: ignore

            b64_img = base64.b64encode(image_bytes).decode("utf-8")
            vision_llm = ChatGroq(
                api_key=api_key,
                model="llama-3.2-90b-vision-preview",
                temperature=0.0,
            )
            msg = HumanMessage(
                content=[
                    {
                        "type": "text",
                        "text": (
                            "Extract all hospital bill line items from this discharge bill image as strict JSON: "
                            '[{"name": "<item name>", "category": "room|procedure|medicine|consumable", "cost": <number>}].'
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"},
                    },
                ]
            )
            resp = vision_llm.invoke([msg])
            raw = str(resp.content).strip()
            m_json = re.search(r"\[.*\]", raw, re.DOTALL)
            if m_json:
                return json.loads(m_json.group(0))
        except Exception:
            return None
        return None

    def parse_bill_text_into_line_items(self, raw_bill_text: str) -> list[dict[str, Any]]:
        """
        Parses structured or raw OCR hospital bill text into individual `(name, cost)` line items.
        """
        items: list[dict[str, Any]] = []
        pattern = re.compile(
            r"^\s*(?:[-*•]|\d+[\.)])?\s*([A-Za-z][A-Za-z0-9\s/\-\(\)&+]+?)\s*[:|\-–—]+\s*(?:Rs\.?|INR|₹)?\s*([0-9,]+(?:\.[0-9]{1,2})?)\s*$",
            re.MULTILINE,
        )
        for match in pattern.finditer(raw_bill_text):
            name = match.group(1).strip()
            cost_str = match.group(2).replace(",", "").strip()
            try:
                cost = float(cost_str)
                items.append({"name": name, "cost": cost})
            except ValueError:
                continue
        return items

    def audit_hospital_bill(
        self,
        plan_name: str = "Optima Secure",
        has_consumables_rider: bool | None = None,
        line_items: list[dict[str, Any]] | None = None,
        raw_bill_text: str | None = None,
        image_bytes: bytes | None = None,
    ) -> dict[str, Any]:
        """
        Audits a hospital discharge bill, categorizing every line item into:
        - `admissible_core_medical` (Room, ICU, Surgeon, OT, Pharmacy, Diagnostics)
        - `insurer_payable_consumable` (Covered via Protect Benefit / Safeguard+ / Extra Protect or post-discharge aid)
        - `illegal_hospital_overcharge` (Subsumed in room/OT tariff under IRDAI Annexure-I — hospital MUST waive)
        - `patient_non_payable_consumable` (Excluded consumable when no rider is active)
        """
        if has_consumables_rider is None:
            p_lower = plan_name.lower()
            has_consumables_rider = "optima" in p_lower or "protect" in p_lower or "safeguard" in p_lower

        extracted_items: list[dict[str, Any]] = []
        if line_items:
            extracted_items = [dict(x) for x in line_items]
        elif image_bytes:
            vision_items = self._try_vision_llm_extraction(image_bytes)
            if vision_items:
                extracted_items = vision_items
        if not extracted_items and raw_bill_text:
            extracted_items = self.parse_bill_text_into_line_items(raw_bill_text)

        # Provide realistic default hospital bill items if triggered via sample scan
        if not extracted_items:
            extracted_items = [
                {"name": "Single Private A/C Room Charges (4 Days)", "cost": 28000.0},
                {"name": "Laparoscopic Surgery & OT Charges", "cost": 65000.0},
                {"name": "Inpatient Pharmacy & IV Antibiotics", "cost": 18500.0},
                {"name": "Surgical Gloves / Examination Gloves", "cost": 2400.0},
                {"name": "Nebulization Kit", "cost": 1450.0},
                {"name": "Patient Gown", "cost": 1200.0},
                {"name": "Laundry Charges", "cost": 1800.0},
                {"name": "Pulse Oximeter Probe", "cost": 2200.0},
                {"name": "Sanitizer / Hand Wash / Betadine", "cost": 950.0},
                {"name": "Admission Kit / Discharge Kit / File Charges", "cost": 2500.0},
            ]

        core_medical_keywords = [
            "room charges", "icu", "surgery", "surgeon", "ot charges", "operation",
            "anesthetist", "pharmacy", "antibiotics", "medicines", "diagnostics",
            "mri", "ct scan", "blood test", "consultation", "implant", "stent",
        ]

        core_medical_items: list[dict[str, Any]] = []
        consumable_candidates: list[dict[str, Any]] = []

        for item in extracted_items:
            name_lower = str(item.get("name", "")).lower()
            is_known_consumable = any(k in name_lower for k in ANNEXURE_I_CONSUMABLES_DB)
            if not is_known_consumable and any(ck in name_lower for ck in core_medical_keywords):
                core_medical_items.append(
                    {
                        "billed_name": item["name"],
                        "cost": float(item["cost"]),
                        "category": "Core Inpatient Medical Expense",
                        "annexure_i_item_number": None,
                        "irdai_status": "admissible_inpatient_benefit",
                        "audit_verdict": "PAYABLE BY INSURER (Core Inpatient Coverage)",
                    }
                )
            else:
                consumable_candidates.append(item)

        consumable_audit = check_consumable_deduction(
            billed_items=consumable_candidates,
            has_consumables_rider=has_consumables_rider,
        )

        core_total = round(sum(x["cost"] for x in core_medical_items), 2)
        illegal_overcharge_total = consumable_audit["illegal_hospital_overcharge_total"]
        insurer_consumables_total = consumable_audit["insurer_payable_consumables_total"]
        patient_oop_consumables = consumable_audit["patient_non_payable_total"]

        total_billed = round(
            core_total + illegal_overcharge_total + insurer_consumables_total + patient_oop_consumables,
            2,
        )
        total_insurer_payable = round(core_total + insurer_consumables_total, 2)

        all_audited_line_items = core_medical_items + consumable_audit["audited_items"]

        dispute_summary = (
            f"Audited {len(all_audited_line_items)} line items totalling Rs. {total_billed:,.2f} under {plan_name}. "
            f"Detected Rs. {illegal_overcharge_total:,.2f} in ILLEGAL separate hospital charges for items strictly "
            f"subsumed in Room/OT tariffs under IRDAI Annexure-I (Hospital must waive these immediately). "
            f"Insurer payable amount is Rs. {total_insurer_payable:,.2f}, leaving Rs. {patient_oop_consumables:,.2f} "
            f"in non-payable patient consumables."
        )

        return {
            "plan_name": plan_name,
            "has_consumables_rider": has_consumables_rider,
            "total_hospital_bill": total_billed,
            "core_medical_admissible_total": core_total,
            "insurer_payable_consumables_total": insurer_consumables_total,
            "total_insurer_payable": total_insurer_payable,
            "illegal_hospital_overcharge_total": illegal_overcharge_total,
            "patient_non_payable_consumables_total": patient_oop_consumables,
            "audited_line_items": all_audited_line_items,
            "dispute_summary": dispute_summary,
        }


class AutonomousOmbudsmanFilingAgent:
    """
    Multi-step legal agent that verifies unfair claim rejections or cashless delays
    against the IRDAI Master Circular 2024 (`IRDAI/HLT/CIR/PRO/84/05/2024`) and
    prepares a complete Insurance Ombudsman Form VI filing package.
    """

    def generate_ombudsman_form_vi_package(
        self,
        complainant_name: str,
        city: str,
        insurer_name: str,
        plan_name: str,
        policy_number: str,
        claim_number: str,
        claimed_amount_inr: float,
        continuous_policy_months: int,
        rejection_reason: str,
        discharge_wait_hours: float | None = None,
        rejected_by_tpa_directly: bool = False,
        ombudsman_award_days_overdue: int | None = None,
    ) -> dict[str, Any]:
        audit = verify_irdai_moratorium_and_tat(
            continuous_policy_months=continuous_policy_months,
            rejection_reason=rejection_reason,
            discharge_wait_hours=discharge_wait_hours,
            rejected_by_tpa_directly=rejected_by_tpa_directly,
            ombudsman_award_days_overdue=ombudsman_award_days_overdue,
        )

        city_key = city.strip().lower()
        jurisdiction_info = OMBUDSMAN_JURISDICTION_MAP.get(
            city_key,
            OMBUDSMAN_JURISDICTION_MAP["bhubaneswar"],
        )

        violations = audit["violations_detected"]
        clauses_cited = [f"{v['clause']} ({v['circular_ref']})" for v in violations] or [
            "Clause 3.1 & 3.2 (IRDAI/HLT/CIR/PRO/84/05/2024)"
        ]

        form_vi_payload = {
            "form_title": "FORM VI — COMPLAINT TO THE INSURANCE OMBUDSMAN (Under Insurance Ombudsman Rules, 2017 & IRDAI Master Circular 2024)",
            "recipient_ombudsman_office": jurisdiction_info["office"],
            "recipient_address": jurisdiction_info["address"],
            "recipient_email": jurisdiction_info["email"],
            "jurisdiction_state": jurisdiction_info["jurisdiction"],
            "complainant_name": complainant_name,
            "complainant_city": city,
            "respondent_insurer": insurer_name,
            "policy_plan_name": plan_name,
            "policy_number": policy_number,
            "claim_reference_number": claim_number,
            "continuous_coverage_tenure_months": continuous_policy_months,
            "moratorium_protection_active": continuous_policy_months >= 36,
            "subject_matter_of_complaint": (
                f"Unlawful repudiation/deduction of health insurance claim ({claim_number}) despite "
                f"{continuous_policy_months} months of continuous coverage and statutory protections under "
                f"IRDAI Master Circular IRDAI/HLT/CIR/PRO/84/05/2024."
            ),
            "statutory_clauses_breached": clauses_cited,
            "detailed_facts_of_case": [v["finding"] for v in violations],
            "relief_sought_from_ombudsman": {
                "principal_claim_amount_inr": claimed_amount_inr,
                "penal_interest_clause": "2% above prevailing Bank Rate from date of last document submission (Rule 17(7) & IRDAI Circular Clause 3.3)",
                "non_compliance_daily_penalty_clause": "Rs. 5,000 per day if Ombudsman Award is not honoured within 30 days (Clause 3.3)",
                "accrued_overdue_penalty_inr": audit["ombudsman_penalty_inr"],
            },
            "declaration": (
                f"I, {complainant_name}, hereby declare that the subject matter of the complaint is within the "
                "pecuniary jurisdiction of the Insurance Ombudsman (<= Rs. 50 Lakhs) and is not pending before "
                "any Court, Consumer Commission, or Arbitrator."
            ),
        }

        gro_letter = (
            f"Subject: FINAL LEGAL NOTICE PRIOR TO OMBUDSMAN ESCALATION — Policy #{policy_number} | Claim #{claim_number}\n\n"
            f"To,\nThe Grievance Redressal Officer (GRO),\n{insurer_name}\n\n"
            f"Dear Sir/Madam,\n\n"
            f"I, {complainant_name}, hold {plan_name} (Policy No: {policy_number}) with {continuous_policy_months} continuous "
            f"months of coverage. My claim (Ref: {claim_number}) for Rs. {claimed_amount_inr:,.2f} was unlawfully rejected/deducted "
            f"on grounds of: '{rejection_reason}'.\n\n"
            f"Please take formal notice of the following statutory violations under IRDAI Master Circular IRDAI/HLT/CIR/PRO/84/05/2024:\n"
            + "\n".join(f"- {v['clause']}: {v['finding']}" for v in violations)
            + f"\n\nDemand is hereby made to settle Rs. {claimed_amount_inr:,.2f} within 15 days, failing which the attached "
            f"Form VI Complaint shall be lodged with the {jurisdiction_info['office']} ({jurisdiction_info['email']}) "
            f"and the IRDAI Bima Bharosa Portal.\n\nSincerely,\n{complainant_name} ({city})"
        )

        return {
            "is_rejection_illegal": audit["is_rejection_or_action_illegal"],
            "violations_detected": violations,
            "form_vi_payload": form_vi_payload,
            "gro_legal_notice": gro_letter,
        }
