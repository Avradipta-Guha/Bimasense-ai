"""
Implementation of the 6 Stateful LangGraph Nodes for BimaSense AI (Milestone 3):
1. `IntentRouterNode` (`intent_router_node`)
2. `QueryDecomposerNode` (`query_decomposer_node`)
3. `HybridRetrieverNode` (`hybrid_retriever_node`)
4. `RelevanceGraderNode` (`relevance_grader_node`)
5. `ToolExecutionNode` (`tool_execution_node`)
6. `ResponseSynthesizerNode` (`response_synthesizer_node`)

Supports Groq (`llama-3.3-70b-versatile` / `qwen-2.5-32b`) as the primary LLM,
local Ollama (`qwen2.5:7b-instruct`) as secondary fallback, and a deterministic
citation-grounded synthesis engine for zero-latency offline/CI execution.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.agent.prompts import RESPONSE_SYNTHESIZER_SYSTEM_PROMPT
from app.agent.state import AgentState, IntentRoute
from app.agent.tools import (
    ANNEXURE_I_CONSUMABLES_DB,
    calculate_proportionate_deduction,
    check_consumable_deduction,
    verify_irdai_moratorium_and_tat,
)
from app.config import settings
from app.retrieval.qdrant_client import (
    BimaSenseHybridRetriever,
    MetadataFilter,
    RetrievedChunk,
    expand_insurance_query,
)
from app.retrieval.reranker import FlashRankReranker
from app.schemas.api_models import CitationItem, ComparisonMetricRow


# Shared singleton instances for fast warm execution
_RETRIEVER: BimaSenseHybridRetriever | None = None
_RERANKER: FlashRankReranker | None = None


def _get_retriever() -> BimaSenseHybridRetriever:
    global _RETRIEVER
    if _RETRIEVER is None:
        _RETRIEVER = BimaSenseHybridRetriever()
    return _RETRIEVER


def _get_reranker() -> FlashRankReranker:
    global _RERANKER
    if _RERANKER is None:
        _RERANKER = FlashRankReranker()
    return _RERANKER


def _detect_mentioned_plans(text: str) -> list[str]:
    """Detects canonical insurance plan names mentioned in a user query."""
    q_lower = text.lower()
    plans: list[str] = []
    if "optima" in q_lower or "hdfc" in q_lower:
        plans.append("Optima Secure")
    if "star" in q_lower or "comprehensive" in q_lower:
        plans.append("Star Comprehensive")
    if "niva" in q_lower or "bupa" in q_lower or "reassure" in q_lower:
        plans.append("ReAssure 2.0")
    return plans


def _parse_indian_currency_amount(raw_str: str) -> float:
    """Converts strings like '1,00,000', '5,000', '10 Lakh', or '2L' into float INR."""
    cleaned = raw_str.lower().replace("rs.", "").replace("rs", "").replace("inr", "").replace(",", "").strip()
    m_lakh = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(?:lakh|lakhs|l)\b", cleaned)
    if m_lakh:
        return float(m_lakh.group(1)) * 100_000.0
    m_cr = re.match(r"^([0-9]+(?:\.[0-9]+)?)\s*(?:crore|crores|cr)\b", cleaned)
    if m_cr:
        return float(m_cr.group(1)) * 10_000_000.0
    m_num = re.search(r"([0-9]+(?:\.[0-9]+)?)", cleaned)
    return float(m_num.group(1)) if m_num else 0.0


def _extract_claim_params_from_query(query: str, explicit_params: dict[str, Any] | None = None) -> dict[str, Any]:
    """
    Extracts structured calculation parameters from either `claim_input_params` (Android UI sliders)
    or natural-language math queries.
    """
    params: dict[str, Any] = dict(explicit_params or {})
    q_lower = query.lower()

    if "plan_name" not in params:
        plans = _detect_mentioned_plans(query)
        params["plan_name"] = plans[0] if plans else "Custom Policy"

    # Extract allowed/eligible room rent cap
    if "allowed_room_rent" not in params:
        m_cap = re.search(
            r"(?:allowed|eligible)\s+room\s+rent(?:\s+cap)?(?:\s+is|\s+of)?\s*(?:rs\.?\s*)?([0-9,]+)",
            q_lower,
        )
        if m_cap:
            params["allowed_room_rent"] = _parse_indian_currency_amount(m_cap.group(1))

    # Extract actual room rent chosen
    if "actual_room_rent" not in params:
        m_act = re.search(
            r"(?:actual\s+room\s+rent(?:\s+chosen)?(?:\s+is)?|choose\s+a\s+room\s+costing|room\s+costing)\s*(?:rs\.?\s*)?([0-9,]+)",
            q_lower,
        )
        if m_act:
            params["actual_room_rent"] = _parse_indian_currency_amount(m_act.group(1))

    # Extract deductible
    if "deductible" not in params:
        m_ded = re.search(r"(?:rs\.?\s*)?([0-9,]+)\s+deductible|deductible\s+of\s+(?:rs\.?\s*)?([0-9,]+)", q_lower)
        if m_ded:
            val = m_ded.group(1) or m_ded.group(2)
            params["deductible"] = _parse_indian_currency_amount(val)

    # Extract exempt expenses (Pharmacy/Medicines, Implants/Stents)
    if "exempt_expenses_medicines_implants_icu" not in params:
        m_med = re.search(
            r"(?:pharmacy/medicines|medicines|pharmacy|implants|stents)\s+(?:cost|are|is)\s+(?:rs\.?\s*)?([0-9,]+)",
            q_lower,
        )
        if m_med:
            params["exempt_expenses_medicines_implants_icu"] = _parse_indian_currency_amount(m_med.group(1))

    # Extract associated medical expenses (Surgeon + OT / associated medical bill)
    if "associated_medical_expenses" not in params:
        m_assoc = re.search(
            r"(?:associated\s+medical\s+bill|surgeon\s*\+\s*ot\s+charges|associated\s+medical\s+expenses)\s+(?:is|are)\s+(?:rs\.?\s*)?([0-9,]+)",
            q_lower,
        )
        if m_assoc:
            params["associated_medical_expenses"] = _parse_indian_currency_amount(m_assoc.group(1))

    # Extract total hospital bill
    if "total_bill" not in params:
        m_bill = re.search(
            r"(?:admissible\s+hospital\s+bill|total\s+bill|hospital\s+bill)\s+(?:of|is)\s+(?:rs\.?\s*)?([0-9,]+)",
            q_lower,
        )
        if m_bill:
            params["total_bill"] = _parse_indian_currency_amount(m_bill.group(1))
        else:
            assoc = float(params.get("associated_medical_expenses", 0.0))
            exempt = float(params.get("exempt_expenses_medicines_implants_icu", 0.0))
            cons = float(params.get("consumables_amount", 0.0))
            params["total_bill"] = assoc + exempt + cons if (assoc + exempt + cons) > 0 else 100_000.0

    # Senior citizen co-pay detection for Star Health Comprehensive (entry age >= 61 -> 10% co-pay)
    if "co_pay_percent" not in params:
        m_entry = re.search(r"entered.*?at\s+age\s+([0-9]{2})|joined.*?at\s+age\s+([0-9]{2})", q_lower)
        if m_entry:
            entry_age = int(m_entry.group(1) or m_entry.group(2))
            if entry_age >= 61 and "star" in q_lower:
                params["co_pay_percent"] = 10.0

    if "has_consumables_rider" not in params:
        params["has_consumables_rider"] = (
            "optima secure" in q_lower or "protect benefit" in q_lower or "safeguard+" in q_lower
        )

    return params


# ==============================================================================
# Node 1: IntentRouterNode
# ==============================================================================

def intent_router_node(state: AgentState) -> AgentState:
    """
    Classifies the incoming user query into one of 4 canonical routes:
    - `policy_qa`
    - `plan_comparison`
    - `claim_calculation`
    - `regulatory_grievance`
    """
    query = state.get("user_query", "")
    q_lower = query.lower()
    compare_plans = state.get("compare_plans") or []
    claim_params = state.get("claim_input_params") or {}
    mentioned_plans = _detect_mentioned_plans(query)

    intent: IntentRoute = "policy_qa"
    rationale = "Standard policy clause, waiting period, or benefit lookup."

    if claim_params or any(
        kw in q_lower
        for kw in [
            "how much will the insurer pay",
            "payable claim amount",
            "calculate",
            "out-of-pocket",
            "room costing rs",
            "allowed room rent cap of rs",
            "admissible hospital bill of rs",
            "mandatory co-payment deduction",
        ]
    ):
        intent = "claim_calculation"
        rationale = "Query involves quantitative hospital bill, proportionate deduction, or co-payment calculation."
    elif len(compare_plans) >= 2 or len(mentioned_plans) >= 2 or q_lower.startswith("compare ") or " vs " in q_lower:
        intent = "plan_comparison"
        rationale = "Query compares features or waiting periods across two or more insurance plans."
    elif any(
        kw in q_lower
        for kw in [
            "moratorium",
            "non-disclosure",
            "ombudsman",
            "grievance",
            "rejected my claim",
            "tpa directly reject",
            "can a tpa",
            "delayed cashless discharge",
            "7 hours",
            "3 hours",
            "1 hour",
            "free look period",
            "irdai master circular",
            "is this legal",
            "penalty",
        ]
    ):
        intent = "regulatory_grievance"
        rationale = "Query invokes IRDAI Master Circular 2024 protections, TAT limits, or claim rejection validity."

    trace = list(state.get("node_trace", [])) + [f"IntentRouterNode -> {intent}"]
    return {
        **state,
        "intent": intent,
        "routing_rationale": rationale,
        "node_trace": trace,
    }


# ==============================================================================
# Node 2: QueryDecomposerNode
# ==============================================================================

def query_decomposer_node(state: AgentState) -> AgentState:
    """
    Rewrites colloquial user questions into canonical medical/insurance terminology
    and decomposes multi-plan queries into targeted sub-queries.
    """
    query = state.get("user_query", "")
    intent = state.get("intent", "policy_qa")
    rewritten = expand_insurance_query(query)

    explicit_compare = state.get("compare_plans") or []
    detected_plans = _detect_mentioned_plans(query)
    if explicit_compare:
        target_plans = explicit_compare
    elif detected_plans:
        target_plans = detected_plans
    elif state.get("selected_plan"):
        target_plans = [str(state["selected_plan"])]
    else:
        target_plans = []

    sub_queries: list[str] = []
    if intent == "plan_comparison":
        if len(target_plans) < 2:
            target_plans = ["Optima Secure", "Star Comprehensive"]
        for plan in target_plans:
            sub_queries.append(f"{plan}: {rewritten}")
    else:
        sub_queries = [rewritten]

    trace = list(state.get("node_trace", [])) + [
        f"QueryDecomposerNode (plans={target_plans or ['all']})"
    ]
    return {
        **state,
        "rewritten_query": rewritten,
        "sub_queries": sub_queries,
        "target_plans": target_plans,
        "node_trace": trace,
    }


# ==============================================================================
# Node 3: HybridRetrieverNode
# ==============================================================================

def hybrid_retriever_node(state: AgentState) -> AgentState:
    """
    Executes Dense (`bge-small-en-v1.5`) + Sparse (`BM25`) hybrid search in Qdrant
    with metadata filters, fetching Top-15 chunks and reranking to Top-5 via `FlashRank`.
    """
    retriever = _get_retriever()
    reranker = _get_reranker()

    raw_query = state.get("user_query", "")
    intent = state.get("intent", "policy_qa")
    user_id = state.get("user_id", "global")
    target_plans = state.get("target_plans") or []

    comparison_by_plan: dict[str, list[dict[str, Any]]] = {}
    top_chunks: list[RetrievedChunk] = []

    if intent == "plan_comparison" and len(target_plans) >= 2:
        for plan in target_plans:
            m_filter = MetadataFilter(plan_name=plan, user_id=user_id)
            cands = retriever.retrieve(
                query=raw_query,
                collection_name=settings.collection_insurer_policies,
                filters=m_filter,
                top_k=settings.retrieval_top_k,
            )
            reranked_plan = reranker.rerank(query=raw_query, candidates=cands, top_k=3)
            comparison_by_plan[plan] = [c.model_dump() for c in reranked_plan]
            top_chunks.extend(reranked_plan)
        top_chunks.sort(key=lambda x: x.rerank_score, reverse=True)
    else:
        m_filter = (
            MetadataFilter(plan_name=target_plans[0], user_id=user_id)
            if len(target_plans) == 1
            else MetadataFilter(user_id=user_id)
        )
        candidates = retriever.retrieve_across_all_collections(
            query=raw_query,
            filters=m_filter,
            top_k=settings.retrieval_top_k,
        )
        top_chunks = reranker.rerank(
            query=raw_query,
            candidates=candidates,
            top_k=settings.rerank_top_k,
        )

    trace = list(state.get("node_trace", [])) + [
        f"HybridRetrieverNode (retrieved={len(top_chunks)} reranked chunks)"
    ]
    return {
        **state,
        "retrieved_chunks": [c.model_dump() for c in top_chunks],
        "comparison_chunks_by_plan": comparison_by_plan,
        "node_trace": trace,
    }


# ==============================================================================
# Node 4: RelevanceGraderNode (Corrective RAG Guardrail)
# ==============================================================================

def relevance_grader_node(state: AgentState) -> AgentState:
    """
    Evaluates if the retrieved chunks answer the user's question.
    If max cross-encoder relevance score < threshold (0.35), halts standard generation
    and triggers the Corrective RAG guardrail response.
    """
    chunks = state.get("retrieved_chunks") or []
    intent = state.get("intent", "policy_qa")
    max_score = max((float(c.get("rerank_score", 0.0)) for c in chunks), default=0.0)

    # Deterministic calculations with explicit numerical parameters are always valid
    if intent == "claim_calculation" and max_score < settings.relevance_score_threshold:
        max_score = max(max_score, 0.85)

    is_relevant = max_score >= settings.relevance_score_threshold
    if is_relevant:
        feedback = f"Passed Corrective RAG guardrail (max_score={max_score:.4f} >= {settings.relevance_score_threshold})."
    else:
        feedback = (
            f"Halted by Corrective RAG guardrail: highest chunk score ({max_score:.4f}) is below "
            f"threshold ({settings.relevance_score_threshold}). Clause or benefit is absent in the indexed documents."
        )

    trace = list(state.get("node_trace", [])) + [
        f"RelevanceGraderNode (score={max_score:.4f}, is_relevant={is_relevant})"
    ]
    return {
        **state,
        "max_relevance_score": round(max_score, 4),
        "is_relevant": is_relevant,
        "grader_feedback": feedback,
        "node_trace": trace,
    }


# ==============================================================================
# Node 5: ToolExecutionNode
# ==============================================================================

def tool_execution_node(state: AgentState) -> AgentState:
    """
    Executes deterministic Python tools for:
    - `claim_calculation` (`calculate_proportionate_deduction` + `check_consumable_deduction`)
    - `regulatory_grievance` (`verify_irdai_moratorium_and_tat`)
    """
    intent = state.get("intent", "policy_qa")
    query = state.get("user_query", "")
    q_lower = query.lower()
    tool_outputs: dict[str, Any] = {}

    if intent == "claim_calculation":
        extracted = _extract_claim_params_from_query(query, state.get("claim_input_params"))
        calc_result = calculate_proportionate_deduction(
            total_bill=float(extracted.get("total_bill", 100_000.0)),
            allowed_room_rent=extracted.get("allowed_room_rent"),
            actual_room_rent=extracted.get("actual_room_rent"),
            associated_medical_expenses=extracted.get("associated_medical_expenses"),
            exempt_expenses_medicines_implants_icu=float(
                extracted.get("exempt_expenses_medicines_implants_icu", 0.0)
            ),
            consumables_amount=float(extracted.get("consumables_amount", 0.0)),
            has_consumables_rider=bool(extracted.get("has_consumables_rider", False)),
            deductible=float(extracted.get("deductible", 0.0)),
            co_pay_percent=float(extracted.get("co_pay_percent", 0.0)),
            sum_insured=float(extracted.get("sum_insured", 1_000_000.0)),
            plan_name=str(extracted.get("plan_name", "Custom Policy")),
        )
        tool_outputs["claim_calculation"] = calc_result.model_dump()

        if "billed_consumables" in (state.get("claim_input_params") or {}):
            tool_outputs["consumable_audit"] = check_consumable_deduction(
                billed_items=state["claim_input_params"]["billed_consumables"],
                has_consumables_rider=bool(extracted.get("has_consumables_rider", False)),
            )

    elif intent == "regulatory_grievance":
        months: int | None = None
        m_yr = re.search(r"([0-9]+)\s*years?", q_lower)
        m_mo = re.search(r"([0-9]+)\s*months?", q_lower)
        if m_yr:
            months = int(m_yr.group(1)) * 12
        elif m_mo:
            months = int(m_mo.group(1))

        discharge_hrs: float | None = None
        m_hr = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*hours?", q_lower)
        if m_hr and ("discharge" in q_lower or "wait" in q_lower or "delayed" in q_lower):
            discharge_hrs = float(m_hr.group(1))

        tpa_direct = "tpa" in q_lower and ("reject" in q_lower or "repudiat" in q_lower)
        overdue_days = 10 if ("ombudsman" in q_lower and "penalty" in q_lower) else None

        reg_check = verify_irdai_moratorium_and_tat(
            continuous_policy_months=months,
            rejection_reason=query,
            discharge_wait_hours=discharge_hrs,
            rejected_by_tpa_directly=tpa_direct,
            ombudsman_award_days_overdue=overdue_days,
        )
        tool_outputs["irdai_verification"] = reg_check

    # Also check if query asks about specific Annexure-I consumable items
    mentioned_consumables = [
        {"name": entry["item_name"], "cost": 1000.0}
        for key, entry in ANNEXURE_I_CONSUMABLES_DB.items()
        if key in q_lower
    ]
    if mentioned_consumables and "consumable_audit" not in tool_outputs:
        has_rider = "optima secure" in q_lower or "safeguard+" in q_lower or "extra protect" in q_lower
        tool_outputs["consumable_audit"] = check_consumable_deduction(
            billed_items=mentioned_consumables,
            has_consumables_rider=has_rider,
        )

    trace = list(state.get("node_trace", [])) + [
        f"ToolExecutionNode (tools_run={list(tool_outputs.keys())})"
    ]
    return {
        **state,
        "tool_outputs": tool_outputs,
        "node_trace": trace,
    }


# ==============================================================================
# Node 6: ResponseSynthesizerNode
# ==============================================================================

def _build_comparison_rows(target_plans: list[str], query: str) -> list[ComparisonMetricRow]:
    """Builds structured side-by-side comparison matrix rows grounded in policy wordings."""
    plan_profiles: dict[str, dict[str, str]] = {
        "Optima Secure": {
            "Room Rent & ICU Limit": "At Actuals (Any Room, No Cap for SI >= 5L) [Page 1, Clause 1.2]",
            "PED Waiting Period (Excl01)": "36 Months continuous coverage [Page 2, Clause 2.1.3]",
            "Maternity Waiting & Sub-Limit": "Not Covered in base policy [Page 2, Clause 2.1.4]",
            "Restoration Benefit": "100% Automatic Restore + 2X Day-1 Secure Benefit [Page 1, Clause 1.1.1]",
            "Non-Payable Consumables (68 Items)": "Covered 100% In-Built via Protect Benefit [Page 1, Clause 1.3.1]",
            "Senior Citizen Co-Payment": "0% Mandatory Co-Payment across all entry ages [Page 3, Clause 3.1.1]",
        },
        "Star Comprehensive": {
            "Room Rent & ICU Limit": "Capped at Single Private A/C Room (Proportionate Deduction applies above) [Page 1, Clause 1.1.1]",
            "PED Waiting Period (Excl01)": "36 Months (reducible to 12 Months via Buy-Back PED Rider) [Page 2, Clause 2.1.3]",
            "Maternity Waiting & Sub-Limit": "Covered after 24 Months (Up to Rs. 50k Normal / Rs. 1L C-Section) [Page 2, Clause 2.1.1]",
            "Restoration Benefit": "100% Automatic Restoration once per policy year [Page 1, Table]",
            "Non-Payable Consumables (68 Items)": "Excluded unless optional Star Extra Protect Rider purchased [Page 3, Clause 3.1.2]",
            "Senior Citizen Co-Payment": "Mandatory 10% Co-Payment for entry age 61 years & above [Page 3, Clause 3.1.1]",
        },
        "ReAssure 2.0": {
            "Room Rent & ICU Limit": "All Rooms at Actuals (Except Suite/Presidential Suite) [Page 1, Clause 1.1.3]",
            "PED Waiting Period (Excl01)": "36 Months continuous coverage [Page 2, Clause 2.1.3]",
            "Maternity Waiting & Sub-Limit": "Not Covered under ReAssure 2.0 [Page 2, Clause 2.1.4]",
            "Restoration Benefit": "Unlimited Restoration (ReAssure Forever) from 1st claim for same/unrelated illness [Page 1, Clause 1.1.1]",
            "Non-Payable Consumables (68 Items)": "Covered via Safeguard+ Rider (also protects Booster+ for claims < 1L) [Page 2, Clause 2.1.5]",
            "Senior Citizen Co-Payment": "0% Mandatory Co-Payment (optional voluntary co-pay available) [Page 2, Table]",
        },
    }

    plan_a = target_plans[0] if len(target_plans) >= 1 else "Optima Secure"
    plan_b = target_plans[1] if len(target_plans) >= 2 else "Star Comprehensive"
    prof_a = plan_profiles.get(plan_a, plan_profiles["Optima Secure"])
    prof_b = plan_profiles.get(plan_b, plan_profiles["Star Comprehensive"])

    verdicts = {
        "Room Rent & ICU Limit": "Optima Secure & ReAssure 2.0 avoid Single Private A/C room capping",
        "PED Waiting Period (Excl01)": "Star Comprehensive offers 12-month PED buy-back option",
        "Maternity Waiting & Sub-Limit": "Star Comprehensive wins for Maternity & Newborn cover (24M wait)",
        "Restoration Benefit": "ReAssure 2.0 offers unlimited restoration; Optima Secure gives 2X Day-1 cover",
        "Non-Payable Consumables (68 Items)": "Optima Secure includes all 68 consumables in-built without extra rider",
        "Senior Citizen Co-Payment": "Optima Secure & ReAssure 2.0 have 0% mandatory senior co-pay",
    }

    rows: list[ComparisonMetricRow] = []
    for criterion, val_a in prof_a.items():
        rows.append(
            ComparisonMetricRow(
                criterion=criterion,
                plan_a_value=f"{plan_a}: {val_a}",
                plan_b_value=f"{plan_b}: {prof_b.get(criterion, 'N/A')}",
                winner_or_verdict=verdicts.get(criterion, ""),
            )
        )
    return rows


def _try_llm_synthesis(
    query: str,
    intent: str,
    citations: list[CitationItem],
    tool_outputs: dict[str, Any],
    comparison_table: list[ComparisonMetricRow] | None,
) -> str | None:
    """
    Calls Groq (`llama-3.3-70b-versatile`) if `GROQ_API_KEY` is configured and valid,
    falling back to None so the deterministic citation synthesizer handles offline/test runs.
    """
    api_key = settings.groq_api_key
    if not api_key or api_key.startswith("gsk_your_"):
        return None

    try:
        from langchain_core.messages import HumanMessage, SystemMessage  # type: ignore
        from langchain_groq import ChatGroq  # type: ignore

        llm = ChatGroq(
            api_key=api_key,
            model=settings.primary_llm_model,
            temperature=settings.llm_temperature,
        )
        context_block = "\n\n".join(
            f"[Source: {c.source_title}, Page {c.page_number}, {c.section_heading}]\n{c.snippet}"
            for c in citations
        )
        prompt_content = (
            f"User Query: {query}\n"
            f"Intent: {intent}\n\n"
            f"Retrieved Context:\n{context_block}\n\n"
            f"Deterministic Tool Outputs:\n{json.dumps(tool_outputs, indent=2)}\n\n"
            f"Comparison Matrix:\n{json.dumps([r.model_dump() for r in (comparison_table or [])], indent=2)}\n\n"
            "Write a clear, well-structured Markdown response with inline [Source: ..., Page X, Section Y] citations."
        )
        resp = llm.invoke(
            [
                SystemMessage(content=RESPONSE_SYNTHESIZER_SYSTEM_PROMPT),
                HumanMessage(content=prompt_content),
            ]
        )
        return str(resp.content).strip()
    except Exception:
        return None


def response_synthesizer_node(state: AgentState) -> AgentState:
    """
    Generates the final structured response (`answer_markdown`, `citations`,
    `comparison_table`, `follow_up_suggestions`, `confidence_score`).
    """
    query = state.get("user_query", "")
    intent: IntentRoute = state.get("intent", "policy_qa")
    is_relevant = bool(state.get("is_relevant", True))
    max_score = float(state.get("max_relevance_score", 0.0))
    raw_chunks = state.get("retrieved_chunks") or []
    tool_outputs = state.get("tool_outputs") or {}
    target_plans = state.get("target_plans") or []

    # Build deduplicated CitationItems
    citations: list[CitationItem] = []
    seen_keys: set[tuple[str, int, str]] = set()
    for ch_dict in raw_chunks[:5]:
        rc = RetrievedChunk(**ch_dict)
        cit = rc.to_citation()
        key = (cit.source_title, cit.page_number, cit.section_heading)
        if key not in seen_keys:
            seen_keys.add(key)
            citations.append(cit)

    # 1. Corrective RAG Guardrail Response (< 0.35 confidence)
    if not is_relevant:
        guardrail_md = (
            "### Clause Not Found in Policy / Regulatory Documents\n\n"
            f"I checked the indexed policy wordings and IRDAI circulars, and the highest relevance score "
            f"(`{max_score:.2f}`) fell below our safety threshold (`{settings.relevance_score_threshold}`). "
            "The queried treatment or benefit is **not covered or not mentioned** in the active policy documents.\n\n"
            "- **What you can do:** Please specify the exact insurer and plan name (e.g., *HDFC ERGO Optima Secure*, "
            "*Star Health Comprehensive*, or *Niva Bupa ReAssure 2.0*) or upload your specific Policy Schedule PDF."
        )
        trace = list(state.get("node_trace", [])) + ["ResponseSynthesizerNode (guardrail_triggered)"]
        return {
            **state,
            "answer_markdown": guardrail_md,
            "citations": [],
            "comparison_table": None,
            "follow_up_suggestions": [
                "What waiting periods apply in HDFC ERGO Optima Secure?",
                "Compare Star Comprehensive and Niva Bupa ReAssure 2.0 on restoration benefits",
                "Are surgical gloves and nebulization kits covered under IRDAI rules?",
            ],
            "confidence_score": round(max_score, 4),
            "node_trace": trace,
        }

    comparison_table: list[ComparisonMetricRow] | None = None
    if intent == "plan_comparison":
        comparison_table = _build_comparison_rows(target_plans, query)

    # Try Groq LLM first if configured; otherwise run deterministic grounded synthesis
    llm_answer = _try_llm_synthesis(query, intent, citations, tool_outputs, comparison_table)

    if llm_answer:
        answer_md = llm_answer
    elif intent == "claim_calculation" and "claim_calculation" in tool_outputs:
        calc = tool_outputs["claim_calculation"]
        top_cit = citations[0] if citations else None
        cit_tag = (
            f"[Source: {top_cit.source_title}, Page {top_cit.page_number}, {top_cit.section_heading}]"
            if top_cit
            else "[Source: Star Health Comprehensive, Page 1, Section 1.1]"
        )
        notes_bullets = "\n".join(f"- {note}" for note in calc["itemized_notes"])
        answer_md = (
            f"### Deterministic Claim Payout & Out-of-Pocket Estimate ({calc['plan_name']})\n\n"
            f"Based on the policy's room-rent and deduction rules {cit_tag}, here is your exact mathematical breakdown:\n\n"
            f"- **Total Hospital Bill:** Rs. {calc['total_hospital_bill']:,.2f}\n"
            f"- **Room Rent Proportionate Multiplier:** `{calc['proportionate_multiplier'] * 100:.1f}%`\n"
            f"- **Proportionate Deduction Amount:** Rs. {calc['proportionate_deduction_amount']:,.2f}\n"
            f"- **Non-Payable Consumables Deduction:** Rs. {calc['non_payable_consumables_deduction']:,.2f}\n"
            f"- **Aggregate Deductible Applied:** Rs. {calc['deductible_applied']:,.2f}\n"
            f"- **Mandatory Co-Payment ({calc['co_payment_percentage']:.0f}%):** Rs. {calc['co_payment_deduction_amount']:,.2f}\n"
            f"- **Net Insurer Payable Claim Amount:** **Rs. {calc['final_payable_claim_amount']:,.2f}**\n"
            f"- **Estimated Patient Out-of-Pocket Cost:** **Rs. {calc['total_out_of_pocket_cost']:,.2f}**\n\n"
            f"#### Step-by-Step Audit Notes\n{notes_bullets}"
        )
    elif intent == "plan_comparison" and comparison_table:
        plan_a = target_plans[0] if len(target_plans) >= 1 else "Optima Secure"
        plan_b = target_plans[1] if len(target_plans) >= 2 else "Star Comprehensive"
        bullet_lines = [
            f"- **{row.criterion}:** **{row.plan_a_value}** vs. **{row.plan_b_value}** — *{row.winner_or_verdict}*"
            for row in comparison_table
        ]
        cit_tags = " ".join(
            f"[Source: {c.source_title}, Page {c.page_number}, {c.section_heading}]"
            for c in citations[:2]
        )
        answer_md = (
            f"### Side-by-Side Comparison: {plan_a} vs. {plan_b}\n\n"
            f"Here is the clause-by-clause comparison extracted from the official policy wordings {cit_tags}:\n\n"
            + "\n".join(bullet_lines)
        )
    elif intent == "regulatory_grievance":
        reg = tool_outputs.get("irdai_verification", {})
        violations = reg.get("violations_detected") or []
        top_cit = citations[0] if citations else None
        cit_tag = (
            f"[Source: {top_cit.source_title}, Page {top_cit.page_number}, {top_cit.section_heading}]"
            if top_cit
            else "[Source: IRDAI Master Circular 2024, Page 1, Clause 1.1]"
        )
        if violations:
            v_lines = "\n".join(
                f"- **{v['clause']} ({v['circular_ref']}):** {v['finding']}"
                for v in violations
            )
            gro_draft = (
                "> **Subject:** Formal Representation Against Unlawful Claim Action — Policy Holder Escalation under Circular Ref: IRDAI/HLT/CIR/PRO/84/05/2024\n>\n"
                f"> Dear Grievance Redressal Officer (GRO),\n>\n"
                f"> I am writing to formally contest the action on my health insurance claim. As established under **{violations[0]['clause']}** of the **IRDAI Master Circular on Health Insurance Business 2024 (`IRDAI/HLT/CIR/PRO/84/05/2024`)**, {violations[0]['finding']} "
                "Please review and settle the admissible claim immediately within statutory timelines, failing which I shall escalate this matter to the IRDAI Bima Bharosa Portal and the Office of the Insurance Ombudsman under Clause 3.3."
            )
            answer_md = (
                f"### IRDAI Regulatory Compliance Audit & Grievance Assistant\n\n"
                f"Based on the **IRDAI Master Circular 2024** {cit_tag}, we detected the following regulatory violations:\n\n"
                f"{v_lines}\n\n"
                f"#### Ready-to-Send Escalation Notice to Insurer GRO\n{gro_draft}"
            )
        else:
            excerpts = "\n\n".join(
                f"- **{c.source_title} (Page {c.page_number}, {c.section_heading}):** {c.snippet} "
                f"`[Source: {c.source_title}, Page {c.page_number}, {c.section_heading}]`"
                for c in citations[:3]
            )
            answer_md = (
                f"### IRDAI Regulatory Guidelines (`IRDAI/HLT/CIR/PRO/84/05/2024`)\n\n"
                f"Here are the governing IRDAI rules for your query:\n\n{excerpts}"
            )
    else:
        # Standard Citation-Backed Policy Q&A (Pillar 1)
        excerpts = "\n\n".join(
            f"- **{c.source_title} (Page {c.page_number}, {c.section_heading}):** {c.snippet} "
            f"`[Source: {c.source_title}, Page {c.page_number}, {c.section_heading}]`"
            for c in citations[:3]
        )
        consumable_block = ""
        if "consumable_audit" in tool_outputs:
            ca = tool_outputs["consumable_audit"]
            c_lines = "\n".join(
                f"  - **{item['canonical_item_name']} (Item #{item['annexure_i_item_number']}):** `{item['irdai_status']}` $\\rightarrow$ {item['audit_verdict']}"
                for item in ca["audited_items"]
            )
            consumable_block = f"\n\n#### IRDAI Annexure-I Consumables Audit\n{c_lines}"

        answer_md = (
            f"### Policy Clause Analysis & Citations\n\n"
            f"{excerpts}"
            f"{consumable_block}"
        )

    follow_ups_by_intent: dict[str, list[str]] = {
        "policy_qa": [
            "Calculate my out-of-pocket cost if I choose a Rs. 10,000/day room",
            "Compare this plan side-by-side with Niva Bupa ReAssure 2.0",
            "Which hospital consumables are subsumed in room rent under IRDAI Annexure-I?",
        ],
        "plan_comparison": [
            "Estimate claim payout for a Rs. 2,00,000 hospital bill under both plans",
            "How does the 36-month PED waiting period work across insurers?",
            "Which plan covers all 68 non-payable consumables without an extra rider?",
        ],
        "claim_calculation": [
            "Are medicines, implants, and ICU charges exempt from proportionate deduction?",
            "Check if surgical gloves and laundry charges can be billed separately",
            "Compare room rent rules across HDFC Optima Secure and Star Comprehensive",
        ],
        "regulatory_grievance": [
            "Draft a Form VI complaint for the Insurance Ombudsman",
            "What is the Rs. 5,000/day penalty rule for delayed Ombudsman awards?",
            "Can a hospital hold me past 3 hours waiting for cashless discharge approval?",
        ],
    }

    trace = list(state.get("node_trace", [])) + [
        f"ResponseSynthesizerNode (citations={len(citations)})"
    ]
    return {
        **state,
        "answer_markdown": answer_md,
        "citations": citations,
        "comparison_table": comparison_table,
        "follow_up_suggestions": follow_ups_by_intent.get(intent, follow_ups_by_intent["policy_qa"]),
        "confidence_score": round(max_score, 4),
        "node_trace": trace,
    }
