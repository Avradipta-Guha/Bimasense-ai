"""
Centralized configuration for the BimaSense AI backend.
Loads settings from environment variables or .env file with sensible defaults
optimized for maximum accuracy on free-tier LLMs and lightweight CPU execution.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

# Base paths
BACKEND_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BACKEND_DIR / "data"
RAW_POLICIES_DIR = DATA_DIR / "raw_policies"
IRDAI_CIRCULARS_DIR = DATA_DIR / "irdai_circulars"
EVAL_DATASET_PATH = DATA_DIR / "eval_dataset.json"
LOCAL_INDEX_PATH = DATA_DIR / "local_hybrid_index.json"


def _load_dotenv_if_present(env_path: Path) -> None:
    """Lightweight .env file loader into os.environ."""
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        os.environ.setdefault(key, val)


_load_dotenv_if_present(BACKEND_DIR / ".env")


class Settings(BaseModel):
    """Application configuration validated with Pydantic v2."""

    # --- Application Metadata ---
    app_name: str = Field(default_factory=lambda: os.getenv("APP_NAME", "BimaSense AI — Medical Insurance Copilot API"))
    app_version: str = "1.0.0"
    app_env: Literal["development", "staging", "production"] = Field(
        default_factory=lambda: os.getenv("APP_ENV", "development")  # type: ignore[return-value]
    )
    debug: bool = Field(default_factory=lambda: os.getenv("DEBUG", "true").lower() == "true")

    # --- LLM Configuration (Free Tier, Maximum Accuracy) ---
    # Groq provides free API access to Llama-3.3-70B-Versatile (top accuracy for
    # medical/legal clause extraction and structured JSON output) with Qwen-2.5
    # and local Ollama as automatic fallbacks.
    groq_api_key: str = Field(
        default_factory=lambda: os.getenv("GROQ_API_KEY", ""),
        description="Groq Cloud API Key",
    )
    primary_llm_model: str = Field(
        default_factory=lambda: os.getenv("PRIMARY_LLM_MODEL", "llama-3.3-70b-versatile"),
        description="Primary high-accuracy LLM for policy analysis and synthesis",
    )
    secondary_llm_model: str = Field(
        default_factory=lambda: os.getenv("SECONDARY_LLM_MODEL", "qwen-2.5-32b"),
        description="Secondary Groq model for fast intent routing and query rewriting",
    )
    llm_temperature: float = Field(
        default_factory=lambda: float(os.getenv("LLM_TEMPERATURE", "0.0")),
        ge=0.0,
        le=1.0,
        description="Zero temperature for deterministic legal/financial reasoning",
    )

    # --- Local Ollama Fallback ---
    ollama_base_url: str = Field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"))
    ollama_fallback_model: str = Field(default_factory=lambda: os.getenv("OLLAMA_FALLBACK_MODEL", "qwen2.5:7b-instruct"))

    # --- Qdrant Vector Database ---
    qdrant_url: str = Field(default_factory=lambda: os.getenv("QDRANT_URL", "http://localhost:6333"))
    qdrant_api_key: str | None = Field(default_factory=lambda: os.getenv("QDRANT_API_KEY") or None)
    qdrant_use_in_memory_fallback: bool = Field(
        default_factory=lambda: os.getenv("QDRANT_USE_IN_MEMORY_FALLBACK", "true").lower() == "true",
        description="Automatically fall back to Qdrant in-memory / local index if Docker is offline",
    )

    # Logical Qdrant collection names from Master Plan Section 4
    collection_insurer_policies: str = "insurer_policies"
    collection_irdai_regulations: str = "irdai_regulations"
    collection_non_payable_consumables: str = "non_payable_consumables"

    # --- Embeddings & Cross-Encoder Reranker ---
    dense_embedding_model: str = Field(
        default_factory=lambda: os.getenv("DENSE_EMBEDDING_MODEL", "BAAI/bge-small-en-v1.5")
    )
    dense_embedding_dim: int = Field(default_factory=lambda: int(os.getenv("DENSE_EMBEDDING_DIM", "384")))
    sparse_embedding_model: str = Field(default_factory=lambda: os.getenv("SPARSE_EMBEDDING_MODEL", "Qdrant/bm25"))
    reranker_model: str = Field(default_factory=lambda: os.getenv("RERANKER_MODEL", "ms-marco-MiniLM-L-12-v2"))

    # --- Chunking & Retrieval Hyperparameters ---
    chunk_size_chars: int = Field(
        default=1200,
        description="Target character length per semantic policy chunk (~300 tokens)",
    )
    chunk_overlap_chars: int = Field(
        default=200,
        description="Overlap between sequential narrative chunks within a section",
    )
    retrieval_top_k: int = Field(default_factory=lambda: int(os.getenv("RETRIEVAL_TOP_K", "15")))
    rerank_top_k: int = Field(default_factory=lambda: int(os.getenv("RERANK_TOP_K", "5")))
    relevance_score_threshold: float = Field(
        default_factory=lambda: float(os.getenv("RELEVANCE_SCORE_THRESHOLD", "0.35"))
    )


settings = Settings()
