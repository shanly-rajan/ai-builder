"""Repository contract for the bounded M13.5 application-logging repair."""

from pathlib import Path

from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    GraphFixtureConfig,
    ScholarPathState,
    VerificationPolicy,
)
from scholarpath.observability import (
    GRAPH_LOG_NODE_NAMES,
    LOG_SCHEMA_VERSION,
    SAFE_PROVIDER_METADATA_KEYS,
    SCHOLARPATH_STATE_FIELDS,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m13_5_prompt_and_active_documentation_describe_safe_logging() -> None:
    prompt_path = PROJECT_ROOT / "docs/prompts/m13-5-privacy-safe-graph-logging.md"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    reliability = (PROJECT_ROOT / "docs/reliability-review.md").read_text(encoding="utf-8")
    build_journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt_path.is_file()
    prompt = " ".join(prompt_path.read_text(encoding="utf-8").split())
    assert "Milestone M13.5 Prompt: Privacy-safe graph execution logging" in prompt
    assert "every ScholarPath graph node" in prompt
    assert "M13.5 privacy-safe graph execution logging" in readme
    assert "provider.lifecycle" in readme
    assert "## M13.5 privacy-safe application logging boundary" in architecture
    assert "Privacy-safe local graph logging is always available" in reliability
    assert "## M13.5 Repair: Privacy-safe graph execution logging" in build_journal


def test_m13_5_logging_schema_fails_closed_for_state_and_provider_metadata() -> None:
    assert LOG_SCHEMA_VERSION == 1
    assert ScholarPathState.__required_keys__ == SCHOLARPATH_STATE_FIELDS
    assert {"__start__", "__end__", *CANONICAL_NODE_NAMES} == GRAPH_LOG_NODE_NAMES
    assert {
        "api_key",
        "candidate_id",
        "critique",
        "query",
        "source_url",
        "thread_id",
    }.isdisjoint(SAFE_PROVIDER_METADATA_KEYS)


def test_m13_5_wraps_each_canonical_node_and_each_conditional_router_once() -> None:
    workflow_source = (PROJECT_ROOT / "src/graph/workflow.py").read_text(encoding="utf-8")

    assert workflow_source.count("execution_logger.wrap_node(") == len(CANONICAL_NODE_NAMES)
    assert workflow_source.count("execution_logger.wrap_conditional_route(") == 5


def test_m13_5_preserves_verification_retry_and_shortlist_thresholds() -> None:
    policy = VerificationPolicy()
    graph_config = GraphFixtureConfig()

    assert policy.minimum_verified_supervisors == 5
    assert policy.maximum_alternate_source_retries == 1
    assert graph_config.shortlist_size == 5
