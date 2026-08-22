"""Unit tests for secret-safe environment configuration."""

from __future__ import annotations

from src.config import load_settings

VARIABLES = ("OPENAI_API_KEY", "PINECONE_API_KEY", "PINECONE_INDEX_NAME")


def test_missing_configuration_is_reported(monkeypatch) -> None:
    for variable in VARIABLES:
        monkeypatch.delenv(variable, raising=False)

    settings = load_settings(env_file=None)

    assert settings.missing_variables == VARIABLES
    assert not settings.is_ready
    assert settings.embedding_model == "text-embedding-3-small"
    assert settings.embedding_dim == 1536
    assert settings.llm_model == "gpt-5.6-luna"
    assert settings.top_k == 5


def test_exported_configuration_is_loaded_without_secret_repr(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "openai-secret")
    monkeypatch.setenv("PINECONE_API_KEY", "pinecone-secret")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "cricket-rag-engine-test")

    settings = load_settings(env_file=None)

    assert settings.is_ready
    assert all(settings.configuration_status.values())
    assert "openai-secret" not in repr(settings)
    assert "pinecone-secret" not in repr(settings)
