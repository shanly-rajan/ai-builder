"""Repository contract for the bounded M13.4 live-path interpretation repair."""

from pathlib import Path

from scholarpath.domain import SearchResultRejectionCategory
from scholarpath.graph import (
    AlternateSourceRejectionCategory,
    GraphFixtureConfig,
    VerificationPolicy,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m13_4_prompt_readme_and_architecture_record_the_bounded_repair() -> None:
    prompt_path = PROJECT_ROOT / "docs/prompts/m13-4-live-discovery-and-official-source-recovery.md"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    build_journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt_path.is_file()
    prompt = " ".join(prompt_path.read_text(encoding="utf-8").split())
    assert "Milestone M13.4 Prompt: Live discovery identity and official-source recovery" in prompt
    assert "Do not lower the five-Verified-Supervisor minimum" in prompt
    assert "Search titles, descriptions, snippets, and hostnames may select a URL only" in prompt
    assert "M13.4 live discovery identity and official-source recovery" in readme
    assert "## M13.4 live discovery identity and official-source recovery boundary" in architecture
    assert "## M13.4 Repair: Live discovery identity and official-source recovery" in build_journal


def test_m13_4_keeps_strict_verification_and_shortlist_thresholds() -> None:
    policy = VerificationPolicy()
    graph_config = GraphFixtureConfig()

    assert policy.minimum_verified_supervisors == 5
    assert policy.maximum_alternate_source_retries == 1
    assert graph_config.shortlist_size == 5


def test_m13_4_preserves_closed_discovery_and_selector_diagnostic_taxonomies() -> None:
    assert {category.value for category in SearchResultRejectionCategory} == {
        "person_not_established",
        "academic_context_not_established",
        "identity_conflict",
        "institution_not_established",
        "incomplete_institution",
    }
    assert {category.value for category in AlternateSourceRejectionCategory} == {
        "query_mismatch",
        "same_url",
        "https_or_host_invalid",
        "exact_person_text_missing",
        "exact_institution_text_missing",
        "singular_route_mismatch",
        "academic_host_mismatch",
        "source_kind_unsupported",
    }
