"""Streamlit shell for validating the Cricket RAG Engine setup."""

from __future__ import annotations

import streamlit as st

from src.config import load_settings

st.set_page_config(page_title="Cricket RAG Engine", page_icon="🏏", layout="wide")

settings = load_settings()

st.title("Cricket RAG Engine")
st.caption("Foundation scaffold — provider connectivity is not called from this screen.")

st.subheader("Environment readiness")
for variable, configured in settings.configuration_status.items():
    icon = "✅" if configured else "⚠️"
    st.write(f"{icon} `{variable}`")

if settings.is_ready:
    st.success("Required configuration is present. Provider connectivity has not been tested.")
else:
    missing = ", ".join(settings.missing_variables)
    st.warning(f"Copy `.env.example` to `.env` and configure: {missing}.")

st.subheader("Planned request flow")
st.code(
    "Question -> retrieve top-k evidence -> evidence gate -> grounded answer + citations",
    language=None,
)
