"""Graph integration tests for the injected M4 Supervisor search boundary."""

import json

import pytest

from scholarpath.config import ApplicationSettings, Environment, LangSmithSettings
from scholarpath.graph import (
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    run_scholarpath_graph,
)
from scholarpath.tools import SupervisorSearchTimeoutError
from tests.fakes import (
    FakePlanningModel,
    FakeSupervisorSearch,
    make_valid_planning_response,
)


def _run_with_fake(
    supervisor_search: FakeSupervisorSearch,
    config: GraphFixtureConfig | None = None,
) -> ScholarPathState:
    return run_scholarpath_graph(
        config,
        planning_model=FakePlanningModel(),
        supervisor_search=supervisor_search,
        application_settings=ApplicationSettings(environment=Environment.TEST),
        langsmith_settings=LangSmithSettings(tracing=False),
    )


def test_graph_executes_each_planned_query_once_and_in_plan_order() -> None:
    search = FakeSupervisorSearch()

    final_state = _run_with_fake(search)

    expected_queries = [item.query for item in make_valid_planning_response().search_queries]
    assert search.calls == expected_queries
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["prospective_supervisors"]) == 8
    assert len(final_state["shortlisted_supervisors"]) == 5


def test_injected_fake_prevents_you_adapter_construction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_you_adapter_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Offline graph tests must not construct YouSearchAdapter")

    monkeypatch.setattr(
        "scholarpath.graph.workflow.YouSearchAdapter",
        fail_if_you_adapter_is_constructed,
    )

    final_state = _run_with_fake(FakeSupervisorSearch())

    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_search_failures_are_sanitized_and_stop_through_bounded_routing() -> None:
    sensitive_message = "synthetic timeout with secret-key and private@example.test"
    outcomes = {
        item.query: SupervisorSearchTimeoutError(sensitive_message)
        for item in make_valid_planning_response().search_queries
    }

    final_state = _run_with_fake(
        FakeSupervisorSearch(outcomes),
        GraphFixtureConfig(max_discovery_retries=0),
    )

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["execution_log"] == [
        "load_candidate_preferences",
        "plan_supervisor_searches",
        "discover_prospective_supervisors",
        "enough_supervisors_found",
    ]
    assert [error.code for error in final_state["tool_errors"]] == [
        "supervisor_search_failed",
        "supervisor_search_failed",
        "supervisor_search_failed",
        "supervisor_search_failed",
        "discovery_retry_exhausted",
    ]
    assert all(error.recoverable for error in final_state["tool_errors"][:-1])
    serialized_errors = json.dumps(
        [error.model_dump(mode="json") for error in final_state["tool_errors"]]
    )
    assert sensitive_message not in serialized_errors


def test_empty_search_results_follow_existing_fallback_route() -> None:
    empty_search = FakeSupervisorSearch(
        {item.query: () for item in make_valid_planning_response().search_queries}
    )
    config = GraphFixtureConfig(
        primary_discovery_count=3,
        fallback_discovery_count=5,
    )

    final_state = _run_with_fake(empty_search, config)

    assert final_state["execution_log"][:6] == [
        "load_candidate_preferences",
        "plan_supervisor_searches",
        "discover_prospective_supervisors",
        "enough_supervisors_found",
        "fallback_supervisor_search",
        "enough_supervisors_found",
    ]
    assert final_state["retry_counts"]["discovery"] == 1
    assert len(final_state["prospective_supervisors"]) == 5
