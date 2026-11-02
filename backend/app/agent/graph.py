"""
Compiled 6-Node Stateful LangGraph Orchestrator for BimaSense AI (Milestone 3).

Graph Topology (Master Plan Section 5):
    START
      │
      ▼
    IntentRouterNode
      │
      ▼
    QueryDecomposerNode
      │
      ▼
    HybridRetrieverNode
      │
      ▼
    RelevanceGraderNode  ──(score < 0.35: Guardrail)──► ResponseSynthesizerNode ──► END
      │
      ├──(claim_calculation | regulatory_grievance | consumable_audit)──► ToolExecutionNode ──► ResponseSynthesizerNode ──► END
      │
      └──(policy_qa | plan_comparison)──────────────────────────────────► ResponseSynthesizerNode ──► END

Uses `langgraph.graph.StateGraph` when installed, and includes a drop-in compatible
state-machine compiler fallback when running in environments without `langgraph`.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from typing import Any

from app.agent.nodes import (
    hybrid_retriever_node,
    intent_router_node,
    query_decomposer_node,
    relevance_grader_node,
    response_synthesizer_node,
    tool_execution_node,
)
from app.agent.state import AgentState
from app.schemas.api_models import ChatResponsePayload


def _route_after_grader(state: AgentState) -> str:
    """
    Conditional edge router after `RelevanceGraderNode`:
    - If `is_relevant` is False (< 0.35), skip tools and go straight to `ResponseSynthesizerNode`
      to emit the Corrective RAG guardrail response.
    - If intent requires deterministic math or IRDAI rule verification (or query mentions Annexure-I
      consumables), route to `ToolExecutionNode`.
    - Otherwise route directly to `ResponseSynthesizerNode`.
    """
    if not state.get("is_relevant", False):
        return "response_synthesizer"

    intent = state.get("intent", "policy_qa")
    q_lower = state.get("user_query", "").lower()
    has_consumable_mention = any(
        k in q_lower for k in ["gloves", "nebulization", "nebulizer", "gown", "laundry", "admission kit", "file charges", "oximeter"]
    )
    if intent in ("claim_calculation", "regulatory_grievance") or has_consumable_mention:
        return "tool_execution"
    return "response_synthesizer"


class BimaSenseAgentGraph:
    """
    Unified interface wrapping the compiled 6-node LangGraph workflow.
    Provides `.invoke()`, `.stream_tokens()`, and `.to_api_payload()` for FastAPI & Android SSE.
    """

    def __init__(self) -> None:
        self._compiled_langgraph: Any = None
        self.engine_mode = "native_state_graph"
        self._init_graph()

    def _init_graph(self) -> None:
        try:
            from langgraph.graph import END, START, StateGraph  # type: ignore

            builder = StateGraph(AgentState)
            builder.add_node("intent_router", intent_router_node)
            builder.add_node("query_decomposer", query_decomposer_node)
            builder.add_node("hybrid_retriever", hybrid_retriever_node)
            builder.add_node("relevance_grader", relevance_grader_node)
            builder.add_node("tool_execution", tool_execution_node)
            builder.add_node("response_synthesizer", response_synthesizer_node)

            builder.add_edge(START, "intent_router")
            builder.add_edge("intent_router", "query_decomposer")
            builder.add_edge("query_decomposer", "hybrid_retriever")
            builder.add_edge("hybrid_retriever", "relevance_grader")
            builder.add_conditional_edges(
                "relevance_grader",
                _route_after_grader,
                {
                    "tool_execution": "tool_execution",
                    "response_synthesizer": "response_synthesizer",
                },
            )
            builder.add_edge("tool_execution", "response_synthesizer")
            builder.add_edge("response_synthesizer", END)

            self._compiled_langgraph = builder.compile()
            self.engine_mode = "langgraph.StateGraph"
        except ImportError:
            self._compiled_langgraph = None
            self.engine_mode = "native_state_graph"

    def invoke(self, initial_state: AgentState) -> AgentState:
        """Executes the 6-node stateful workflow synchronously and returns the final `AgentState`."""
        state: AgentState = {
            "user_id": "global",
            "node_trace": [],
            **initial_state,
        }

        if self._compiled_langgraph is not None:
            return self._compiled_langgraph.invoke(state)

        # Native deterministic state-graph execution matching exact LangGraph edges
        state = intent_router_node(state)
        state = query_decomposer_node(state)
        state = hybrid_retriever_node(state)
        state = relevance_grader_node(state)

        next_node = _route_after_grader(state)
        if next_node == "tool_execution":
            state = tool_execution_node(state)

        state = response_synthesizer_node(state)
        return state

    def invoke_to_payload(self, initial_state: AgentState) -> ChatResponsePayload:
        """Runs the graph and returns a validated `ChatResponsePayload` ready for FastAPI."""
        final_state = self.invoke(initial_state)
        return ChatResponsePayload(
            intent=final_state.get("intent", "policy_qa"),
            answer_markdown=final_state.get("answer_markdown", ""),
            citations=final_state.get("citations", []),
            comparison_table=final_state.get("comparison_table"),
            follow_up_suggestions=final_state.get("follow_up_suggestions", []),
            confidence_score=float(final_state.get("confidence_score", 0.0)),
        )

    def stream_sse_events(self, initial_state: AgentState, chunk_words: int = 6) -> Generator[dict[str, Any], None, None]:
        """
        Streams Server-Sent Events (SSE) for the Android Chat Screen (`POST /api/v1/chat/stream`):
        1. Emits `node_status` events as the graph progresses.
        2. Streams `token` chunks of `answer_markdown`.
        3. Emits the final `complete` payload containing `citations[]`, `comparison_table`, and `follow_up_suggestions[]`.
        """
        final_state = self.invoke(initial_state)

        for step in final_state.get("node_trace", []):
            yield {"event": "node_status", "data": {"step": step}}

        answer = final_state.get("answer_markdown", "")
        words = answer.split(" ")
        for i in range(0, len(words), chunk_words):
            token_piece = " ".join(words[i : i + chunk_words])
            if i + chunk_words < len(words):
                token_piece += " "
            yield {"event": "token", "data": {"delta": token_piece}}

        payload = ChatResponsePayload(
            intent=final_state.get("intent", "policy_qa"),
            answer_markdown=answer,
            citations=final_state.get("citations", []),
            comparison_table=final_state.get("comparison_table"),
            follow_up_suggestions=final_state.get("follow_up_suggestions", []),
            confidence_score=float(final_state.get("confidence_score", 0.0)),
        )
        yield {"event": "complete", "data": payload.model_dump()}

    async def astream_sse_events(self, initial_state: AgentState, chunk_words: int = 6) -> AsyncGenerator[dict[str, Any], None]:
        """Async generator wrapper for FastAPI `StreamingResponse` / `EventSourceResponse`."""
        for ev in self.stream_sse_events(initial_state, chunk_words=chunk_words):
            yield ev


def build_bimasense_graph() -> BimaSenseAgentGraph:
    """Factory returning a compiled `BimaSenseAgentGraph` instance."""
    return BimaSenseAgentGraph()
