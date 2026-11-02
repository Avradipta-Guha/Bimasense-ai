"""
End-to-End Verification Suite for BimaSense AI — Milestone 7 (Phase 2 Upgrade):
Autonomous Hospital Bill Auditor Agent & Insurance Ombudsman Form VI Generator.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from fastapi.testclient import TestClient
from app.main import app


def run_milestone7_tests() -> dict[str, Any]:
    client = TestClient(app)

    # 1. Test Multimodal Hospital Bill Auditor Agent (`POST /api/v1/agent/audit-bill`)
    sample_ocr_bill = """
    Single Private A/C Room Charges (4 Days) : Rs. 28,000
    Laparoscopic Surgery & OT Charges : Rs. 65,000
    Inpatient Pharmacy & IV Antibiotics : Rs. 18,500
    Surgical Gloves / Examination Gloves : Rs. 2,400
    Nebulization Kit : Rs. 1,450
    Patient Gown : Rs. 1,200
    Laundry Charges : Rs. 1,800
    Pulse Oximeter Probe : Rs. 2,200
    Sanitizer / Hand Wash / Betadine : Rs. 950
    Admission Kit / Discharge Kit / File Charges : Rs. 2,500
    """

    # 1A: Under HDFC ERGO Optima Secure (Protect Benefit rider active -> Gloves & Nebulizer covered)
    r_audit_optima = client.post(
        "/api/v1/agent/audit-bill",
        json={
            "plan_name": "Optima Secure",
            "raw_bill_text": sample_ocr_bill,
        },
    )
    assert r_audit_optima.status_code == 200
    optima_audit = r_audit_optima.json()
    assert optima_audit["total_hospital_bill"] == 124000.0
    assert optima_audit["illegal_hospital_overcharge_total"] == 8650.0
    assert optima_audit["insurer_payable_consumables_total"] == 3850.0
    assert optima_audit["total_insurer_payable"] == 115350.0
    assert optima_audit["patient_non_payable_consumables_total"] == 0.0

    # 1B: Under Star Health Comprehensive without rider (Gloves & Nebulizer non-payable by insurer)
    r_audit_star = client.post(
        "/api/v1/agent/audit-bill",
        json={
            "plan_name": "Star Comprehensive",
            "has_consumables_rider": False,
            "raw_bill_text": sample_ocr_bill,
        },
    )
    assert r_audit_star.status_code == 200
    star_audit = r_audit_star.json()
    assert star_audit["illegal_hospital_overcharge_total"] == 8650.0
    assert star_audit["patient_non_payable_consumables_total"] == 3850.0
    assert star_audit["total_insurer_payable"] == 111500.0

    # 2. Test Autonomous Insurance Ombudsman Form VI Filing Agent (`POST /api/v1/agent/ombudsman-form6`)
    r_form6 = client.post(
        "/api/v1/agent/ombudsman-form6",
        json={
            "complainant_name": "Aarav Mohanty",
            "city": "Bhubaneswar",
            "insurer_name": "Star Health and Allied Insurance Co. Ltd.",
            "plan_name": "Star Comprehensive",
            "policy_number": "P/191100/01/2022/009482",
            "claim_number": "CLI/2026/191100/0482910",
            "claimed_amount_inr": 185000.0,
            "continuous_policy_months": 48,
            "rejection_reason": "Claim rejected by TPA citing non-disclosure of hypertension 4 years ago",
            "discharge_wait_hours": 6.5,
            "rejected_by_tpa_directly": True,
            "ombudsman_award_days_overdue": 4,
        },
    )
    assert r_form6.status_code == 200
    form6_data = r_form6.json()
    assert form6_data["is_rejection_illegal"] is True
    assert len(form6_data["violations_detected"]) == 4
    assert "Bhubaneswar" in form6_data["form_vi_payload"]["recipient_ombudsman_office"]
    assert form6_data["form_vi_payload"]["moratorium_protection_active"] is True
    assert form6_data["form_vi_payload"]["relief_sought_from_ombudsman"]["accrued_overdue_penalty_inr"] == 20000

    return {
        "status": "ALL_MILESTONE_7_AGENT_TESTS_PASSED",
        "hospital_bill_audit_optima_secure": {
            "total_hospital_bill": optima_audit["total_hospital_bill"],
            "total_insurer_payable": optima_audit["total_insurer_payable"],
            "illegal_hospital_overcharge_waived": optima_audit["illegal_hospital_overcharge_total"],
            "patient_non_payable_consumables": optima_audit["patient_non_payable_consumables_total"],
            "dispute_summary": optima_audit["dispute_summary"],
        },
        "hospital_bill_audit_star_comprehensive": {
            "total_hospital_bill": star_audit["total_hospital_bill"],
            "total_insurer_payable": star_audit["total_insurer_payable"],
            "illegal_hospital_overcharge_waived": star_audit["illegal_hospital_overcharge_total"],
            "patient_non_payable_consumables": star_audit["patient_non_payable_consumables_total"],
        },
        "ombudsman_form_vi_dossier": form6_data["form_vi_payload"],
    }


if __name__ == "__main__":
    summary = run_milestone7_tests()
    print(json.dumps(summary, indent=2))
