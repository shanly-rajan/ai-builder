"""Contract tests for M7 Research Fit evaluation and preliminary synthesis."""

from pathlib import Path

from pydantic import BaseModel

from scholarpath.agents import (
    RESEARCH_FIT_PROMPT_VERSION,
    ResearchFitModelPort,
    StructuredResearchFitResult,
)
from scholarpath.domain import ResearchFitRubric
from tests.fakes import FakeResearchFitModel

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]


def test_research_fit_output_and_fake_satisfy_the_provider_neutral_contract() -> None:
    model: ResearchFitModelPort = FakeResearchFitModel()

    assert callable(model.evaluate)
    assert issubclass(StructuredResearchFitResult, BaseModel)
    assert RESEARCH_FIT_PROMPT_VERSION == "research-fit-evaluation-v1"


def test_default_rubric_is_the_required_one_hundred_point_contract() -> None:
    rubric = ResearchFitRubric()

    assert rubric.weights == {
        "topic_alignment": 40,
        "methodological_alignment": 20,
        "research_orientation_alignment": 15,
        "recent_research_alignment": 15,
        "practical_constraint_alignment": 10,
    }
    assert sum(rubric.weights.values()) == 100


def test_openai_adapter_uses_native_strict_structured_output_without_prose_parsing() -> None:
    source = (PROJECT_ROOT / "src" / "agents" / "openai_research_fit.py").read_text(
        encoding="utf-8"
    )

    assert ".with_structured_output(" in source
    assert 'method="json_schema"' in source
    assert "include_raw=False" in source
    assert "strict=True" in source
    assert "max_retries=0" in source
    assert "json.loads" not in source
    assert "bind_tools" not in source


def test_m7_environment_prompt_diagram_live_test_and_journal_are_recorded() -> None:
    environment_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs" / "build-journal.md").read_text(encoding="utf-8")
    prompt = (
        PROJECT_ROOT / "docs" / "prompts" / "m7-research-fit-evaluation-and-shortlist-synthesis.md"
    )
    diagram = PROJECT_ROOT / "docs" / "m7-research-fit-graph.mmd"
    live_test = PROJECT_ROOT / "tests" / "integration" / "test_openai_research_fit_live.py"

    assert prompt.is_file()
    assert diagram.is_file()
    assert "ResearchFitModelPort" in journal
    assert "m7-research-fit-evaluation-and-shortlist-synthesis.md" in journal
    assert "OPENAI_RESEARCH_FIT_MODEL=gpt-5.4-mini" in environment_example
    assert "OPENAI_RESEARCH_FIT_TIMEOUT_SECONDS=60" in environment_example
    live_source = live_test.read_text(encoding="utf-8")
    assert "@pytest.mark.live" in live_source
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in live_source
    assert "OPENAI_API_KEY" in live_source
