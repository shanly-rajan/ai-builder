"""Contract tests for M8 independent Research Fit review and reconciliation."""

from pathlib import Path

from pydantic import BaseModel

from scholarpath.agents import (
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    IndependentReviewModelPort,
    IndependentReviewResult,
)
from scholarpath.graph import ScholarPathState, render_scholarpath_mermaid
from tests.fakes import FakeIndependentReviewModel

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]


def test_review_output_and_fake_satisfy_the_provider_neutral_contract() -> None:
    model: IndependentReviewModelPort = FakeIndependentReviewModel()

    assert callable(model.review)
    assert issubclass(IndependentReviewResult, BaseModel)
    assert INDEPENDENT_REVIEW_PROMPT_VERSION == "independent-review-v1"
    assert "research_fit_review_records" in ScholarPathState.__required_keys__


def test_structured_result_cannot_change_forbidden_workflow_state() -> None:
    schema_fields = set(IndependentReviewResult.model_fields)

    assert schema_fields == {
        "decision",
        "recommended_score",
        "unsupported_claim_ids",
        "overlooked_evidence_ids",
        "confidence",
        "critique",
    }
    assert schema_fields.isdisjoint(
        {
            "availability_status",
            "candidate_preferences",
            "admission_probability",
            "proposed_shortlist",
            "shortlisted_supervisors",
        }
    )


def test_nebius_adapter_uses_strict_structured_output_and_configured_endpoint() -> None:
    adapter_source = (PROJECT_ROOT / "src" / "agents" / "nebius_review.py").read_text(
        encoding="utf-8"
    )
    config_source = (PROJECT_ROOT / "src" / "config.py").read_text(encoding="utf-8")

    assert ".with_structured_output(" in adapter_source
    assert 'method="json_schema"' in adapter_source
    assert "include_raw=False" in adapter_source
    assert "strict=True" in adapter_source
    assert "max_retries=0" in adapter_source
    assert "json.loads" not in adapter_source
    assert "api.tokenfactory.nebius.com" not in adapter_source
    assert "Qwen/Qwen3-235B-A22B" not in adapter_source
    assert "https://api.tokenfactory.nebius.com/v1/" in config_source
    assert 'review_model: str = "Qwen/Qwen3-235B-A22B"' in config_source


def test_m8_environment_prompt_diagram_live_test_and_journal_are_recorded() -> None:
    environment_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs" / "build-journal.md").read_text(encoding="utf-8")
    prompt_name = "m8-independent-research-fit-review-nebius.md"
    prompt = PROJECT_ROOT / "docs" / "prompts" / prompt_name
    diagram = PROJECT_ROOT / "docs" / "m8-independent-review-graph.mmd"
    live_test = PROJECT_ROOT / "tests" / "integration" / "test_nebius_review_live.py"

    assert prompt.is_file()
    assert diagram.is_file()
    assert "IndependentReviewModelPort" in journal
    assert prompt_name in journal
    assert "NEBIUS_API_KEY=" in environment_example
    assert "NEBIUS_REVIEW_MODEL=Qwen/Qwen3-235B-A22B" in environment_example
    assert "NEBIUS_ENDPOINT=https://api.tokenfactory.nebius.com/v1/" in environment_example
    live_source = live_test.read_text(encoding="utf-8")
    assert "@pytest.mark.live" in live_source
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in live_source
    assert "NEBIUS_API_KEY" in live_source


def test_m8_mermaid_is_the_current_generated_graph_snapshot() -> None:
    saved = (PROJECT_ROOT / "docs" / "m8-independent-review-graph.mmd").read_text(encoding="utf-8")

    assert saved.strip() == render_scholarpath_mermaid().strip()
