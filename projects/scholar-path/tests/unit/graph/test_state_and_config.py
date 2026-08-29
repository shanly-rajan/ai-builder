"""Unit tests for M2 graph reducers, state construction, and fixture controls."""

from collections.abc import Callable

import pytest
from pydantic import ValidationError

from scholarpath.agents import ResearchPlanningAgent
from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.domain import (
    CandidateReviewAction,
    CandidateReviewDecision,
    SupervisorLifecycleStatus,
    apply_candidate_review,
)
from scholarpath.graph import (
    DiscoveryPolicy,
    GraphFixtureConfig,
    RawSupervisorSearchResult,
    ReviewStatus,
    ScholarPathState,
    append_items,
    build_walking_skeleton_fixtures,
    create_initial_state,
    merge_supervisors_by_id,
    run_scholarpath_graph,
)
from scholarpath.graph.workflow import DeterministicScholarPathNodes
from tests.fakes import FakePlanningModel, FakeSupervisorSearch

FIXTURE_IDS = tuple(
    supervisor.supervisor_id
    for supervisor in build_walking_skeleton_fixtures().verified_supervisors
)


def _run_graph(config: GraphFixtureConfig | None = None) -> ScholarPathState:
    return run_scholarpath_graph(
        config,
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.OFF,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
    )


def test_append_reducer_returns_a_new_list_without_mutating_inputs() -> None:
    left = ["first"]
    right = ["second"]

    merged = append_items(left, right)

    assert merged == ["first", "second"]
    assert left == ["first"]
    assert right == ["second"]
    assert merged is not left
    assert merged is not right


def test_supervisor_reducer_replaces_existing_id_and_appends_new_id() -> None:
    fixtures = build_walking_skeleton_fixtures()
    first, second = fixtures.verified_supervisors[:2]
    rejection = CandidateReviewDecision(
        action=CandidateReviewAction.REJECT,
        supervisor_ids=(first.supervisor_id,),
        reason="The Candidate rejected this fixture record.",
    )
    rejected_first = apply_candidate_review(first, rejection)

    merged = merge_supervisors_by_id([first], [rejected_first, second])

    assert [item.supervisor_id for item in merged] == [first.supervisor_id, second.supervisor_id]
    assert merged[0].status is SupervisorLifecycleStatus.REJECTED
    assert first.status is SupervisorLifecycleStatus.VERIFIED


def test_initial_state_populates_every_channel_with_safe_defaults() -> None:
    fixtures = build_walking_skeleton_fixtures()

    state = create_initial_state(fixtures.candidate_profile)

    assert state["candidate_profile"] == fixtures.candidate_profile
    assert state["retry_counts"] == {"discovery": 0, "evidence": 0, "review": 0}
    assert state["review_status"] is ReviewStatus.PENDING
    assert state["search_plan"] is None
    assert state["supervisor_shortlist"] is None
    assert state["search_attempts"] == []
    assert state["fallback_search_used"] is False
    assert state["fallback_search_round"] is None
    assert state["discovery_round"] == 0
    assert state["execution_log"] == []


def test_raw_search_result_revalidates_during_domain_conversion() -> None:
    fixtures = build_walking_skeleton_fixtures()
    raw = fixtures.raw_search_results[0]

    prospective = raw.to_prospective_supervisor()

    assert prospective.supervisor_id == raw.supervisor_id
    assert str(prospective.profile_url) == str(raw.profile_url)
    assert raw.discovery_round == 1

    with pytest.raises(ValidationError, match="profile_url"):
        RawSupervisorSearchResult.model_validate(
            {**raw.model_dump(mode="python"), "profile_url": "not-a-url"}
        )


@pytest.mark.parametrize(
    ("config_factory", "message"),
    [
        (
            lambda: GraphFixtureConfig(
                discovery_policy=DiscoveryPolicy(minimum_unique_supervisors=0)
            ),
            "greater than or equal to 1",
        ),
        (
            lambda: GraphFixtureConfig(
                discovery_policy=DiscoveryPolicy(maximum_tavily_fallback_count=101)
            ),
            "less than or equal to 100",
        ),
        (
            lambda: GraphFixtureConfig(minimum_verified_supervisors=4),
            "must not be less than shortlist_size",
        ),
        (lambda: GraphFixtureConfig(shortlist_size=4), "must be 5"),
        (lambda: GraphFixtureConfig(max_evidence_retries=-1), "must not be negative"),
        (lambda: GraphFixtureConfig(max_review_retries=6), "must not exceed 5"),
    ],
)
def test_graph_fixture_config_rejects_invalid_controls(
    config_factory: Callable[[], GraphFixtureConfig], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        config_factory()


def test_planning_without_loaded_preferences_uses_candidate_profile_regions() -> None:
    config = GraphFixtureConfig()
    planning_model = FakePlanningModel()
    nodes = DeterministicScholarPathNodes(config, ResearchPlanningAgent(planning_model))
    state = create_initial_state(config.fixtures.candidate_profile)

    update = nodes.plan_supervisor_searches(state)

    search_plan = update.get("search_plan")
    assert search_plan is not None
    assert search_plan.target_regions == config.fixtures.candidate_profile.preferred_regions
    assert (
        planning_model.inputs[0].target_regions
        == config.fixtures.candidate_profile.preferred_regions
    )


def test_invalid_review_scope_stops_safely() -> None:
    invalid_decision = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=("supervisor-999",),
        reason="This fixture deliberately references an unknown Supervisor.",
    )

    final_state = _run_graph(GraphFixtureConfig(review_decisions=(invalid_decision,)))

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["tool_errors"][-1].code == "review_scope_invalid"
    assert final_state["candidate_feedback"] == []


def test_review_retry_limit_stops_before_replanning() -> None:
    request_more = CandidateReviewDecision(
        action=CandidateReviewAction.REQUEST_MORE,
        supervisor_ids=tuple(FIXTURE_IDS[index] for index in (0, 1, 3, 2, 4)),
        reason="The Candidate requested a broader fixture search.",
    )

    final_state = _run_graph(
        GraphFixtureConfig(review_decisions=(request_more,), max_review_retries=0)
    )

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["tool_errors"][-1].code == "review_retry_exhausted"
    assert final_state["execution_log"].count("plan_supervisor_searches") == 1
    assert final_state["retry_counts"]["review"] == 0


def test_partial_approval_cannot_complete_the_five_supervisor_shortlist() -> None:
    partial_approval = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=(FIXTURE_IDS[0],),
        reason="The Candidate approved only one fixture recommendation.",
    )

    final_state = _run_graph(GraphFixtureConfig(review_decisions=(partial_approval,)))

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["tool_errors"][-1].code == "approved_shortlist_incomplete"
    assert final_state["shortlisted_supervisors"] == []
    assert final_state["supervisor_shortlist"] is None


def test_briefing_node_rejects_missing_shortlist() -> None:
    config = GraphFixtureConfig()
    nodes = DeterministicScholarPathNodes(config, ResearchPlanningAgent(FakePlanningModel()))
    state = create_initial_state(config.fixtures.candidate_profile)

    with pytest.raises(ValueError, match="SupervisorShortlist is required"):
        nodes.generate_shortlist_briefing(state)


def test_repeated_default_runs_are_equal() -> None:
    assert _run_graph() == _run_graph()
