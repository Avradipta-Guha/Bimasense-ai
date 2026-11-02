"""
FastAPI Application Entrypoint (`main.py`) for BimaSense AI (Milestone 4).
Configures CORS, ensures seed policies and Qdrant/local hybrid indexes are initialized on startup,
and mounts the Policy Vault, Smart Chat SSE, Plan Comparator, and Claim Calculator routers.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import chat_router, policy_router, tools_router
from app.config import LOCAL_INDEX_PATH, settings
from scripts.run_milestone1_pipeline import run_milestone1_ingestion


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description=(
            "Production-grade Hybrid RAG & Agentic Backend for BimaSense AI — "
            "decoding Indian medical insurance policies with page-level citations, "
            "side-by-side plan comparisons, deterministic room-rent & consumable calculators, "
            "and IRDAI Master Circular 2024 regulatory verification."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # Allow Android client & local web debuggers via CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @application.on_event("startup")
    async def startup_initialize_index() -> None:
        if not LOCAL_INDEX_PATH.exists():
            run_milestone1_ingestion()

    @application.get("/health", tags=["System Health"])
    async def health_check() -> dict[str, str]:
        return {
            "status": "healthy",
            "service": settings.app_name,
            "version": settings.app_version,
            "primary_llm": settings.primary_llm_model,
            "dense_embedding_model": settings.dense_embedding_model,
            "reranker_model": settings.reranker_model,
        }

    application.include_router(policy_router)
    application.include_router(chat_router)
    application.include_router(tools_router)

    return application


app = create_app()
