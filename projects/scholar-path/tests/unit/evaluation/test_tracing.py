"""Tests for allowlisted, content-free LangSmith evaluation dimensions."""

import json

import pytest
from pydantic import ValidationError

from scholarpath.agents import (
    PlanningInput,
    ResearchPlanningError,
    StructuredSearchPlanResponse,
)
from scholarpath.evaluation import (
    evaluation_dataset_inputs,
    evaluation_scenario_by_id,
    make_search_planning_target,
)
from scholarpath.evaluation.models import CandidateReviewOutcome, EvaluationTargetKind
from scholarpath.evaluation.tracing import (
    EVALUATION_APPLICATION,
    SAFE_EVALUATION_TRACE_METADATA_KEYS,
    EvaluationTraceContext,
    sanitize_evaluation_trace_metadata,
    tag_current_evaluation_run,
)


class CapturingRunTree:
    """Minimal LangSmith run-tree double for trace mutation assertions."""

    def __init__(self) -> None:
        self.tags: list[str] = []
        self.metadata: dict[str, object] = {}

    def add_tags(self, tags: list[str]) -> None:
        self.tags.extend(tags)

    def add_metadata(self, metadata: dict[str, object]) -> None:
        self.metadata.update(metadata)


class FailingPlanningModel:
    """Raise after static evaluation tags should already be attached."""

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        del planning_input
        raise RuntimeError("synthetic planning failure")


def _context(**overrides: object) -> EvaluationTraceContext:
    data: dict[str, object] = {
        "scenario_id": "you-timeout-tavily-fallback",
        "target": EvaluationTargetKind.GRAPH_FAKE,
        "environment": "test",
        "graph_version": "m12.3",
        "prompt_versions": ("planning-v1", "evidence-v1"),
        "model_providers": ("fake", "openai"),
        "fallback_search_used": True,
        "candidate_review_outcome": CandidateReviewOutcome.AWAITING_REVIEW,
    }
    return EvaluationTraceContext.model_validate({**data, **overrides})


def test_trace_context_emits_all_required_filterable_tags() -> None:
    context = _context()

    assert context.tags() == [
        "application:scholarpath",
        "environment:test",
        "graph-version:m12.3",
        "prompt-version:planning-v1",
        "prompt-version:evidence-v1",
        "model-provider:fake",
        "model-provider:openai",
        "fallback-used:true",
        "candidate-review-outcome:awaiting_review",
        "evaluation-target:graph_fake",
    ]
    assert context.metadata() == {
        "application": EVALUATION_APPLICATION,
        "environment": "test",
        "graph_version": "m12.3",
        "prompt_version": "multiple",
        "model_provider": "multiple",
        "fallback_search_used": True,
        "candidate_review_outcome": "awaiting_review",
        "evaluation_target": "graph_fake",
        "evaluation_scenario_id": "you-timeout-tavily-fallback",
    }
    assert tuple(context.metadata()) == SAFE_EVALUATION_TRACE_METADATA_KEYS


def test_single_prompt_and_provider_are_preserved_as_scalar_metadata() -> None:
    context = _context(
        prompt_versions=("research-fit-v1",),
        model_providers=("openai",),
        fallback_search_used=None,
    )

    metadata = context.metadata()

    assert metadata["prompt_version"] == "research-fit-v1"
    assert metadata["model_provider"] == "openai"
    assert "fallback_search_used" not in metadata
    assert "fallback-used:not_applicable" in context.tags()


def test_metadata_sanitizer_drops_unknown_sensitive_and_non_scalar_values() -> None:
    metadata = sanitize_evaluation_trace_metadata(
        {
            "application": "scholarpath",
            "environment": "test",
            "fallback_search_used": False,
            "candidate_name": "Sensitive Person",
            "candidate_email": "sensitive@example.test",
            "api_key": "secret-sentinel",
            "research_statement": "complete statement",
            "source_content": "complete page",
            "model_provider": ["fake", "openai"],
            "graph_version": {"unsafe": "nested"},
        }
    )

    assert metadata == {
        "application": "scholarpath",
        "environment": "test",
        "fallback_search_used": False,
    }


def test_trace_context_rejects_duplicate_dimensions_blank_values_and_extras() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        _context(prompt_versions=("planning-v1", "PLANNING-V1"))
    with pytest.raises(ValidationError):
        _context(scenario_id=" ")
    with pytest.raises(ValidationError, match="extra"):
        EvaluationTraceContext.model_validate(
            {**_context().model_dump(mode="python"), "candidate_email": "hidden@example.test"}
        )


def test_with_outcome_returns_a_new_revalidated_context() -> None:
    initial = _context(
        fallback_search_used=None,
        candidate_review_outcome=CandidateReviewOutcome.NOT_APPLICABLE,
    )

    completed = initial.with_outcome(
        fallback_search_used=True,
        candidate_review_outcome=CandidateReviewOutcome.APPROVE,
    )

    assert initial.fallback_search_used is None
    assert initial.candidate_review_outcome is CandidateReviewOutcome.NOT_APPLICABLE
    assert completed.fallback_search_used is True
    assert completed.candidate_review_outcome is CandidateReviewOutcome.APPROVE


def test_tagging_without_an_active_run_is_a_clean_no_op(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scholarpath.evaluation.tracing.get_current_run_tree",
        lambda: None,
    )

    assert tag_current_evaluation_run(_context()) is False


def test_active_run_receives_only_context_tags_and_allowlisted_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = CapturingRunTree()
    monkeypatch.setattr(
        "scholarpath.evaluation.tracing.get_current_run_tree",
        lambda: run,
    )
    context = _context()

    assert tag_current_evaluation_run(context) is True
    assert run.tags == context.tags()
    assert run.metadata == context.metadata()
    assert set(run.metadata) <= set(SAFE_EVALUATION_TRACE_METADATA_KEYS)


def test_failed_target_retains_static_diagnostic_tags_without_dynamic_outcomes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run = CapturingRunTree()
    monkeypatch.setattr(
        "scholarpath.evaluation.tracing.get_current_run_tree",
        lambda: run,
    )
    scenario = evaluation_scenario_by_id("planning-source-coverage")

    with pytest.raises(ResearchPlanningError):
        make_search_planning_target(FailingPlanningModel())(evaluation_dataset_inputs(scenario))

    assert "application:scholarpath" in run.tags
    assert "evaluation-target:search_planning" in run.tags
    assert "prompt-version:research-planning-v2" in run.tags
    assert "model-provider:fake" in run.tags
    assert not any(tag.startswith("fallback-used:") for tag in run.tags)
    assert not any(tag.startswith("candidate-review-outcome:") for tag in run.tags)
    assert "candidate_review_outcome" not in run.metadata


def test_context_serialization_contains_no_candidate_identity_secret_or_source_content() -> None:
    serialized = json.dumps(
        {"tags": _context().tags(), "metadata": _context().metadata()}
    ).casefold()

    for forbidden in (
        "candidate_id",
        "candidate_name",
        "candidate_email",
        "proposed_research_statement",
        "api_key",
        "provider_secret",
        "full_page_content",
        "source_url",
        "search_query",
        "thread_id",
    ):
        assert forbidden not in serialized
