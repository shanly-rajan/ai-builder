"""Actual graph invocation boundaries distinguish first review from later work."""

import json
from collections.abc import Iterator, Mapping
from contextlib import nullcontext
from dataclasses import dataclass

import pytest
from langchain_core.runnables import RunnableConfig
from langsmith import tracing_context
from pydantic import ValidationError

from scholarpath.config import ApplicationSettings, Environment, LangSmithSettings
from scholarpath.evaluation.measurements import (
    GraphInvocationObservation,
    GraphPortInvocationCounts,
)
from scholarpath.evaluation.models import (
    EvaluationScenario,
    EvaluationTargetKind,
    GraphTargetOutput,
)
from scholarpath.evaluation.reviewed_manifest import build_reviewed_manifest
from scholarpath.evaluation.scenarios import evaluation_dataset_inputs
from scholarpath.evaluation.targets import fake_end_to_end_target
from scholarpath.graph import workflow

_GRAPH_SCENARIOS = tuple(
    case.scenario
    for case in build_reviewed_manifest().source_draft.cases
    if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
)
_INITIAL_COUNTS = {
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


def _observe(graph_case: str) -> tuple[list[GraphInvocationObservation], GraphTargetOutput]:
    scenario = next(
        item for item in _GRAPH_SCENARIOS if item.config.get("graph_case") == graph_case
    )
    observations: list[GraphInvocationObservation] = []
    with tracing_context(enabled=False):
        output = fake_end_to_end_target(
            evaluation_dataset_inputs(scenario),
            invocation_usage_observer=observations.append,
        )
    return observations, GraphTargetOutput.model_validate(output)


def _observation_payload() -> dict[str, object]:
    return {
        "invocation_index": 0,
        "at_candidate_review": True,
        "cumulative_counts": dict(_INITIAL_COUNTS),
    }


@pytest.mark.parametrize("scenario", _GRAPH_SCENARIOS, ids=lambda scenario: scenario.scenario_id)
def test_invocation_observer_preserves_each_frozen_graph_case_output(
    scenario: EvaluationScenario,
) -> None:
    assert len(_GRAPH_SCENARIOS) == 12
    inputs = evaluation_dataset_inputs(scenario)
    original_inputs = json.dumps(inputs, sort_keys=True)
    observed: list[GraphInvocationObservation] = []
    final_counts: list[GraphPortInvocationCounts] = []

    with tracing_context(enabled=False):
        baseline = fake_end_to_end_target(inputs)
        observed_output = fake_end_to_end_target(
            inputs,
            invocation_usage_observer=observed.append,
            port_usage_observer=final_counts.append,
        )

    assert observed_output == baseline
    output = GraphTargetOutput.model_validate(observed_output)
    assert len(observed) == len(output.candidate_reviews) + 1
    assert [item.invocation_index for item in observed] == list(range(len(observed)))
    assert len(final_counts) == 1
    assert observed[-1].cumulative_counts == final_counts[0]
    assert observed[-1].cumulative_counts.total == output.measurements.port_invocations
    assert observed[-1].at_candidate_review is output.interrupted
    assert json.dumps(inputs, sort_keys=True) == original_inputs
    assert "invocation_usage_observer" not in observed_output


def test_first_review_measures_no_unapproved_memory_writes_or_shortlist_save() -> None:
    observed, output = _observe("approval_pause")

    assert len(observed) == 1
    assert observed[0].cumulative_counts.model_dump() == _INITIAL_COUNTS
    assert observed[0].cumulative_counts.total == 38
    assert observed[0].at_candidate_review is True
    assert output.candidate_reviews == ()
    assert output.shortlisted_supervisor_ids == ()


def test_request_more_measures_two_real_boundaries_and_the_feedback_write() -> None:
    observed, output = _observe("request_more")

    assert [item.cumulative_counts.total for item in observed] == [38, 76]
    assert [item.cumulative_counts.memory_store for item in observed] == [0, 1]
    assert [item.cumulative_counts.memory_load for item in observed] == [1, 1]
    assert [item.cumulative_counts.planning for item in observed] == [1, 2]
    assert [item.at_candidate_review for item in observed] == [True, True]
    assert observed[0].cumulative_counts.model_dump() == _INITIAL_COUNTS
    delta = {
        port: observed[1].cumulative_counts.model_dump()[port] - count
        for port, count in observed[0].cumulative_counts.model_dump().items()
    }
    assert delta == {**_INITIAL_COUNTS, "memory_load": 0, "memory_store": 1}
    assert sum(delta.values()) == 38
    assert output.candidate_reviews[0].action.value == "request_more"
    assert output.shortlisted_supervisor_ids == ()


@pytest.mark.parametrize("graph_case", ["approve_one", "approve_subset"])
def test_approval_resume_adds_only_the_observed_preference_write(graph_case: str) -> None:
    observed, output = _observe(graph_case)

    assert [item.cumulative_counts.total for item in observed] == [38, 39]
    assert [item.at_candidate_review for item in observed] == [True, False]
    assert observed[-1].cumulative_counts.model_dump() == {**_INITIAL_COUNTS, "memory_store": 1}
    assert output.interrupted is False
    assert output.shortlisted_supervisor_ids


def test_rejection_then_approval_measures_each_resume_without_replaying_search() -> None:
    observed, output = _observe("reject_then_approve")

    assert [item.invocation_index for item in observed] == [0, 1, 2]
    assert [item.cumulative_counts.total for item in observed] == [38, 39, 40]
    assert [item.cumulative_counts.memory_store for item in observed] == [0, 1, 2]
    assert [item.cumulative_counts.planning for item in observed] == [1, 1, 1]
    assert [item.at_candidate_review for item in observed] == [True, True, False]
    assert output.interrupted is False
    assert output.shortlisted_supervisor_ids
    assert set(output.rejected_supervisor_ids).isdisjoint(output.shortlisted_supervisor_ids)


def test_failed_provider_retries_are_included_before_the_first_review() -> None:
    observed, output = _observe("you_timeout_tavily")

    assert len(observed) == 1
    counts = observed[0].cumulative_counts
    assert counts.primary_search == 2
    assert counts.fallback_search == 3
    assert counts.total == 31
    assert observed[0].at_candidate_review is True
    assert sum(item.error_category is not None for item in output.search_attempts) == 2


def test_final_count_observer_runs_after_all_invocation_observations() -> None:
    scenario = next(
        item for item in _GRAPH_SCENARIOS if item.config.get("graph_case") == "request_more"
    )
    events: list[tuple[str, int]] = []
    with tracing_context(enabled=False):
        fake_end_to_end_target(
            evaluation_dataset_inputs(scenario),
            invocation_usage_observer=lambda item: events.append(
                ("invocation", item.cumulative_counts.total)
            ),
            port_usage_observer=lambda item: events.append(("whole_case", item.total)),
        )

    assert events == [("invocation", 38), ("invocation", 76), ("whole_case", 76)]


def test_new_runs_reset_invocation_indices_and_do_not_mutate_old_observations() -> None:
    first, _ = _observe("request_more")
    saved_first = tuple(item.model_dump_json() for item in first)
    second, _ = _observe("approval_pause")

    assert [item.invocation_index for item in first] == [0, 1]
    assert [item.invocation_index for item in second] == [0]
    assert second[0].cumulative_counts.total == 38
    assert saved_first == tuple(item.model_dump_json() for item in first)


def test_observations_have_only_closed_numeric_counters_and_a_review_boundary_flag() -> None:
    observed, _ = _observe("request_more")

    assert tuple(GraphInvocationObservation.model_fields) == (
        "invocation_index",
        "at_candidate_review",
        "cumulative_counts",
    )
    for item in observed:
        data = item.model_dump(mode="json")
        assert type(data["invocation_index"]) is int
        assert type(data["at_candidate_review"]) is bool
        assert set(data["cumulative_counts"]) == set(_INITIAL_COUNTS)
        assert all(type(value) is int for value in data["cumulative_counts"].values())


@pytest.mark.parametrize(
    "missing", ["invocation_index", "at_candidate_review", "cumulative_counts"]
)
def test_observation_requires_all_boundary_fields(missing: str) -> None:
    data = _observation_payload()
    data.pop(missing)

    with pytest.raises(ValidationError) as raised:
        GraphInvocationObservation.model_validate(data)

    assert raised.value.errors()[0]["loc"] == (missing,)
    assert raised.value.errors()[0]["type"] == "missing"


@pytest.mark.parametrize("invalid", [-1, True, "1", None, 0.5])
def test_invocation_index_requires_a_nonnegative_strict_integer(invalid: object) -> None:
    with pytest.raises(ValidationError) as raised:
        GraphInvocationObservation.model_validate(
            {**_observation_payload(), "invocation_index": invalid}
        )

    assert raised.value.errors()[0]["loc"] == ("invocation_index",)


@pytest.mark.parametrize("invalid", [0, 1, "true", None, []])
def test_review_boundary_requires_an_explicit_boolean(invalid: object) -> None:
    with pytest.raises(ValidationError) as raised:
        GraphInvocationObservation.model_validate(
            {**_observation_payload(), "at_candidate_review": invalid}
        )

    assert raised.value.errors()[0]["loc"] == ("at_candidate_review",)


@pytest.mark.parametrize("invalid", [{}, None, {**_INITIAL_COUNTS, "planning": -1}])
def test_cumulative_counters_cannot_be_absent_empty_or_invalid(invalid: object) -> None:
    with pytest.raises(ValidationError):
        GraphInvocationObservation.model_validate(
            {**_observation_payload(), "cumulative_counts": invalid}
        )


@pytest.mark.parametrize("field", ["candidate_id", "source_url", "state", "api_key"])
def test_payload_data_is_forbidden_at_the_observation_boundary(field: str) -> None:
    with pytest.raises(ValidationError) as raised:
        GraphInvocationObservation.model_validate(
            {**_observation_payload(), field: "synthetic-private-value"}
        )

    assert raised.value.errors()[0]["loc"] == (field,)
    assert raised.value.errors()[0]["type"] == "extra_forbidden"


def test_observation_and_nested_counts_are_frozen_and_round_trip() -> None:
    observation = GraphInvocationObservation.model_validate(_observation_payload())
    assert (
        GraphInvocationObservation.model_validate_json(observation.model_dump_json()) == observation
    )
    for field, value in (("invocation_index", 10), ("at_candidate_review", False)):
        with pytest.raises(ValidationError, match="frozen"):
            setattr(observation, field, value)
    with pytest.raises(ValidationError, match="frozen"):
        observation.cumulative_counts.planning = 999
    data = observation.model_dump()
    data["cumulative_counts"]["planning"] = 999
    assert observation.cumulative_counts.planning == 1


def test_nested_port_counters_reject_payload_data() -> None:
    with pytest.raises(ValidationError) as raised:
        GraphInvocationObservation.model_validate(
            {
                **_observation_payload(),
                "cumulative_counts": {**_INITIAL_COUNTS, "source_text": "synthetic-private-value"},
            }
        )

    assert raised.value.errors()[0]["loc"] == ("cumulative_counts", "source_text")
    assert raised.value.errors()[0]["type"] == "extra_forbidden"


@dataclass
class _StubGraph:
    outcomes: Iterator[object]
    calls: int = 0

    def invoke(self, _input: object, *, config: RunnableConfig) -> object:
        self.calls += 1
        result = next(self.outcomes)
        if isinstance(result, Exception):
            raise result
        return result


class _StubObservability:
    def activate(self) -> nullcontext[None]:
        return nullcontext()


@dataclass
class _StubRuntime:
    graph: _StubGraph
    observability: _StubObservability

    def runnable_config(self, thread_id: str) -> RunnableConfig:
        return {"configurable": {"thread_id": thread_id}}


def _stub_runtime(monkeypatch: pytest.MonkeyPatch, *outcomes: object) -> _StubGraph:
    graph = _StubGraph(iter(outcomes))
    runtime = _StubRuntime(graph, _StubObservability())
    monkeypatch.setattr(workflow, "build_scholarpath_runtime", lambda *_args, **_kwargs: runtime)
    monkeypatch.setattr(
        workflow,
        "candidate_review_payload_from_graph_output",
        lambda output: (
            object() if isinstance(output, Mapping) and output.get("review_pause") is True else None
        ),
    )
    return graph


@pytest.mark.parametrize("terminal_output", [{"completed": True}, "terminal-non-mapping"])
def test_graph_hook_does_not_report_responses_that_never_execute(
    monkeypatch: pytest.MonkeyPatch, terminal_output: object
) -> None:
    graph = _stub_runtime(monkeypatch, terminal_output)
    boundaries: list[bool] = []

    result = workflow.run_scholarpath_graph(
        thread_id="test-unused-resume",
        candidate_review_responses=({"action": "request_more"},),
        application_settings=ApplicationSettings(environment=Environment.TEST),
        langsmith_settings=LangSmithSettings(tracing=False),
        on_invocation_complete=boundaries.append,
    )

    assert result == terminal_output
    assert graph.calls == 1
    assert boundaries == [False]


def test_graph_hook_does_not_report_a_failed_initial_invoke(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _stub_runtime(monkeypatch, RuntimeError("synthetic invocation failure"))
    boundaries: list[bool] = []

    with pytest.raises(RuntimeError, match="synthetic invocation failure"):
        workflow.run_scholarpath_graph(
            thread_id="test-failed-invoke",
            application_settings=ApplicationSettings(environment=Environment.TEST),
            langsmith_settings=LangSmithSettings(tracing=False),
            on_invocation_complete=boundaries.append,
        )

    assert graph.calls == 1
    assert boundaries == []


def test_graph_hook_preserves_first_boundary_when_a_resume_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _stub_runtime(
        monkeypatch,
        {"review_pause": True},
        RuntimeError("synthetic resume failure"),
    )
    boundaries: list[bool] = []

    with pytest.raises(RuntimeError, match="synthetic resume failure"):
        workflow.run_scholarpath_graph(
            thread_id="test-failed-resume",
            candidate_review_responses=({"action": "request_more"},),
            application_settings=ApplicationSettings(environment=Environment.TEST),
            langsmith_settings=LangSmithSettings(tracing=False),
            on_invocation_complete=boundaries.append,
        )

    assert graph.calls == 2
    assert boundaries == [True]


def test_observer_failure_cannot_silently_report_a_successful_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    graph = _stub_runtime(monkeypatch, {"review_pause": True}, {"completed": True})

    def fail_observation(_at_candidate_review: bool) -> None:
        raise RuntimeError("synthetic observation failure")

    with pytest.raises(RuntimeError, match="synthetic observation failure"):
        workflow.run_scholarpath_graph(
            thread_id="test-failed-observer",
            candidate_review_responses=({"action": "approve"},),
            application_settings=ApplicationSettings(environment=Environment.TEST),
            langsmith_settings=LangSmithSettings(tracing=False),
            on_invocation_complete=fail_observation,
        )

    assert graph.calls == 1
