"""Repository contracts for the bounded M11.1 and M11.2 discovery repairs."""

from pathlib import Path

from scholarpath.agents import RESEARCH_PLANNING_PROMPT_VERSION
from scholarpath.graph import DiscoveryPolicy, SearchAttempt
from scholarpath.observability import GRAPH_VERSION, SAFE_TRACE_METADATA_KEYS

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_repair_prompt_diagram_readme_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs/prompts/m11-discovery-quality-repair.md"
    diagram = PROJECT_ROOT / "docs/m11-discovery-quality-repair.mmd"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert diagram.is_file()
    assert "M11 Discovery-Quality Repair" in prompt.read_text(encoding="utf-8")
    assert "M11.1 discovery-quality repair" in readme
    assert "## M11.1 Repair: Discovery quality and safe diagnostics" in journal


def test_m11_2_prompt_diagram_readme_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs/prompts/m11-2-discovery-completion-repair.md"
    diagram = PROJECT_ROOT / "docs/m11-2-discovery-completion-repair.mmd"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert diagram.is_file()
    assert "M11.2 Discovery-Completion Repair" in prompt.read_text(encoding="utf-8")
    assert "M11.2 discovery-completion repair" in readme
    assert "## M11.2 Repair: Discovery completion" in journal


def test_m11_2_preserves_discovery_gate_and_fallback_budget() -> None:
    policy = DiscoveryPolicy()
    attempt_properties = SearchAttempt.model_json_schema()["properties"]

    assert policy.minimum_unique_supervisors == 5
    assert policy.maximum_tavily_fallback_count == 4
    assert "rejection_counts" in attempt_properties


def test_repair_versions_and_langsmith_regional_settings_are_explicit() -> None:
    environment_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert RESEARCH_PLANNING_PROMPT_VERSION == "research-planning-v2"
    assert GRAPH_VERSION == "m12"
    assert "LANGSMITH_ENDPOINT=" in environment_example
    assert "LANGSMITH_WORKSPACE_ID=" in environment_example


def test_trace_metadata_contract_excludes_search_and_candidate_content() -> None:
    forbidden_keys = {
        "api_key",
        "candidate_id",
        "candidate_name",
        "full_page",
        "query",
        "raw_results",
        "source_url",
        "supervisor_name",
    }

    assert forbidden_keys.isdisjoint(SAFE_TRACE_METADATA_KEYS)
    assert {
        "provider",
        "attempt_number",
        "raw_result_count",
        "plausible_supervisor_count",
        "error_category",
        "fallback_search_used",
        "discovery_route",
        "rejected_person_not_established_count",
        "rejected_academic_context_not_established_count",
        "rejected_identity_conflict_count",
        "rejected_institution_not_established_count",
        "rejected_incomplete_institution_count",
    } <= set(SAFE_TRACE_METADATA_KEYS)
