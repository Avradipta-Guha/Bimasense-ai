"""
LangGraph State Schema (`AgentState`) for BimaSense AI (Milestone 3).
Tracks the complete lifecycle of a request across all 6 nodes:
1. `IntentRouterNode`
2. `QueryDecomposerNode`
3. `HybridRetrieverNode`
4. `RelevanceGraderNode`
5. `ToolExecutionNode`
6. `ResponseSynthesizerNode`
"""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from app.schemas.api_models import CitationItem, ComparisonMetricRow


IntentRoute = Literal[
    "policy_qa",
    "plan_comparison",
    "claim_calculation",
    "regulatory_grievance",
]


class AgentState(TypedDict, total=False):
    """Stateful dictionary passed between nodes in the BimaSense LangGraph workflow."""

    # --- Input Context ---
    user_query: str
    user_id: str
    selected_plan: str | None
    compare_plans: list[str]
    claim_input_params: dict[str, Any]

    # --- Node 1: IntentRouterNode Outputs ---
    intent: IntentRoute
    routing_rationale: str

    # --- Node 2: QueryDecomposerNode Outputs ---
    rewritten_query: str
    sub_queries: list[str]
    target_plans: list[str]
    target_section_category: str | None

    # --- Node 3: HybridRetrieverNode Outputs ---
    retrieved_chunks: list[dict[str, Any]]
    comparison_chunks_by_plan: dict[str, list[dict[str, Any]]]

    # --- Node 4: RelevanceGraderNode (Corrective RAG Guardrail) Outputs ---
    max_relevance_score: float
    is_relevant: bool
    grader_feedback: str

    # --- Node 5: ToolExecutionNode Outputs ---
    tool_outputs: dict[str, Any]

    # --- Node 6: ResponseSynthesizerNode Final Outputs ---
    answer_markdown: str
    citations: list[CitationItem]
    comparison_table: list[ComparisonMetricRow] | None
    follow_up_suggestions: list[str]
    confidence_score: float
    node_trace: list[str]
