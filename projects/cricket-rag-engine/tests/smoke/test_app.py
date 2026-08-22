"""Smoke test for the Streamlit application shell."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_streamlit_app_starts_without_provider_calls(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("PINECONE_API_KEY", "")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "")

    app = AppTest.from_file(str(PROJECT_ROOT / "app.py")).run(timeout=10)

    assert not app.exception
    assert app.title[0].value == "Cricket RAG Engine"
