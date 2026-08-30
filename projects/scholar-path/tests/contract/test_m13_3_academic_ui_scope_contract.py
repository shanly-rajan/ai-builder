"""Repository contract for the bounded M13.3 academic UI and scope repair."""

from pathlib import Path

from scholarpath.agents import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V4,
    RESEARCH_PLANNING_PROMPT_VERSION,
    RESEARCH_PLANNING_SYSTEM_PROMPT_V4,
)
from scholarpath.domain import CandidateProfile, SearchSourceType
from scholarpath.graph import GraphFixtureConfig, VerificationPolicy
from scholarpath.ui.app import HERO_SUBTITLE, HERO_TITLE, PAGE_ICON, STAGE_LABELS

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m13_3_prompt_active_documentation_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs/prompts/m13-3-academic-ui-and-research-degree-scope.md"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert "Milestone M13.3 Prompt" in prompt.read_text(encoding="utf-8")
    assert "Evidence-backed supervisor discovery for postgraduate research." in readme
    assert "## M13.3 academic presentation and postgraduate research scope" in architecture
    assert "## M13.3 Repair: Academic UI and research-degree scope" in journal


def test_m13_3_exposes_the_exact_academic_research_degree_presentation_contract() -> None:
    assert PAGE_ICON == "🎓"
    assert HERO_TITLE == "🎓 ScholarPath"
    assert HERO_SUBTITLE == "Evidence-backed supervisor discovery for postgraduate research."
    assert STAGE_LABELS[0] == "1. Your Research Degree Profile"
    assert len(STAGE_LABELS) == 6


def test_m13_3_active_prompts_cover_postgraduate_research_without_weakening_source_scope() -> None:
    assert RESEARCH_PLANNING_PROMPT_VERSION == "research-planning-v4"
    assert EVIDENCE_VERIFICATION_PROMPT_VERSION == "evidence-verification-v4"
    normalized_planning = " ".join(RESEARCH_PLANNING_SYSTEM_PROMPT_V4.split())
    normalized_evidence = " ".join(EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V4.split())

    assert "postgraduate research interests" in normalized_planning
    assert "preserve that exact degree scope" in normalized_planning
    assert "admission probability" in normalized_planning
    assert "Master's" in normalized_evidence
    assert "doctoral" in normalized_evidence


def test_m13_3_neutral_source_type_reads_legacy_checkpoints_without_writing_legacy_copy() -> None:
    assert SearchSourceType("doctoral_supervision_information") is (
        SearchSourceType.RESEARCH_DEGREE_SUPERVISION_INFORMATION
    )
    assert (
        SearchSourceType.RESEARCH_DEGREE_SUPERVISION_INFORMATION.value
        == "research_degree_supervision_information"
    )


def test_m13_3_does_not_add_degree_eligibility_state_or_relax_graph_gates() -> None:
    policy = VerificationPolicy()
    graph_config = GraphFixtureConfig()

    assert "degree_type" not in CandidateProfile.model_fields
    assert "degree_level" not in CandidateProfile.model_fields
    assert policy.minimum_verified_supervisors == 5
    assert policy.maximum_alternate_source_retries == 1
    assert graph_config.shortlist_size == 5
