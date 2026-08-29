"""Unit tests for M2 graph reducers, state construction, and fixture controls."""

from collections.abc import Callable, Sequence
from datetime import datetime
from typing import cast

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
    CandidatePreferenceRevision,
    CandidateReviewAction,
    CandidateReviewDecision,
    SupervisorLifecycleStatus,
    apply_candidate_review,
)
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRequestMoreResponse,
    CandidateReviewResponse,
    DiscoveryPolicy,
    GraphFixtureConfig,
    RawSupervisorSearchResult,
    ReviewStatus,
    ScholarPathState,
    UtcClockPort,
    VerificationPolicy,
    append_items,
    build_walking_skeleton_fixtures,
    create_initial_state,
    default_review_decision,
    merge_supervisors_by_id,
    run_scholarpath_graph,
)
from scholarpath.graph.workflow import DeterministicScholarPathNodes
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
)

FIXTURE_IDS = tuple(
    supervisor.supervisor_id
    for supervisor in build_walking_skeleton_fixtures().verified_supervisors
)


class _FixedUtcClock:
    """Keep offline walking-skeleton runs reproducible."""

    def __init__(self, timestamp: datetime) -> None:
        self._timestamp = timestamp

    def now(self) -> datetime:
        return self._timestamp


def _run_graph(
    config: GraphFixtureConfig | None = None,
    *,
    candidate_review_responses: Sequence[CandidateReviewResponse] | None = None,
) -> ScholarPathState:
    resolved_config = config or GraphFixtureConfig()
    utc_clock: UtcClockPort = _FixedUtcClock(resolved_config.fixtures.generated_at)
    default_approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )
    return cast(
        ScholarPathState,
        run_scholarpath_graph(
            resolved_config,
            thread_id="legacy-state-and-config",
            candidate_review_responses=candidate_review_responses or (default_approval,),
            planning_model=FakePlanningModel(),
            supervisor_search=FakeSupervisorSearch(),
            content_extractor=FakeContentExtraction(),
            evidence_model=FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=DiscoveryFailureMode.OFF,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
            utc_clock=utc_clock,
        ),
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
    assert state["retry_counts"] == {
        "discovery": 0,
        "evidence": 0,
        "review": 0,
        "review_input": 0,
    }
    assert state["review_status"] is ReviewStatus.PENDING
    assert state["search_plan"] is None
    assert state["supervisor_shortlist"] is None
    assert state["proposed_shortlist"] is None
    assert state["search_attempts"] == []
    assert state["verification_records"] == []
    assert state["research_fit_review_records"] == []
    assert state["candidate_review_error"] is None
    assert state["evidence_extraction_attempts"] == []
    assert state["alternate_evidence_sources"] == {}
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
            lambda: GraphFixtureConfig(
                verification_policy=VerificationPolicy(minimum_verified_supervisors=4)
            ),
            "must not be less than shortlist_size",
        ),
        (lambda: GraphFixtureConfig(shortlist_size=4), "must be 5"),
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
    nodes = DeterministicScholarPathNodes(
        config,
        ResearchPlanningAgent(planning_model),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
    )
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
    invalid_response = CandidateApproveResponse(
        action="approve",
        supervisor_ids=("supervisor-999",),
    )

    final_state = _run_graph(
        GraphFixtureConfig(max_review_input_retries=1),
        candidate_review_responses=(invalid_response,),
    )

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["tool_errors"][-1].code == "review_scope_invalid"
    assert final_state["candidate_feedback"] == []


def test_review_retry_limit_stops_before_replanning() -> None:
    request_more = CandidateRequestMoreResponse(
        action="request_more",
        revised_preferences=CandidatePreferenceRevision(
            preferred_regions=("Netherlands",),
        ),
    )

    final_state = _run_graph(
        GraphFixtureConfig(max_review_retries=0),
        candidate_review_responses=(request_more,),
    )

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["tool_errors"][-1].code == "review_retry_exhausted"
    assert final_state["execution_log"].count("plan_supervisor_searches") == 1
    assert final_state["retry_counts"]["review"] == 0


def test_explicit_partial_approval_shortlists_only_the_selected_supervisor() -> None:
    partial_approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=(FIXTURE_IDS[0],),
    )

    final_state = _run_graph(candidate_review_responses=(partial_approval,))

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert [item.supervisor_id for item in final_state["shortlisted_supervisors"]] == [
        FIXTURE_IDS[0]
    ]
    assert final_state["supervisor_shortlist"] is not None


def test_briefing_node_rejects_missing_shortlist() -> None:
    config = GraphFixtureConfig()
    nodes = DeterministicScholarPathNodes(
        config,
        ResearchPlanningAgent(FakePlanningModel()),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
    )
    state = create_initial_state(config.fixtures.candidate_profile)

    with pytest.raises(ValueError, match="SupervisorShortlist is required"):
        nodes.generate_shortlist_briefing(state)


def test_repeated_default_runs_are_equal() -> None:
    assert _run_graph() == _run_graph()
