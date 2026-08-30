"""Graph tests for the deterministic ScholarPath M2 walking skeleton."""

from collections.abc import Callable, Sequence
from typing import cast

import pytest

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.domain import (
    CandidatePreferenceRevision,
    CandidateReviewAction,
    ProspectiveSupervisor,
    SupervisorLifecycleStatus,
    SupervisorShortlist,
    VerificationEvidenceStandard,
    VerifiedSupervisor,
)
from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    CandidateApproveResponse,
    CandidateRejectionReason,
    CandidateRejectResponse,
    CandidateRequestMoreResponse,
    CandidateReviewResponse,
    DiscoveryPolicy,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    build_scholarpath_graph,
    build_walking_skeleton_fixtures,
    render_scholarpath_mermaid,
    run_scholarpath_graph,
)
from scholarpath.tools import SearchErrorCategory, SearchProvider, SearchProviderError
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_valid_planning_response,
)

HAPPY_PATH_LOG = [
    "load_candidate_preferences",
    "plan_supervisor_searches",
    "discover_prospective_supervisors",
    "enough_supervisors_found",
    "deduplicate_supervisors",
    "extract_supervisor_evidence",
    "supervisor_evidence_sufficient",
    "evaluate_research_fit",
    "review_fit_assessments",
    "synthesize_supervisor_shortlist",
    "candidate_review_gate",
    "learn_candidate_preferences",
    "save_shortlisted_supervisors",
    "generate_shortlist_briefing",
]
FIXTURE_IDS = tuple(
    supervisor.supervisor_id
    for supervisor in build_walking_skeleton_fixtures().verified_supervisors
)
RANKED_IDS = tuple(FIXTURE_IDS[index] for index in (0, 1, 3, 2, 4))
RANKED_IDS_AFTER_REJECTION = tuple(FIXTURE_IDS[index] for index in (0, 1, 3, 2, 5))


def _run_graph(
    config: GraphFixtureConfig | None = None,
    *,
    planning_model: FakePlanningModel | None = None,
    supervisor_search: FakeSupervisorSearch | None = None,
    tavily_search: FakeSupervisorSearch | None = None,
    content_extractor: FakeContentExtraction | None = None,
    evidence_model: FakeEvidenceVerificationModel | None = None,
    research_fit_model: FakeResearchFitModel | None = None,
    alternate_evidence_search: FakeSupervisorSearch | None = None,
    candidate_review_responses: Sequence[CandidateReviewResponse] | None = None,
) -> ScholarPathState:
    responses = candidate_review_responses or (_approve(),)
    return cast(
        ScholarPathState,
        run_scholarpath_graph(
            config,
            thread_id="legacy-workflow",
            candidate_review_responses=responses,
            planning_model=planning_model or FakePlanningModel(),
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            supervisor_search=supervisor_search or FakeSupervisorSearch(),
            tavily_search=tavily_search or FakeSupervisorSearch(),
            content_extractor=content_extractor or FakeContentExtraction(),
            evidence_model=evidence_model or FakeEvidenceVerificationModel(),
            research_fit_model=research_fit_model or FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            alternate_evidence_search=alternate_evidence_search,
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=DiscoveryFailureMode.OFF,
                verification_evidence_standard=VerificationEvidenceStandard.STRICT,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        ),
    )


def _approve(
    supervisor_ids: tuple[str, ...] = RANKED_IDS,
) -> CandidateApproveResponse:
    return CandidateApproveResponse(
        action="approve",
        supervisor_ids=supervisor_ids,
    )


def _reject(supervisor_ids: tuple[str, ...]) -> CandidateRejectResponse:
    return CandidateRejectResponse(
        action="reject",
        rejections=tuple(
            CandidateRejectionReason(
                supervisor_id=supervisor_id,
                reason=f"The Candidate rejected fixture Supervisor {supervisor_id}.",
            )
            for supervisor_id in supervisor_ids
        ),
    )


def _request_more(
    revised_preferences: CandidatePreferenceRevision | None = None,
) -> CandidateRequestMoreResponse:
    return CandidateRequestMoreResponse(
        action="request_more",
        revised_preferences=revised_preferences
        or CandidatePreferenceRevision(exclusions=("broaden the fixture search",)),
    )


def test_normal_happy_path_has_the_exact_node_sequence() -> None:
    final_state = _run_graph()

    assert final_state["execution_log"] == HAPPY_PATH_LOG
    assert final_state["retry_counts"] == {
        "discovery": 0,
        "evidence": 0,
        "review": 0,
        "review_input": 0,
    }
    assert final_state["tool_errors"] == []
    assert len(final_state["shortlisted_supervisors"]) == 5


def test_insufficient_results_route_through_fallback_search() -> None:
    empty_search = FakeSupervisorSearch(
        {item.query: () for item in make_valid_planning_response().search_queries}
    )

    final_state = _run_graph(
        supervisor_search=empty_search,
        tavily_search=FakeSupervisorSearch(),
    )

    log = final_state["execution_log"]
    assert log[:7] == [
        "load_candidate_preferences",
        "plan_supervisor_searches",
        "discover_prospective_supervisors",
        "enough_supervisors_found",
        "fallback_supervisor_search",
        "enough_supervisors_found",
        "deduplicate_supervisors",
    ]
    assert final_state["retry_counts"]["discovery"] == 3
    assert len(final_state["raw_search_results"]) == 6
    assert len(final_state["prospective_supervisors"]) == 6
    assert len({item.supervisor_id for item in final_state["prospective_supervisors"]}) == 6


def test_candidate_approval_reaches_end_with_shortlisted_statuses() -> None:
    final_state = _run_graph()

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert final_state["execution_log"][-2:] == [
        "save_shortlisted_supervisors",
        "generate_shortlist_briefing",
    ]
    assert final_state["candidate_feedback"][-1].action is CandidateReviewAction.APPROVE
    assert all(
        supervisor.status is SupervisorLifecycleStatus.SHORTLISTED
        for supervisor in final_state["shortlisted_supervisors"]
    )


def test_candidate_rejection_records_feedback_and_reconsiders_existing_shortlist() -> None:
    reject = _reject((FIXTURE_IDS[4],))
    approve_remaining = _approve(RANKED_IDS_AFTER_REJECTION)
    config = GraphFixtureConfig(max_review_retries=1)

    final_state = _run_graph(
        config,
        candidate_review_responses=(reject, approve_remaining),
    )

    rejected = final_state["rejected_supervisors"]
    assert [item.supervisor_id for item in rejected] == [FIXTURE_IDS[4]]
    assert rejected[0].status is SupervisorLifecycleStatus.REJECTED
    assert [decision.action for decision in final_state["candidate_feedback"]] == [
        CandidateReviewAction.REJECT,
        CandidateReviewAction.APPROVE,
    ]
    assert final_state["execution_log"].count("plan_supervisor_searches") == 1
    assert final_state["execution_log"].count("synthesize_supervisor_shortlist") == 2
    assert final_state["execution_log"].count("candidate_review_gate") == 2
    assert final_state["retry_counts"]["review"] == 1
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    shortlisted_ids = tuple(item.supervisor_id for item in final_state["shortlisted_supervisors"])
    assert shortlisted_ids == RANKED_IDS_AFTER_REJECTION
    assert all(
        item.status is SupervisorLifecycleStatus.SHORTLISTED
        for item in final_state["shortlisted_supervisors"]
    )
    assert final_state["supervisor_shortlist"] is not None
    assert final_state["supervisor_shortlist"].shortlisted_supervisors == tuple(
        final_state["shortlisted_supervisors"]
    )


def test_request_more_records_preferences_and_returns_to_search_planning() -> None:
    revision = CandidatePreferenceRevision(preferred_regions=("Netherlands",))
    request_more = _request_more(revision)
    approve = _approve()
    config = GraphFixtureConfig(max_review_retries=1)

    planning_model = FakePlanningModel()
    final_state = _run_graph(
        config,
        planning_model=planning_model,
        candidate_review_responses=(request_more, approve),
    )

    assert [decision.action for decision in final_state["candidate_feedback"]] == [
        CandidateReviewAction.REQUEST_MORE,
        CandidateReviewAction.APPROVE,
    ]
    assert final_state["candidate_preferences"][-1] == revision
    assert final_state["search_plan"] is not None
    assert final_state["search_plan"].target_regions == ("Netherlands",)
    assert planning_model.call_count == 2
    assert planning_model.inputs[-1].target_regions == ("Netherlands",)
    assert final_state["execution_log"].count("plan_supervisor_searches") == 2
    assert final_state["execution_log"].count("candidate_review_gate") == 2
    assert final_state["retry_counts"]["review"] == 1
    assert final_state["rejected_supervisors"] == []
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len({item.supervisor_id for item in final_state["shortlisted_supervisors"]}) == 5
    assert len(final_state["research_fit_review_records"]) == len(
        final_state["research_fit_assessments"]
    )


@pytest.mark.parametrize(
    (
        "config_factory",
        "responses_factory",
        "error_code",
        "last_node",
        "retry_key",
        "retry_node",
        "node_count",
    ),
    [
        (
            lambda: GraphFixtureConfig(max_review_retries=1),
            lambda: (_request_more(), _request_more()),
            "review_retry_exhausted",
            "learn_candidate_preferences",
            "review",
            "plan_supervisor_searches",
            2,
        ),
    ],
)
def test_retry_exhaustion_stops_cleanly_without_recursion_failure(
    config_factory: Callable[[], GraphFixtureConfig],
    responses_factory: Callable[[], tuple[CandidateReviewResponse, ...]],
    error_code: str,
    last_node: str,
    retry_key: str,
    retry_node: str,
    node_count: int,
) -> None:
    final_state = _run_graph(
        config_factory(),
        candidate_review_responses=responses_factory(),
    )

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert len(final_state["tool_errors"]) == 1
    assert final_state["tool_errors"][0].code == error_code
    assert final_state["tool_errors"][0].recoverable is False
    assert final_state["execution_log"][-1] == last_node
    assert final_state["execution_log"].count(retry_node) == node_count
    assert final_state["retry_counts"][retry_key] == 1
    assert "generate_shortlist_briefing" not in final_state["execution_log"]
    assert final_state["supervisor_shortlist"] is None


def test_maximum_configured_discovery_retries_exhaust_through_domain_state() -> None:
    config = GraphFixtureConfig(
        discovery_policy=DiscoveryPolicy(
            maximum_you_retry_count=1,
            maximum_tavily_fallback_count=5,
        )
    )
    first_query = make_valid_planning_response().search_queries[0].query
    you_search = FakeSupervisorSearch(
        scripts={
            first_query: [
                SearchProviderError(
                    "First bounded timeout.",
                    provider=SearchProvider.YOU,
                    category=SearchErrorCategory.TIMEOUT,
                    retryable=True,
                ),
                SearchProviderError(
                    "Second bounded timeout.",
                    provider=SearchProvider.YOU,
                    category=SearchErrorCategory.TIMEOUT,
                    retryable=True,
                ),
            ]
        }
    )
    tavily_search = FakeSupervisorSearch(
        {
            item.query: SearchProviderError(
                "Bounded Tavily provider failure.",
                provider=SearchProvider.TAVILY,
                category=SearchErrorCategory.PROVIDER,
                retryable=True,
            )
            for item in make_valid_planning_response().search_queries
        }
    )

    final_state = _run_graph(
        config,
        supervisor_search=you_search,
        tavily_search=tavily_search,
    )

    assert final_state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE
    assert final_state["retry_counts"]["discovery"] == 6
    assert final_state["execution_log"].count("fallback_supervisor_search") == 1
    assert final_state["execution_log"].count("enough_supervisors_found") == 2
    assert final_state["tool_errors"][-1].code == "supervisor_discovery_incomplete"


def test_maximum_configured_review_retries_exhaust_through_domain_state() -> None:
    request_more = _request_more()
    config = GraphFixtureConfig(max_review_retries=5)

    final_state = _run_graph(
        config,
        candidate_review_responses=(request_more,) * 6,
    )

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["retry_counts"]["review"] == 5
    assert final_state["execution_log"].count("plan_supervisor_searches") == 6
    assert final_state["execution_log"].count("candidate_review_gate") == 6
    assert final_state["tool_errors"][0].code == "review_retry_exhausted"


def test_graph_paths_never_use_candidate_as_a_supervisor_label() -> None:
    graph = build_scholarpath_graph(
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
    ).get_graph()
    graph_node_names = set(graph.nodes)
    candidate_nodes = {name for name in graph_node_names if "candidate" in name.casefold()}

    assert set(CANONICAL_NODE_NAMES) <= graph_node_names
    assert candidate_nodes == {
        "load_candidate_preferences",
        "candidate_review_gate",
        "learn_candidate_preferences",
    }

    mermaid = render_scholarpath_mermaid().casefold()
    for banned_phrase in (
        "supervisor candidate",
        "supervisor_candidate",
        "supervisor-candidate",
        "approved candidate",
    ):
        assert banned_phrase not in mermaid

    final_state = _run_graph()
    proposal = final_state["proposed_shortlist"]
    assert proposal is not None
    proposed_supervisors = [
        recommendation.supervisor for recommendation in proposal.recommendations
    ]
    supervisor_collections: tuple[list[ProspectiveSupervisor] | list[VerifiedSupervisor], ...] = (
        final_state["prospective_supervisors"],
        final_state["verified_supervisors"],
        proposed_supervisors,
        final_state["shortlisted_supervisors"],
        final_state["rejected_supervisors"],
    )
    assert all(
        "candidate" not in supervisor.supervisor_id.casefold()
        for collection in supervisor_collections
        for supervisor in collection
    )
    assert all(
        isinstance(supervisor, ProspectiveSupervisor)
        for supervisor in final_state["prospective_supervisors"]
    )
    assert all(
        isinstance(supervisor, VerifiedSupervisor)
        for collection in supervisor_collections[1:]
        for supervisor in collection
    )


def test_final_state_satisfies_supervisor_shortlist_validation() -> None:
    final_state = _run_graph()
    shortlist = final_state["supervisor_shortlist"]

    assert shortlist is not None
    restored = SupervisorShortlist.model_validate_json(shortlist.model_dump_json())
    assert restored == shortlist
    assert restored.candidate_id == final_state["candidate_profile"].candidate_id
    assert tuple(item.supervisor_id for item in restored.shortlisted_supervisors) == RANKED_IDS
    assert final_state["shortlist_briefing"] is not None
    reconstructed = SupervisorShortlist(
        candidate_id=final_state["candidate_profile"].candidate_id,
        shortlisted_supervisors=tuple(final_state["shortlisted_supervisors"]),
        generated_at=restored.generated_at,
        briefing=final_state["shortlist_briefing"],
    )
    assert reconstructed == restored
    assert all(
        supervisor.candidate_review_decision is not None
        and supervisor.candidate_review_decision.action is CandidateReviewAction.APPROVE
        for supervisor in restored.shortlisted_supervisors
    )
    assert len({item.supervisor_id for item in restored.shortlisted_supervisors}) == 5
    assert all(item.evidence for item in restored.shortlisted_supervisors)
