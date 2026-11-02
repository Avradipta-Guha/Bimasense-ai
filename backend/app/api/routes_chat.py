"""
Smart Insurance Chat & SSE Streaming Endpoints (`routes_chat.py`) for BimaSense AI (Milestone 4).
Exposes:
- `POST /api/v1/chat/stream`: Streams Server-Sent Events (`text/event-stream`) formatted for
  Android's OkHttp EventSource client (`event: node_status`, `event: token`, `event: complete`).
- `POST /api/v1/chat/query`: Synchronous JSON endpoint returning `ChatResponsePayload`.
"""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.agent.graph import build_bimasense_graph
from app.agent.state import AgentState
from app.schemas.api_models import ChatRequest, ChatResponsePayload

router = APIRouter(prefix="/api/v1/chat", tags=["Smart Insurance Chat & SSE"])

_AGENT_GRAPH = build_bimasense_graph()


def _format_sse_frame(event_name: str, data_dict: dict) -> str:
    """Formats a single W3C-compliant Server-Sent Event frame (`event: <name>\\ndata: <json>\\n\\n`)."""
    payload_json = json.dumps(data_dict, ensure_ascii=False)
    return f"event: {event_name}\ndata: {payload_json}\n\n"


@router.post("/stream")
async def stream_chat_response(request: ChatRequest) -> StreamingResponse:
    """
    Streams RAG response tokens + final citation payload over Server-Sent Events (SSE).
    Android's OkHttp SSE client listens to:
    - `event: node_status` -> `{"step": "IntentRouterNode -> policy_qa"}`
    - `event: token`       -> `{"delta": "Under HDFC ERGO..."}`
    - `event: complete`    -> Full `ChatResponsePayload` JSON with `citations[]` and `comparison_table`.
    """
    initial_state: AgentState = {
        "user_query": request.query,
        "user_id": request.user_id,
        "selected_plan": request.selected_plan,
        "compare_plans": request.compare_plans,
    }

    async def event_generator() -> AsyncGenerator[str, None]:
        async for ev in _AGENT_GRAPH.astream_sse_events(initial_state, chunk_words=6):
            yield _format_sse_frame(ev["event"], ev["data"])

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/query", response_model=ChatResponsePayload)
async def query_chat_sync(request: ChatRequest) -> ChatResponsePayload:
    """Synchronous JSON endpoint executing the 6-node LangGraph workflow."""
    initial_state: AgentState = {
        "user_query": request.query,
        "user_id": request.user_id,
        "selected_plan": request.selected_plan,
        "compare_plans": request.compare_plans,
    }
    return _AGENT_GRAPH.invoke_to_payload(initial_state)
