"""Repository contract for the bounded M13.11 Research Planning repair."""

from pathlib import Path

from scholarpath.agents import StructuredSearchPlanResponse
from scholarpath.agents.research_planning import MAX_PLANNING_OUTPUT_ATTEMPTS

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_planning_repair_prompt_and_architecture_are_documented() -> None:
    prompt = (
        PROJECT_ROOT / "docs" / "prompts" / "m13-11-research-planning-resilience.md"
    ).read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "the MVP research run was working but now its not" in prompt
    assert "## M13.11 Research Planning resilience repair" in architecture
    assert "safe quote normalization".casefold() in readme.casefold()


def test_native_array_bounds_and_visible_retry_ceiling_are_fixed() -> None:
    schema = StructuredSearchPlanResponse.model_json_schema()
    query_schema = schema["properties"]["search_queries"]

    assert query_schema["minItems"] == 4
    assert query_schema["maxItems"] == 8
    assert MAX_PLANNING_OUTPUT_ATTEMPTS == 2


def test_planning_adapter_has_no_hidden_provider_retry_or_prose_parser() -> None:
    adapter = (PROJECT_ROOT / "src" / "agents" / "openai_planning.py").read_text(encoding="utf-8")
    planning = (PROJECT_ROOT / "src" / "agents" / "research_planning.py").read_text(
        encoding="utf-8"
    )

    assert "max_retries=0" in adapter
    assert "json.loads" not in adapter
    assert "emit_provider_event" in adapter
    assert "_normalize_excess_quote_marks" in planning
    assert "_remove_extra_boolean_operators" not in planning
    assert "_remove_extra_site_filters" not in planning
