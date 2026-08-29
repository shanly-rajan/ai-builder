"""Repository contracts for M5 resilient Supervisor discovery."""

import inspect
import tomllib
from pathlib import Path

from pydantic import BaseModel

from scholarpath.config import ApplicationSettings, DiscoveryFailureMode
from scholarpath.graph import (
    DiscoveryPolicy,
    ScholarPathState,
    SearchAttempt,
    render_scholarpath_mermaid,
    route_after_supervisor_discovery,
)
from scholarpath.graph.workflow import DeterministicScholarPathNodes

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"


def test_m5_uses_typed_policy_attempt_and_pure_routing_contracts() -> None:
    assert issubclass(SearchAttempt, BaseModel)
    assert issubclass(DiscoveryPolicy, BaseModel)
    assert "state" not in inspect.signature(route_after_supervisor_discovery).parameters
    assert {
        "provider_used",
        "query",
        "attempt_number",
        "result_count",
        "error_category",
    } <= SearchAttempt.model_json_schema()["properties"].keys()


def test_m5_state_retains_search_history_and_fallback_activation() -> None:
    assert {
        "search_attempts",
        "fallback_search_used",
        "fallback_search_round",
        "discovery_round",
    } <= ScholarPathState.__required_keys__


def test_m5_uses_official_tavily_package_without_community_imports() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    tavily_source = (SOURCE_ROOT / "tools" / "tavily_search.py").read_text(encoding="utf-8")

    assert "langchain-tavily==0.2.17" in dependencies
    assert "from langchain_tavily import TavilySearch" in tavily_source
    assert "langchain_community" not in tavily_source


def test_m5_failure_injection_is_disabled_by_default() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    configured_default = ApplicationSettings.model_fields["discovery_failure_mode"].default

    assert configured_default is DiscoveryFailureMode.OFF
    assert "SCHOLARPATH_DISCOVERY_FAILURE_MODE=off" in env_example


def test_m5_keeps_evidence_extraction_fixture_backed() -> None:
    source = inspect.getsource(DeterministicScholarPathNodes.extract_supervisor_evidence)

    assert "self.config.fixtures.verified_supervisors" in source
    assert ".search(" not in source
    assert "TavilySearchAdapter" not in source
    assert "YouSearchAdapter" not in source


def test_m5_prompt_environment_live_guard_and_generated_graph_are_recorded() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    live_test = (PROJECT_ROOT / "tests/integration/test_tavily_search_live.py").read_text(
        encoding="utf-8"
    )
    prompt = PROJECT_ROOT / "docs/prompts/m5-resilient-supervisor-discovery.md"
    mermaid = PROJECT_ROOT / "docs/m5-resilient-discovery-graph.mmd"

    assert "TAVILY_API_KEY=" in env_example
    assert "TAVILY_SEARCH_TIMEOUT_SECONDS=20" in env_example
    assert "TAVILY_SEARCH_RESULT_COUNT=10" in env_example
    assert "@pytest.mark.live" in live_test
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in live_test
    assert "TAVILY_API_KEY" in live_test
    assert prompt.is_file()
    assert mermaid.read_text(encoding="utf-8") == render_scholarpath_mermaid()
