"""Graph integration tests for the injected M4 Supervisor search boundary."""

import json

import pytest

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.graph import (
    DiscoveryPolicy,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    run_scholarpath_graph,
)
from scholarpath.tools import SupervisorSearchTimeoutError
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakePlanningModel,
    FakeSupervisorSearch,
    make_valid_planning_response,
)


def _run_with_fake(
    supervisor_search: FakeSupervisorSearch,
    config: GraphFixtureConfig | None = None,
    tavily_search: FakeSupervisorSearch | None = None,
) -> ScholarPathState:
    return run_scholarpath_graph(
        config,
        planning_model=FakePlanningModel(),
        supervisor_search=supervisor_search,
        tavily_search=tavily_search or FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.OFF,
        ),
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
        GraphFixtureConfig(
            discovery_policy=DiscoveryPolicy(
                maximum_you_retry_count=0,
                maximum_tavily_fallback_count=0,
            )
        ),
    )

    assert final_state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE
    assert final_state["execution_log"] == [
        "load_candidate_preferences",
        "plan_supervisor_searches",
        "discover_prospective_supervisors",
        "enough_supervisors_found",
    ]
    assert [error.code for error in final_state["tool_errors"]] == [
        "you_search_timeout",
        "supervisor_discovery_incomplete",
    ]
    assert all(error.recoverable for error in final_state["tool_errors"])
    serialized_errors = json.dumps(
        [error.model_dump(mode="json") for error in final_state["tool_errors"]]
    )
    assert sensitive_message not in serialized_errors


def test_empty_search_results_follow_existing_fallback_route() -> None:
    empty_search = FakeSupervisorSearch(
        {item.query: () for item in make_valid_planning_response().search_queries}
    )
    final_state = _run_with_fake(empty_search, tavily_search=FakeSupervisorSearch())

    assert final_state["execution_log"][:6] == [
        "load_candidate_preferences",
        "plan_supervisor_searches",
        "discover_prospective_supervisors",
        "enough_supervisors_found",
        "fallback_supervisor_search",
        "enough_supervisors_found",
    ]
    assert final_state["retry_counts"]["discovery"] == 3
    assert len(final_state["prospective_supervisors"]) == 6
