"""Repository contract for M13.9 postgraduate presentation controls."""

from pathlib import Path

import pytest

from scholarpath.ui.app import HERO_SUBTITLE

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TAGLINE = "Evidence-backed supervisor discovery for postgraduate research."
LEGACY_TAGLINE = "Evidence-backed Supervisor discovery for Master's and doctoral research."


@pytest.mark.parametrize(
    "relative_path",
    (
        "README.md",
        "docs/architecture.md",
    ),
)
def test_active_presentation_docs_use_exact_postgraduate_tagline(relative_path: str) -> None:
    document = (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")

    assert TAGLINE in document
    assert LEGACY_TAGLINE not in document


def test_streamlit_hero_uses_exact_postgraduate_tagline() -> None:
    assert HERO_SUBTITLE == TAGLINE


def test_current_terminology_uses_postgraduate_scope_without_weakening_source_scope() -> None:
    contract = (PROJECT_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    terminology = (PROJECT_ROOT / "docs/terminology.md").read_text(encoding="utf-8")
    reliability = (PROJECT_ROOT / "docs/reliability-review.md").read_text(encoding="utf-8")

    assert "Candidate: a person pursuing postgraduate research." in contract
    assert "must not be generalized to another" in contract
    assert "postgraduate research product scope" in terminology.lower()
    assert "postgraduate-degree context" in terminology
    assert "Candidate's postgraduate research preferences" in reliability


def test_milestone_prompt_and_architecture_record_reviewer_controls() -> None:
    prompt = (PROJECT_ROOT / "docs/prompts/m13-9-demo-profile-theme-controls.md").read_text(
        encoding="utf-8"
    )
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    normalized_architecture = " ".join(architecture.split())
    diagram = (PROJECT_ROOT / "docs/m13-9-postgraduate-presentation-controls.mmd").read_text(
        encoding="utf-8"
    )

    assert (
        'Update tagline to "Evidence-backed supervisor discovery for postgraduate research."'
        in prompt
    )
    assert (
        "Applications of machine learning and artificial intelligence in software engineering."
        in prompt
    )
    assert "Use demo research profile" in prompt
    assert "Light mode" in prompt
    assert "## M13.9 postgraduate presentation and reviewer controls" in architecture
    assert (
        "LangGraph state, Candidate memory, evidence, traces, or Supervisor lifecycle data"
        in normalized_architecture
    )
    assert "Use demo research profile" in diagram
    assert "off = dark" in diagram
