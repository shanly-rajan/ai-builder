"""Contract tests for the M2 LangGraph state, topology, and documentation."""

import tomllib
from pathlib import Path
from typing import Annotated, cast, get_args, get_origin, get_type_hints

from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    ScholarPathState,
    build_scholarpath_graph,
)

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]

REQUIRED_STATE_FIELDS = {
    "candidate_profile",
    "candidate_preferences",
    "search_plan",
    "raw_search_results",
    "prospective_supervisors",
    "verified_supervisors",
    "research_fit_assessments",
    "proposed_shortlist",
    "shortlisted_supervisors",
    "rejected_supervisors",
    "candidate_feedback",
    "tool_errors",
    "search_attempts",
    "fallback_search_used",
    "retry_counts",
    "review_status",
    "execution_log",
}
M2_CANONICAL_NODE_NAMES = (
    "load_candidate_preferences",
    "plan_supervisor_searches",
    "discover_prospective_supervisors",
    "enough_supervisors_found",
    "fallback_supervisor_search",
    "deduplicate_supervisors",
    "extract_supervisor_evidence",
    "supervisor_evidence_sufficient",
    "retry_alternate_evidence_source",
    "evaluate_research_fit",
    "review_fit_assessments",
    "synthesize_supervisor_shortlist",
    "candidate_review_gate",
    "save_shortlisted_supervisors",
    "generate_shortlist_briefing",
)


def test_scholarpath_state_contains_every_required_m2_channel() -> None:
    assert ScholarPathState.__required_keys__ >= REQUIRED_STATE_FIELDS


def test_append_only_history_channels_have_reducers() -> None:
    annotations = get_type_hints(ScholarPathState, include_extras=True)

    for field_name in (
        "candidate_preferences",
        "raw_search_results",
        "rejected_supervisors",
        "candidate_feedback",
        "tool_errors",
        "search_attempts",
        "execution_log",
    ):
        annotation = annotations[field_name]
        assert get_origin(annotation) is Annotated
        assert len(get_args(annotation)) == 2


def test_compiled_graph_contains_the_current_canonical_nodes() -> None:
    graph_nodes = set(build_scholarpath_graph().get_graph().nodes)

    assert graph_nodes - {"__start__", "__end__"} == set(CANONICAL_NODE_NAMES)
    assert len(CANONICAL_NODE_NAMES) == 16


def test_historical_m2_mermaid_preserves_the_fifteen_node_walking_skeleton() -> None:
    saved = (PROJECT_ROOT / "docs" / "m2-walking-skeleton.mmd").read_text(encoding="utf-8")

    for node_name in M2_CANONICAL_NODE_NAMES:
        historical_name = (
            "candidate_review_gate_stub" if node_name == "candidate_review_gate" else node_name
        )
        assert historical_name in saved


def test_runtime_does_not_import_test_fixtures_or_deferred_integrations() -> None:
    graph_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "src" / "graph").glob("*.py"))
    )
    project_config = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = cast(list[str], project_config["project"]["dependencies"])
    normalized_dependencies = "\n".join(dependencies).casefold()

    assert "tests.fixtures" not in graph_source
    assert "langchain-core>=1.6.0,<2" in dependencies
    assert "langchain-openai>=1.6.0,<2" in dependencies
    assert "langchain-tavily==0.2.17" in dependencies
    assert "langgraph>=1.2.11,<2" in dependencies
    assert "langsmith>=0.11.2,<1" in dependencies
    assert "streamlit==1.62.0" in normalized_dependencies


def test_m2_cli_prompt_and_diagram_are_documented() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    assert "python -m scholarpath.cli" in readme
    assert (PROJECT_ROOT / "src" / "cli.py").is_file()
    assert (PROJECT_ROOT / "docs" / "m2-walking-skeleton.mmd").is_file()
    assert (
        PROJECT_ROOT / "docs" / "prompts" / "m2-deterministic-langgraph-walking-skeleton.md"
    ).is_file()
