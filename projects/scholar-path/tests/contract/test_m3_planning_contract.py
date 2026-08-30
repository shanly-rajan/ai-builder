"""Contract tests for the M3 planning and observability boundaries."""

from pathlib import Path

from pydantic import BaseModel

from scholarpath.agents import (
    RESEARCH_PLANNING_PROMPT_VERSION,
    RESEARCH_PLANNING_SYSTEM_PROMPT_V1,
    RESEARCH_PLANNING_SYSTEM_PROMPT_V2,
    RESEARCH_PLANNING_SYSTEM_PROMPT_V3,
    PlanningModelPort,
    StructuredSearchPlanResponse,
)
from tests.fakes import FakePlanningModel

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]


def test_planning_output_and_fake_satisfy_the_provider_neutral_contract() -> None:
    model: PlanningModelPort = FakePlanningModel()

    assert issubclass(StructuredSearchPlanResponse, BaseModel)
    assert callable(model.generate)
    assert RESEARCH_PLANNING_PROMPT_VERSION == "research-planning-v3"
    assert RESEARCH_PLANNING_SYSTEM_PROMPT_V1 != RESEARCH_PLANNING_SYSTEM_PROMPT_V2
    assert RESEARCH_PLANNING_SYSTEM_PROMPT_V2 != RESEARCH_PLANNING_SYSTEM_PROMPT_V3
    assert "provider-portable" in RESEARCH_PLANNING_SYSTEM_PROMPT_V2
    assert "at most one site:" in RESEARCH_PLANNING_SYSTEM_PROMPT_V2
    assert "Master's or doctoral research-degree interests" in (RESEARCH_PLANNING_SYSTEM_PROMPT_V3)
    assert "explicit research-degree supervision information" in (
        RESEARCH_PLANNING_SYSTEM_PROMPT_V3
    )


def test_openai_adapter_uses_structured_output_without_search_tools_or_prose_parsing() -> None:
    source = (PROJECT_ROOT / "src" / "agents" / "openai_planning.py").read_text(encoding="utf-8")

    assert ".with_structured_output(" in source
    assert 'method="json_schema"' in source
    assert "strict=True" in source
    assert "RESEARCH_PLANNING_SYSTEM_PROMPT_V3" in source
    assert "max_retries=0" in source
    assert "bind_tools" not in source
    assert "json.loads" not in source


def test_m3_environment_and_audit_artifacts_are_present() -> None:
    environment_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for variable_name in (
        "OPENAI_API_KEY",
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
    ):
        assert variable_name in environment_example

    assert (
        PROJECT_ROOT
        / "docs"
        / "prompts"
        / "m3-openai-research-planning-and-langsmith-observability.md"
    ).is_file()
    assert (PROJECT_ROOT / "docs" / "m3-research-planning-graph.mmd").is_file()


def test_default_suite_contains_a_guarded_live_smoke_test() -> None:
    live_test = PROJECT_ROOT / "tests" / "integration" / "test_openai_planning_live.py"
    source = live_test.read_text(encoding="utf-8")

    assert "@pytest.mark.live" in source
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in source
    assert "OPENAI_API_KEY" in source
