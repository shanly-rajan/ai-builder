"""Secret-safe runtime configuration for the Cricket RAG Engine."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV_FILE = PROJECT_ROOT / ".env"


@dataclass(frozen=True)
class Settings:
    """Provider settings and hyperparameter defaults loaded from environment."""

    openai_api_key: str = field(repr=False)
    pinecone_api_key: str = field(repr=False)
    pinecone_index_name: str

    # Model and retrieval defaults
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    llm_model: str = "gpt-5.6-luna"
    top_k: int = 5

    @property
    def configuration_status(self) -> dict[str, bool]:
        """Return presence flags without exposing credential values."""

        return {
            "OPENAI_API_KEY": bool(self.openai_api_key),
            "PINECONE_API_KEY": bool(self.pinecone_api_key),
            "PINECONE_INDEX_NAME": bool(self.pinecone_index_name),
        }

    @property
    def missing_variables(self) -> tuple[str, ...]:
        """Return the required environment variables that are blank or absent."""

        return tuple(
            variable
            for variable, configured in self.configuration_status.items()
            if not configured
        )

    @property
    def is_ready(self) -> bool:
        """Return whether every required setting has a value."""

        return not self.missing_variables


def load_settings(env_file: Path | None = DEFAULT_ENV_FILE) -> Settings:
    """Load local variables without overriding explicitly exported values.

    Passing ``None`` skips dotenv loading, which keeps automated tests isolated from
    a developer's real local credentials.
    """

    if env_file is not None:
        load_dotenv(dotenv_path=env_file, override=False)

    return Settings(
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        pinecone_api_key=os.getenv("PINECONE_API_KEY", "").strip(),
        pinecone_index_name=os.getenv("PINECONE_INDEX_NAME", "").strip(),
        embedding_model=os.getenv("EMBEDDING_MODEL", "text-embedding-3-small").strip(),
        embedding_dim=int(os.getenv("EMBEDDING_DIM", "1536")),
        llm_model=os.getenv("LLM_MODEL", "gpt-5.6-luna").strip(),
        top_k=int(os.getenv("TOP_K_RETRIEVAL", "5")),
    )
