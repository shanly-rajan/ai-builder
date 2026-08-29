"""Repository contracts for M4 You.com Supervisor discovery."""

import tomllib
from pathlib import Path

from pydantic import BaseModel

from scholarpath.agents import SupervisorDiscoveryResult
from scholarpath.domain import SearchResult
from scholarpath.graph import render_scholarpath_mermaid
from scholarpath.tools import SupervisorSearchPort
from tests.fakes import FakeSupervisorSearch

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"


def test_m4_boundaries_use_typed_structured_contracts() -> None:
    assert issubclass(SearchResult, BaseModel)
    assert issubclass(SupervisorDiscoveryResult, BaseModel)
    assert isinstance(FakeSupervisorSearch(), SupervisorSearchPort)

    output_properties = SupervisorDiscoveryResult.model_json_schema()["properties"]
    assert set(output_properties) == {
        "prospective_supervisors",
        "result_count",
        "plausible_supervisor_count",
        "duplicate_result_count",
    }


def test_you_adapter_is_transport_only() -> None:
    source = (SOURCE_ROOT / "tools" / "you_search.py").read_text(encoding="utf-8")

    assert "https://ydc-index.io/v1/search" not in source
    assert "SearchResult" in source
    for forbidden_domain_type in (
        "ProspectiveSupervisor",
        "ResearchFitAssessment",
        "AvailabilityStatus",
        "SupervisorDiscoveryAgent",
    ):
        assert forbidden_domain_type not in source


def test_m4_you_adapter_stays_transport_only_after_tavily_is_added() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = pyproject["project"]["dependencies"]
    you_source = (SOURCE_ROOT / "tools" / "you_search.py").read_text(encoding="utf-8").casefold()

    assert "httpx>=0.28,<1" in dependencies
    assert "langchain-tavily==0.2.17" in dependencies
    assert "tavily" not in you_source
    assert "langchain_community" not in you_source


def test_m4_environment_prompt_live_guard_and_generated_graph_are_recorded() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    live_test = (PROJECT_ROOT / "tests" / "integration" / "test_you_search_live.py").read_text(
        encoding="utf-8"
    )
    prompt = PROJECT_ROOT / "docs" / "prompts" / "m4-you-com-supervisor-discovery.md"
    mermaid = PROJECT_ROOT / "docs" / "m4-you-com-discovery-graph.mmd"

    assert "YDC_API_KEY=" in env_example
    assert "YOU_SEARCH_TIMEOUT_SECONDS=20" in env_example
    assert "YOU_SEARCH_RESULT_COUNT=10" in env_example
    assert "@pytest.mark.live" in live_test
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in live_test
    assert "YDC_API_KEY" in live_test
    assert prompt.is_file()
    assert mermaid.is_file()
    assert "discover_prospective_supervisors" in mermaid.read_text(encoding="utf-8")
    assert "discover_prospective_supervisors" in render_scholarpath_mermaid()
