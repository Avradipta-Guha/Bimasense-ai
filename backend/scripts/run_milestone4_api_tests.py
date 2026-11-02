"""
End-to-End FastAPI Integration & SSE Streaming Verification Suite (Milestone 4).
Tests all endpoints defined in Master Plan Section 6 plus OpenAPI schema validation.
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

from app.config import RAW_POLICIES_DIR
from app.main import app


def run_milestone4_tests() -> dict[str, Any]:
    client = TestClient(app)
    results: dict[str, Any] = {}

    # 1. Health Check & OpenAPI Schema Validation
    r_health = client.get("/health")
    assert r_health.status_code == 200
    r_openapi = client.get("/openapi.json")
    assert r_openapi.status_code == 200
    openapi_schema = r_openapi.json()
    registered_paths = list(openapi_schema.get("paths", {}).keys())
    results["openapi_and_health"] = {
        "health": r_health.json(),
        "registered_endpoints": registered_paths,
    }

    # 2. GET /api/v1/policies/list (Pre-loaded plans)
    r_list = client.get("/api/v1/policies/list", params={"user_id": "android_user_01"})
    assert r_list.status_code == 200
    list_data = r_list.json()
    assert list_data["total_count"] == 3
    results["list_preloaded_policies"] = {
        "total_count": list_data["total_count"],
        "plans": [p["plan_name"] for p in list_data["policies"]],
    }

    # 3. POST /api/v1/policies/upload (Multipart PDF Upload & User Isolation Indexing)
    sample_pdf_path = RAW_POLICIES_DIR / "HDFC_ERGO_Optima_Secure_Policy_Wording.pdf"
    with sample_pdf_path.open("rb") as f_pdf:
        r_upload = client.post(
            "/api/v1/policies/upload",
            files={"file": ("My_Personal_Optima_Policy.pdf", f_pdf, "application/pdf")},
            data={
                "insurer_name": "HDFC ERGO",
                "plan_name": "Personal Optima Schedule",
                "user_id": "android_user_01",
            },
        )
    assert r_upload.status_code == 200, f"Upload failed: {r_upload.text}"
    upload_data = r_upload.json()
    assert upload_data["status"] == "indexed"
    assert upload_data["chunks_indexed"] > 0

    # Verify uploaded policy appears in user's policy vault list
    r_list_after = client.get("/api/v1/policies/list", params={"user_id": "android_user_01"})
    assert r_list_after.json()["total_count"] == 4
    results["upload_user_policy_pdf"] = upload_data

    # 4. GET /api/v1/policies/{policy_id}/pdf (PDF byte delivery for Android PdfRenderer)
    r_pdf = client.get("/api/v1/policies/hdfc-optima-secure/pdf")
    assert r_pdf.status_code == 200
    assert r_pdf.headers["content-type"] == "application/pdf"
    assert r_pdf.content.startswith(b"%PDF")
    results["download_policy_pdf"] = {
        "status_code": r_pdf.status_code,
        "content_type": r_pdf.headers["content-type"],
        "pdf_size_bytes": len(r_pdf.content),
    }

    # 5. POST /api/v1/chat/query (Synchronous RAG Chat)
    r_chat = client.post(
        "/api/v1/chat/query",
        json={
            "query": "What is the waiting period for sugar and BP in HDFC ERGO Optima Secure?",
            "user_id": "android_user_01",
            "selected_plan": "Optima Secure",
        },
    )
    assert r_chat.status_code == 200
    chat_data = r_chat.json()
    assert chat_data["intent"] == "policy_qa"
    assert len(chat_data["citations"]) >= 1
    results["chat_query_sync"] = {
        "intent": chat_data["intent"],
        "confidence_score": chat_data["confidence_score"],
        "top_citation": chat_data["citations"][0],
    }

    # 6. POST /api/v1/chat/stream (Server-Sent Events Streaming)
    r_stream = client.post(
        "/api/v1/chat/stream",
        json={
            "query": "Does HDFC ERGO Optima Secure have any room rent capping for a 10L policy?",
            "user_id": "android_user_01",
            "selected_plan": "Optima Secure",
        },
    )
    assert r_stream.status_code == 200
    assert "text/event-stream" in r_stream.headers["content-type"]
    raw_sse_text = r_stream.text
    sse_blocks = [b.strip() for b in raw_sse_text.split("\n\n") if b.strip()]
    parsed_events = []
    for block in sse_blocks:
        lines = block.splitlines()
        if len(lines) >= 2 and lines[0].startswith("event:") and lines[1].startswith("data:"):
            ev_type = lines[0].partition(":")[2].strip()
            ev_data = json.loads(lines[1].partition(":")[2].strip())
            parsed_events.append((ev_type, ev_data))

    assert any(ev[0] == "node_status" for ev in parsed_events)
    assert any(ev[0] == "token" for ev in parsed_events)
    assert parsed_events[-1][0] == "complete"
    results["chat_stream_sse"] = {
        "total_sse_frames": len(parsed_events),
        "final_event_type": parsed_events[-1][0],
        "final_citations_count": len(parsed_events[-1][1]["citations"]),
    }

    # 7. POST /api/v1/compare (Side-by-Side Plan Comparator)
    r_compare = client.post(
        "/api/v1/compare",
        json={
            "plan_a": "Star Comprehensive",
            "plan_b": "ReAssure 2.0",
            "criteria": [
                "Room Rent & ICU Limit",
                "Maternity Waiting & Sub-Limit",
                "Restoration Benefit",
            ],
        },
    )
    assert r_compare.status_code == 200
    comp_data = r_compare.json()
    assert len(comp_data["comparison_table"]) == 3
    results["compare_endpoint"] = {
        "plan_a": comp_data["plan_a"],
        "plan_b": comp_data["plan_b"],
        "comparison_rows": comp_data["comparison_table"],
    }

    # 8. POST /api/v1/calculator/estimate (Deterministic Claim & Consumable Estimator)
    r_calc = client.post(
        "/api/v1/calculator/estimate",
        json={
            "plan_name": "Star Comprehensive",
            "sum_insured": 1_000_000.0,
            "total_bill": 150_000.0,
            "allowed_room_rent": 5_000.0,
            "actual_room_rent": 10_000.0,
            "associated_medical_expenses": 100_000.0,
            "exempt_expenses_medicines_implants_icu": 40_000.0,
            "consumables_amount": 10_000.0,
            "has_consumables_rider": False,
            "deductible": 0.0,
            "co_pay_percent": 10.0,
            "billed_consumables": [
                {"name": "Surgical Gloves", "cost": 4000.0},
                {"name": "Patient Gown", "cost": 3000.0},
                {"name": "Laundry Charges", "cost": 3000.0},
            ],
        },
    )
    assert r_calc.status_code == 200
    calc_data = r_calc.json()
    # Associated 100k * 0.5 = 50k + Exempt 40k = 90k; minus 10% co-pay (9k) = 81,000 payable
    assert calc_data["final_payable_claim_amount"] == 81000.0
    assert calc_data["consumable_audit"]["illegal_hospital_overcharge_total"] == 6000.0
    results["calculator_estimate_endpoint"] = {
        "final_payable_claim_amount": calc_data["final_payable_claim_amount"],
        "total_out_of_pocket_cost": calc_data["total_out_of_pocket_cost"],
        "illegal_hospital_overcharge_total": calc_data["consumable_audit"]["illegal_hospital_overcharge_total"],
        "citations_count": len(calc_data["policy_rule_citations"]),
    }

    # 9. POST /api/v1/grievance/verify (IRDAI Moratorium, TAT & GRO Escalation Draft)
    r_griev = client.post(
        "/api/v1/grievance/verify",
        json={
            "insurer_name": "Star Health",
            "plan_name": "Star Comprehensive",
            "continuous_policy_months": 42,
            "rejection_reason": "Rejected due to alleged non-disclosure of pre-existing hypertension",
            "discharge_wait_hours": 6.5,
            "rejected_by_tpa_directly": True,
            "ombudsman_award_days_overdue": 5,
        },
    )
    assert r_griev.status_code == 200
    griev_data = r_griev.json()
    assert griev_data["is_rejection_or_action_illegal"] is True
    assert len(griev_data["violations_detected"]) == 4
    assert griev_data["ombudsman_penalty_inr"] == 25000
    results["grievance_verify_endpoint"] = {
        "is_illegal": griev_data["is_rejection_or_action_illegal"],
        "violations_count": len(griev_data["violations_detected"]),
        "ombudsman_penalty_inr": griev_data["ombudsman_penalty_inr"],
        "gro_email_preview": griev_data["gro_escalation_email_draft"][:320] + "...",
    }

    return {
        "status": "ALL_MILESTONE_4_API_TESTS_PASSED",
        "results": results,
    }


if __name__ == "__main__":
    summary = run_milestone4_tests()
    print(json.dumps(summary, indent=2))
