"""Per-port diagnostics count actual fake work without changing graph outcomes."""

import json

import pytest
from langsmith import tracing_context
from pydantic import ValidationError

from scholarpath.evaluation.measurements import GraphPortInvocationCounts
from scholarpath.evaluation.models import (
    EvaluationScenario,
    EvaluationTargetKind,
    GraphTargetOutput,
)
from scholarpath.evaluation.reviewed_manifest import build_reviewed_manifest
from scholarpath.evaluation.scenarios import evaluation_dataset_inputs
from scholarpath.evaluation.targets import fake_end_to_end_target

_FIELDS = (
    "planning",
    "primary_search",
    "fallback_search",
    "alternate_evidence_search",
    "content_extraction",
    "evidence_model",
    "research_fit",
    "independent_review",
    "memory_load",
    "memory_store",
)
_GRAPH_SCENARIOS = tuple(
    case.scenario
    for case in build_reviewed_manifest().source_draft.cases
    if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
)
_INITIAL = {
    "planning": 1,
    "primary_search": 4,
    "fallback_search": 0,
    "alternate_evidence_search": 0,
    "content_extraction": 8,
    "evidence_model": 8,
    "research_fit": 8,
    "independent_review": 8,
    "memory_load": 1,
    "memory_store": 0,
}


def _observe(graph_case: str) -> tuple[GraphPortInvocationCounts, GraphTargetOutput]:
    scenario = next(
        item for item in _GRAPH_SCENARIOS if item.config.get("graph_case") == graph_case
    )
    observed: list[GraphPortInvocationCounts] = []
    with tracing_context(enabled=False):
        output = fake_end_to_end_target(
            evaluation_dataset_inputs(scenario), port_usage_observer=observed.append
        )
    assert len(observed) == 1
    return observed[0], GraphTargetOutput.model_validate(output)


def test_complete_zero_counts_are_valid_and_sum_to_zero() -> None:
    counts = GraphPortInvocationCounts.model_validate(dict.fromkeys(_FIELDS, 0))

    assert tuple(GraphPortInvocationCounts.model_fields) == _FIELDS
    assert counts.total == 0
    assert counts.model_dump() == dict.fromkeys(_FIELDS, 0)


@pytest.mark.parametrize("invalid", [-1, True, "1", None, 1.5])
def test_every_port_requires_a_nonnegative_strict_integer(invalid: object) -> None:
    for field in _FIELDS:
        data: dict[str, object] = dict.fromkeys(_FIELDS, 0)
        data[field] = invalid

        with pytest.raises(ValidationError) as raised:
            GraphPortInvocationCounts.model_validate(data)

        assert raised.value.errors()[0]["loc"] == (field,)


def test_missing_port_counts_are_unknown_not_silently_defaulted_to_zero() -> None:
    for missing in _FIELDS:
        incomplete = {field: 0 for field in _FIELDS if field != missing}

        with pytest.raises(ValidationError) as raised:
            GraphPortInvocationCounts.model_validate(incomplete)

        assert raised.value.errors()[0]["type"] == "missing"
        assert raised.value.errors()[0]["loc"] == (missing,)


def test_payload_fields_cannot_enter_count_diagnostics() -> None:
    with pytest.raises(ValidationError) as raised:
        GraphPortInvocationCounts.model_validate(
            {**dict.fromkeys(_FIELDS, 0), "candidate_id": "synthetic-private-value"}
        )

    assert raised.value.errors()[0]["type"] == "extra_forbidden"


def test_counts_are_immutable_round_trip_and_have_detached_json_payloads() -> None:
    counts = GraphPortInvocationCounts.model_validate(_INITIAL)
    assert counts.total == sum(_INITIAL.values()) == 38
    assert GraphPortInvocationCounts.model_validate_json(counts.model_dump_json()) == counts
    envelope = json.loads(json.dumps({"ports": counts.model_dump(mode="json")}))
    assert set(envelope["ports"]) == set(_FIELDS)
    assert all(type(value) is int for value in envelope["ports"].values())
    envelope["ports"]["planning"] = 999
    assert counts.planning == 1
    for field in _FIELDS:
        with pytest.raises(ValidationError, match="frozen"):
            setattr(counts, field, 999)
    assert counts.total == 38


@pytest.mark.parametrize("scenario", _GRAPH_SCENARIOS, ids=lambda scenario: scenario.scenario_id)
def test_observing_each_frozen_graph_case_preserves_its_exact_default_output(
    scenario: EvaluationScenario,
) -> None:
    assert len(_GRAPH_SCENARIOS) == 12
    inputs = evaluation_dataset_inputs(scenario)
    original_inputs = json.dumps(inputs, sort_keys=True)
    observed: list[GraphPortInvocationCounts] = []

    with tracing_context(enabled=False):
        baseline = fake_end_to_end_target(inputs)
        with_observer = fake_end_to_end_target(inputs, port_usage_observer=observed.append)

    assert with_observer == baseline
    assert len(observed) == 1
    counts = observed[0]
    output = GraphTargetOutput.model_validate(with_observer)
    assert counts.total == output.measurements.port_invocations
    assert counts.total == sum(counts.model_dump().values())
    assert json.dumps(inputs, sort_keys=True) == original_inputs
    assert set(counts.model_dump()) == set(_FIELDS)
    assert "port_usage_observer" not in with_observer


def test_initial_review_pause_does_not_write_candidate_memory() -> None:
    counts, output = _observe("approval_pause")

    assert counts.model_dump() == _INITIAL
    assert counts.total == 38
    assert output.interrupted is True
    assert output.candidate_reviews == ()
    assert output.shortlisted_supervisor_ids == ()
    assert counts.memory_store == 0


def test_request_more_counts_both_rounds_and_one_explicit_preference_write() -> None:
    counts, output = _observe("request_more")

    assert counts.model_dump() == {
        **_INITIAL,
        "planning": 2,
        "primary_search": 8,
        "content_extraction": 16,
        "evidence_model": 16,
        "research_fit": 16,
        "independent_review": 16,
        "memory_store": 1,
    }
    assert counts.total == 76
    assert output.interrupted is True
    assert len(output.candidate_reviews) == 1
    assert output.candidate_reviews[0].action.value == "request_more"
    assert output.shortlisted_supervisor_ids == ()


def test_failed_you_calls_and_bounded_tavily_fallback_remain_counted() -> None:
    counts, output = _observe("you_timeout_tavily")

    assert counts.model_dump() == {
        **_INITIAL,
        "primary_search": 2,
        "fallback_search": 3,
        "content_extraction": 6,
        "evidence_model": 6,
        "research_fit": 6,
        "independent_review": 6,
    }
    assert counts.total == 31
    assert output.fallback_search_used is True
    assert sum(item.error_category is not None for item in output.search_attempts) == 2


def test_failed_extraction_counts_the_attempt_not_an_unexecuted_model_call() -> None:
    counts, output = _observe("extraction_failure")

    assert counts.model_dump() == {
        **_INITIAL,
        "alternate_evidence_search": 1,
        "evidence_model": 7,
        "research_fit": 7,
        "independent_review": 7,
    }
    assert counts.content_extraction == 8
    assert counts.total == 36
    assert output.tool_error_codes


def test_separate_observer_invocations_do_not_accumulate_other_run_counts() -> None:
    first, _ = _observe("request_more")
    second, _ = _observe("approval_pause")

    assert first.total == 76
    assert second.total == 38
    assert first.memory_store == 1
    assert second.memory_store == 0
