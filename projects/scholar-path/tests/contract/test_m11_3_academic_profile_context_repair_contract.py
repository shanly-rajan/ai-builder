"""Repository contracts for the bounded M11.3 academic-profile repair."""

from pathlib import Path

from scholarpath.domain import SearchResultRejectionCategory
from scholarpath.graph import DiscoveryPolicy
from scholarpath.observability import GRAPH_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m11_3_prompt_diagram_readme_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs/prompts/m11-3-academic-profile-context-repair.md"
    diagram = PROJECT_ROOT / "docs/m11-3-academic-profile-context-repair.mmd"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert diagram.is_file()
    assert "M11.3 Academic-Profile Context Repair" in prompt.read_text(encoding="utf-8")
    assert "M11.3 academic-profile context repair" in readme
    assert "## M11.3 Repair: Academic-profile context" in journal


def test_m11_3_remains_deterministic_and_keeps_policy_bounds() -> None:
    source = (PROJECT_ROOT / "src/agents/supervisor_discovery.py").read_text(encoding="utf-8")
    policy = DiscoveryPolicy()

    assert GRAPH_VERSION == "m12.2"
    assert policy.minimum_unique_supervisors == 5
    assert policy.maximum_you_retry_count == 1
    assert policy.maximum_tavily_fallback_count == 4
    assert "_MAX_BOUNDED_DESCRIPTION_CHARACTERS = 1_000" in source
    assert "_identity_matches_search_topic" in source
    assert "_extract_owner_linked_context_institution" in source
    for forbidden_dependency in ("ChatOpenAI", "langchain", "httpx", "requests"):
        assert forbidden_dependency not in source


def test_m11_3_preserves_the_closed_privacy_safe_rejection_taxonomy() -> None:
    assert {category.value for category in SearchResultRejectionCategory} == {
        "person_not_established",
        "academic_context_not_established",
        "identity_conflict",
        "institution_not_established",
        "incomplete_institution",
    }
