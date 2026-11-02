"""
End-to-End Verification Suite for BimaSense AI — Milestone 3:
LangGraph 6-Node Orchestrator & Deterministic Tools.

Verifies:
1. Pillar 1 (`policy_qa` + Annexure-I Consumables Audit)
2. Pillar 2 (`plan_comparison` with structured `comparison_table` matrix)
3. Pillar 3 (`claim_calculation` — both Natural Language & Structured Android inputs)
4. Pillar 4 (`regulatory_grievance` — 36-Month Moratorium, 3-Hour Discharge TAT, TPA Ban & GRO Notice)
5. Corrective RAG Guardrail (`< 0.35` threshold halting hallucination on out-of-scope queries)
6. Server-Sent Events (SSE) token streaming (`stream_sse_events`)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.agent.graph import build_bimasense_graph
from app.config import LOCAL_INDEX_PATH
from scripts.run_milestone1_pipeline import run_milestone1_ingestion


def run_milestone3_tests() -> dict[str, Any]:
    if not LOCAL_INDEX_PATH.exists():
        run_milestone1_ingestion()

    graph = build_bimasense_graph()
    results: dict[str, Any] = {}

    # --- Test 1: Pillar 1 (Citation-Backed Policy Q&A + Consumables Check) ---
    s1 = graph.invoke(
        {
            "user_query": "What is the waiting period for sugar and BP in HDFC ERGO Optima Secure, and are surgical gloves and patient gown covered?",
            "selected_plan": "Optima Secure",
        }
    )
    assert s1["intent"] == "policy_qa", f"Expected policy_qa, got {s1['intent']}"
    assert s1["is_relevant"] is True
    assert len(s1["citations"]) >= 1
    assert "consumable_audit" in s1["tool_outputs"]
    results["test_1_policy_qa"] = {
        "intent": s1["intent"],
        "node_trace": s1["node_trace"],
        "confidence_score": s1["confidence_score"],
        "top_citation": s1["citations"][0].model_dump(),
        "consumable_audit_summary": {
            "insurer_payable": s1["tool_outputs"]["consumable_audit"]["insurer_payable_consumables_total"],
            "illegal_hospital_overcharge": s1["tool_outputs"]["consumable_audit"]["illegal_hospital_overcharge_total"],
        },
        "answer_preview": s1["answer_markdown"][:350] + "...",
    }

    # --- Test 2: Pillar 2 (Multi-Insurer Side-by-Side Plan Comparator) ---
    s2 = graph.invoke(
        {
            "user_query": "Compare Star Health Comprehensive and Niva Bupa ReAssure 2.0 on maternity waiting period and restoration benefits.",
        }
    )
    assert s2["intent"] == "plan_comparison", f"Expected plan_comparison, got {s2['intent']}"
    assert s2["comparison_table"] is not None and len(s2["comparison_table"]) >= 4
    results["test_2_plan_comparison"] = {
        "intent": s2["intent"],
        "target_plans": s2["target_plans"],
        "node_trace": s2["node_trace"],
        "comparison_rows_count": len(s2["comparison_table"]),
        "sample_comparison_rows": [r.model_dump() for r in s2["comparison_table"][:3]],
    }

    # --- Test 3A: Pillar 3 (Deterministic Claim Calculator — Natural Language with Exempt Items) ---
    s3a = graph.invoke(
        {
            "user_query": (
                "Under Star Health Comprehensive, if Eligible Room Rent is Rs. 6,000/day, "
                "Actual Room Rent chosen is Rs. 9,000/day, Surgeon + OT charges are Rs. 90,000, "
                "and Pharmacy/Medicines cost Rs. 30,000, how much will the insurer pay?"
            ),
        }
    )
    assert s3a["intent"] == "claim_calculation"
    calc_3a = s3a["tool_outputs"]["claim_calculation"]
    assert calc_3a["final_payable_claim_amount"] == 90000.0, f"Expected 90000.0, got {calc_3a['final_payable_claim_amount']}"
    assert calc_3a["proportionate_deduction_amount"] == 30000.0
    results["test_3a_claim_math_nl"] = {
        "intent": s3a["intent"],
        "node_trace": s3a["node_trace"],
        "calculation_result": calc_3a,
    }

    # --- Test 3B: Pillar 3 (Deterministic Claim Calculator — Android UI Slider Payload) ---
    s3b = graph.invoke(
        {
            "user_query": "Calculate my claim payout and out-of-pocket deduction.",
            "claim_input_params": {
                "plan_name": "Star Comprehensive",
                "sum_insured": 1_000_000.0,
                "total_bill": 100_000.0,
                "allowed_room_rent": 5_000.0,
                "actual_room_rent": 10_000.0,
                "deductible": 10_000.0,
                "co_pay_percent": 0.0,
            },
        }
    )
    calc_3b = s3b["tool_outputs"]["claim_calculation"]
    assert calc_3b["final_payable_claim_amount"] == 40000.0, f"Expected 40000.0, got {calc_3b['final_payable_claim_amount']}"
    assert calc_3b["total_out_of_pocket_cost"] == 60000.0
    results["test_3b_claim_math_structured"] = {
        "final_payable_claim_amount": calc_3b["final_payable_claim_amount"],
        "total_out_of_pocket_cost": calc_3b["total_out_of_pocket_cost"],
        "proportionate_multiplier": calc_3b["proportionate_multiplier"],
    }

    # --- Test 4: Pillar 4 (IRDAI Rights, Moratorium & Cashless Discharge TAT Assistant) ---
    s4 = graph.invoke(
        {
            "user_query": (
                "My insurer rejected my claim after 4 years of continuous policy renewals citing "
                "non-disclosure of hypertension, and also delayed cashless discharge approval by 7 hours. "
                "Is this legal under IRDAI rules?"
            ),
        }
    )
    assert s4["intent"] == "regulatory_grievance"
    irdai_out = s4["tool_outputs"]["irdai_verification"]
    assert irdai_out["is_rejection_or_action_illegal"] is True
    assert len(irdai_out["violations_detected"]) >= 2
    results["test_4_regulatory_grievance"] = {
        "intent": s4["intent"],
        "node_trace": s4["node_trace"],
        "is_illegal": irdai_out["is_rejection_or_action_illegal"],
        "violations_detected": irdai_out["violations_detected"],
        "answer_preview": s4["answer_markdown"][:420] + "...",
    }

    # --- Test 5: Corrective RAG Guardrail (< 0.35 Threshold on Out-of-Scope Query) ---
    s5 = graph.invoke(
        {
            "user_query": "Does this policy pay for robotic hair transplant and dental veneers in Zurich?",
        }
    )
    assert s5["is_relevant"] is False, "Expected Corrective RAG guardrail to trigger (is_relevant=False)"
    assert s5["confidence_score"] < 0.35
    assert len(s5["citations"]) == 0
    results["test_5_corrective_rag_guardrail"] = {
        "is_relevant": s5["is_relevant"],
        "confidence_score": s5["confidence_score"],
        "node_trace": s5["node_trace"],
        "guardrail_response": s5["answer_markdown"],
    }

    # --- Test 6: SSE Event Streaming (`stream_sse_events`) ---
    sse_events = list(
        graph.stream_sse_events(
            {"user_query": "Does HDFC ERGO Optima Secure have any room rent capping for a 10L policy?"}
        )
    )
    event_types = [e["event"] for e in sse_events]
    assert "node_status" in event_types
    assert "token" in event_types
    assert event_types[-1] == "complete"
    results["test_6_sse_streaming"] = {
        "total_sse_events": len(sse_events),
        "node_status_events": sum(1 for e in sse_events if e["event"] == "node_status"),
        "token_events": sum(1 for e in sse_events if e["event"] == "token"),
        "final_event_type": event_types[-1],
    }

    return {
        "status": "ALL_MILESTONE_3_TESTS_PASSED",
        "graph_engine": graph.engine_mode,
        "results": results,
    }


if __name__ == "__main__":
    summary = run_milestone3_tests()
    print(json.dumps(summary, indent=2))
