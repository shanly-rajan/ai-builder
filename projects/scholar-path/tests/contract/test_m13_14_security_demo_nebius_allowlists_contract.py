"""Repository contract for the M13.14 demo and independent-review repair."""

from pathlib import Path

from scholarpath.agents import (
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    INDEPENDENT_REVIEW_SYSTEM_PROMPT_V4,
    IndependentReviewInput,
)
from scholarpath.ui.app import (
    DEMO_PROFILE_RESEARCH_STATEMENT,
    DEMO_PROFILE_RESEARCH_TOPICS,
    demo_profile_widget_values,
)
from tests.fixtures import (
    make_candidate_profile,
    make_research_fit_assessment,
    make_verified_supervisor,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_active_demo_profile_uses_the_security_research_example() -> None:
    assert DEMO_PROFILE_RESEARCH_STATEMENT == (
        "Automated vulnerability detection, threat analysis, and secure code evaluation in "
        "distributed cloud environments."
    )
    assert DEMO_PROFILE_RESEARCH_TOPICS == (
        "Computer Security, Software Security, Vulnerability Analysis, Cloud Security, "
        "Static Analysis"
    )
    assert demo_profile_widget_values()["profile_methodological_interests"] == ""


def test_active_independent_review_contract_exposes_exact_reference_allowlists() -> None:
    review_input = IndependentReviewInput.from_domain(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )

    assert INDEPENDENT_REVIEW_PROMPT_VERSION == "independent-review-v4"
    assert "removable_supporting_evidence_ids" in INDEPENDENT_REVIEW_SYSTEM_PROMPT_V4
    assert "eligible_overlooked_evidence_ids" in INDEPENDENT_REVIEW_SYSTEM_PROMPT_V4
    assert review_input.removable_supporting_evidence_ids
    assert review_input.eligible_overlooked_evidence_ids == ()


def test_prompt_and_current_docs_record_the_bounded_repair() -> None:
    prompt = (
        PROJECT_ROOT / "docs" / "prompts" / "m13-14-security-demo-and-nebius-review-allowlists.md"
    ).read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    demo = (PROJECT_ROOT / "docs" / "five-minute-demo.md").read_text(encoding="utf-8")

    assert "Automated vulnerability detection" in prompt
    assert 'why the "Independent Research Fit" was unavailable' in prompt
    assert "M13.14" in readme
    assert "M13.14 security demo profile" in architecture
    assert "Computer Security; Software Security" in demo
