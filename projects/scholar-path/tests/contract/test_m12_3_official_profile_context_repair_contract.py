"""Repository contract for the bounded M12.3 official-profile context repair."""

from pathlib import Path

from scholarpath.agents import EVIDENCE_VERIFICATION_PROMPT_VERSION
from scholarpath.domain import (
    EvidenceClaim,
    is_singular_person_profile_url,
    supervisor_names_are_title_equivalent,
)
from scholarpath.evaluation import LOCAL_BASELINE_NAME
from scholarpath.graph import VerificationPolicy
from scholarpath.observability import GRAPH_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m12_3_prompt_diagram_readme_architecture_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs/prompts/m12-3-official-profile-context-repair.md"
    safety_prompt = (
        PROJECT_ROOT / "docs/prompts/m12-3a-official-profile-subject-safety-hardening.md"
    )
    diagram = PROJECT_ROOT / "docs/m12-3-official-profile-context-repair.mmd"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert safety_prompt.is_file()
    assert diagram.is_file()
    assert "M12.3 Official-profile context and discovery integrity repair" in prompt.read_text(
        encoding="utf-8"
    )
    assert "subject identity evidence ID" in diagram.read_text(encoding="utf-8")
    assert "surname alone" in safety_prompt.read_text(encoding="utf-8")
    assert "M12.3 official-profile context and discovery integrity repair" in readme
    assert "M12.3 official-profile context and discovery integrity boundary" in architecture
    assert "## M12.3 Repair: Official-profile context and discovery integrity" in journal


def test_m12_3_versions_the_graph_prompt_and_offline_replay() -> None:
    assert GRAPH_VERSION == "m13"
    assert EVIDENCE_VERIFICATION_PROMPT_VERSION == "evidence-verification-v3"
    assert LOCAL_BASELINE_NAME == "scholarpath-m13-fake-baseline-2026-08-30"


def test_m12_3_keeps_verification_and_retry_thresholds_unchanged() -> None:
    policy = VerificationPolicy()

    assert policy.minimum_verified_supervisors == 5
    assert policy.maximum_alternate_source_retries == 1


def test_m12_3_persists_typed_identity_context_and_native_structured_output() -> None:
    evidence_source = (PROJECT_ROOT / "src/agents/evidence_verification.py").read_text(
        encoding="utf-8"
    )
    openai_source = (PROJECT_ROOT / "src/agents/openai_evidence.py").read_text(encoding="utf-8")

    assert "subject_identity_evidence_id" in EvidenceClaim.model_fields
    assert "subject_identity_evidence_id" in evidence_source
    assert "EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V3" in openai_source
    assert 'method="json_schema"' in openai_source
    assert "strict=True" in openai_source
    assert "max_retries=0" in openai_source
    assert "json.loads" not in openai_source


def test_m12_3_recognizes_bounded_profile_paths_and_discovery_integrity_checks() -> None:
    routing_source = (PROJECT_ROOT / "src/graph/verification.py").read_text(encoding="utf-8")
    discovery_source = (PROJECT_ROOT / "src/agents/supervisor_discovery.py").read_text(
        encoding="utf-8"
    )

    for path_token in ('"persons"', '"researcher"', '"researchers"', '"directory"'):
        assert path_token in routing_source
    assert "_has_complete_institution_shape" in discovery_source
    assert "require_owner_linked_context" in discovery_source
    assert "_COMPACT_INSTITUTION_ACRONYM_PATTERN" in discovery_source


def test_m12_3_contract_locks_singular_profile_and_name_ownership_boundaries() -> None:
    accepted_urls = (
        "https://example.edu/profile/jane-doe",
        "https://example.edu/profiles/42",
        "https://example.edu/academic/jane-doe",
        "https://example.edu/academics/jane-doe",
        "https://example.edu/people/jane-doe",
        "https://example.edu/person/jane-doe",
        "https://example.edu/persons/jane-doe",
        "https://example.edu/directories/jane-doe",
        "https://example.edu/directory/jane-doe",
        "https://example.edu/staff-directory/jane-doe",
        "https://example.edu/department/staff/jane-doe",
        "https://example.edu/faculty/jane-doe",
        "https://example.edu/researcher/jane-doe",
        "https://example.edu/researchers/jane-doe",
        "https://example.edu/staff/42/jane-doe",
        "https://example.edu/about/our-people/jane-doe",
        "https://example.edu/profile/alice-news",
        "https://profiles.example.edu/jane-doe",
    )
    rejected_urls = (
        "https://example.edu/people",
        "https://example.edu/staff",
        "https://example.edu/directory",
        "https://example.edu/people/events",
        "https://example.edu/faculty/about",
        "https://example.edu/profile/contact",
        "https://example.edu/profile/our-people",
        "https://example.edu/news/jane-doe",
        "https://example.edu/projects/jane-doe",
        "https://example.edu/contact/people/jane-doe",
        "https://example.edu/search/people/jane-doe",
        "https://example.edu/projects/profile/jane-doe",
        "https://example.edu/groups/people/jane-doe",
        "https://example.edu/about/profile/jane-doe",
        "https://example.edu/about-us/people/jane-doe",
        "https://example.edu/en/news-and-events/people/jane-doe",
        "https://example.edu/en/news_and_events/people/jane-doe",
        "https://example.edu/en/articles-and-news/profiles/jane-doe",
        "https://example.edu/en/projects-and-events/faculty/jane-doe",
        "https://example.edu/en/search-results/person/jane-doe",
        "https://example.edu/en/newsAndEvents/people/jane-doe",
        "https://example.edu/en/newsandevents/people/jane-doe",
        "https://example.edu/en/searchResults/people/jane-doe",
        "https://example.edu/en/contactUs/people/jane-doe",
        "https://example.edu/en/researchProjects/people/jane-doe",
    )

    assert all(is_singular_person_profile_url(url) for url in accepted_urls)
    assert not any(is_singular_person_profile_url(url) for url in rejected_urls)
    assert supervisor_names_are_title_equivalent(
        "Professor Dhavalkumar (Dhaval) Thakker",
        "Professor Dhaval Thakker",
    )
    assert not supervisor_names_are_title_equivalent("Professor Thakker", "Dhaval Thakker")
    assert not supervisor_names_are_title_equivalent("Margaret (AI) Boden", "Margaret AI Boden")
