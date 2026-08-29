"""Graph tests for the injected M3 Research Planning Agent boundary."""

import json

import pytest

from scholarpath.agents import PlanningModelInvocationError, PlanningModelOutputError
from scholarpath.config import ApplicationSettings, Environment, LangSmithSettings
from scholarpath.graph import ReviewStatus, ScholarPathState, run_scholarpath_graph
from tests.fakes import FakePlanningModel, FakeSupervisorSearch


def _run_with_fake(model: FakePlanningModel) -> ScholarPathState:
    return run_scholarpath_graph(
        planning_model=model,
        supervisor_search=FakeSupervisorSearch(),
        application_settings=ApplicationSettings(environment=Environment.TEST),
        langsmith_settings=LangSmithSettings(tracing=False),
    )


def test_terminal_malformed_output_uses_one_retry_and_stops_cleanly() -> None:
    model = FakePlanningModel(
        (
            PlanningModelOutputError("first malformed response"),
            PlanningModelOutputError("second malformed response"),
        )
    )

    final_state = _run_with_fake(model)

    assert model.call_count == 2
    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["execution_log"] == [
        "load_candidate_preferences",
        "plan_supervisor_searches",
    ]
    tool_errors = final_state["tool_errors"]
    assert len(tool_errors) == 1
    assert tool_errors[0].code == "planning_output_invalid"
    assert tool_errors[0].recoverable is False
    assert final_state["search_plan"] is None


def test_model_failure_is_sanitized_in_tool_errors_without_an_unhandled_crash() -> None:
    sensitive_provider_message = (
        "synthetic provider failure containing candidate-sensitive@example.test and secret-key"
    )
    model = FakePlanningModel((PlanningModelInvocationError(sensitive_provider_message),))

    final_state = _run_with_fake(model)

    assert model.call_count == 1
    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    tool_errors = final_state["tool_errors"]
    assert len(tool_errors) == 1
    assert tool_errors[0].node == "plan_supervisor_searches"
    assert tool_errors[0].code == "planning_model_failed"
    assert tool_errors[0].recoverable is False
    assert sensitive_provider_message not in json.dumps(
        [error.model_dump(mode="json") for error in tool_errors]
    )
    assert "discover_prospective_supervisors" not in final_state["execution_log"]


def test_injected_fake_prevents_default_tests_from_constructing_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_openai_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Offline graph tests must not construct the OpenAI adapter")

    monkeypatch.setattr(
        "scholarpath.graph.workflow.OpenAIPlanningModelAdapter",
        fail_if_openai_is_constructed,
    )
    model = FakePlanningModel()

    final_state = _run_with_fake(model)

    assert model.call_count == 1
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["shortlisted_supervisors"]) == 5
