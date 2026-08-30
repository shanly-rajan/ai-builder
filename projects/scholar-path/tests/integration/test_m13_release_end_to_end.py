"""Offline release journey across ScholarPath's real checkpointed graph boundary."""

from collections import Counter
from datetime import datetime
from typing import cast

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.domain import (
    CandidateReviewAction,
    SearchResult,
    SupervisorLifecycleStatus,
    SupervisorShortlist,
)
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRejectionReason,
    CandidateRejectResponse,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathRuntime,
    ScholarPathState,
    UtcClockPort,
    build_scholarpath_runtime,
    build_walking_skeleton_fixtures,
    create_test_checkpointer,
)
from scholarpath.memory import CandidateMemoryKind, CandidateMemorySourceAction
from scholarpath.tools import SearchErrorCategory, SearchProvider, SearchProviderError
from scholarpath.ui import ScholarPathApplicationService, UiStage
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
from tests.fixtures import make_candidate_profile


class _FixedUtcClock:
    """Return one stable UTC timestamp for memory and proposal identifiers."""

    def __init__(self, timestamp: datetime) -> None:
        self._timestamp = timestamp

    def now(self) -> datetime:
        return self._timestamp


def _profile_results(query: str) -> tuple[SearchResult, ...]:
    """Return six complete profile results attributed to one exact provider query."""
    raw_results = build_walking_skeleton_fixtures().raw_search_results[:6]
    return tuple(
        SearchResult(
            url=raw.profile_url,
            title=f"{raw.full_name} | {raw.department} | {raw.institution}",
            description=f"{raw.full_name} is an academic researcher at {raw.institution}.",
            publication_date=None,
            originating_query=query,
        )
        for raw in raw_results
    )


def _state(runtime: ScholarPathRuntime, thread_id: str) -> ScholarPathState:
    snapshot = runtime.graph.get_state(runtime.runnable_config(thread_id))
    return cast(ScholarPathState, snapshot.values)


def test_release_journey_falls_back_learns_replans_and_requires_approval() -> None:
    """Prove the complete fake-provider release journey on one durable graph thread."""
    initial_response = make_valid_planning_response()
    refined_response = make_valid_planning_response(
        expanded_research_concepts=[
            "applied enterprise AI governance",
            "design science architecture evaluation",
            "traceable agentic systems",
        ],
        search_queries=[
            item.model_copy(update={"query": f"{item.query} applied design science"})
            for item in initial_response.search_queries
        ],
        rationale=(
            "Refine the search toward explicit applied and design-science evidence after the "
            "Candidate's rejection."
        ),
    )
    initial_query = initial_response.search_queries[0].query
    refined_queries = tuple(item.query for item in refined_response.search_queries)
    retry_failure = SearchProviderError(
        "Synthetic retryable failure after the configured timeout.",
        provider=SearchProvider.YOU,
        category=SearchErrorCategory.PROVIDER,
        retryable=True,
    )

    graph_config = GraphFixtureConfig()
    planning_model = FakePlanningModel((initial_response, refined_response))
    primary_search = FakeSupervisorSearch(
        outcomes={
            query: (_profile_results(query) if index == 0 else ())
            for index, query in enumerate(refined_queries)
        },
        scripts={initial_query: [retry_failure]},
    )
    fallback_search = FakeSupervisorSearch(
        outcomes={initial_query: _profile_results(initial_query)}
    )
    alternate_search = FakeSupervisorSearch(outcomes={})
    content_extractor = FakeContentExtraction()
    evidence_model = FakeEvidenceVerificationModel()
    research_fit_model = FakeResearchFitModel()
    review_model = FakeIndependentReviewModel()
    memory = FakeCandidatePreferenceMemory()
    clock: UtcClockPort = _FixedUtcClock(graph_config.fixtures.generated_at)
    runtime = build_scholarpath_runtime(
        graph_config,
        checkpointer=create_test_checkpointer(),
        planning_model=planning_model,
        supervisor_search=primary_search,
        tavily_search=fallback_search,
        content_extractor=content_extractor,
        evidence_model=evidence_model,
        research_fit_model=research_fit_model,
        independent_review_model=review_model,
        candidate_preference_memory=memory,
        alternate_evidence_search=alternate_search,
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.YOU_TIMEOUT_ONCE,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
        utc_clock=clock,
    )
    service = ScholarPathApplicationService(runtime)
    profile = make_candidate_profile(
        candidate_id="candidate-m13-release-001",
        proposed_research_statement=(
            "Evaluate applied enterprise architecture controls for traceable agentic AI systems."
        ),
        research_topics=("enterprise architecture", "agentic AI governance"),
        preferred_research_orientation="applied",
        methodological_interests=("design science", "case study evaluation"),
    )
    thread_id = "m13-release-journey"

    first_pause = service.start(profile, thread_id)
    first_state = _state(runtime, thread_id)
    first_round_attempts = [
        attempt for attempt in first_state["search_attempts"] if attempt.discovery_round == 1
    ]

    assert first_pause.stage is UiStage.REVIEW_SUPERVISORS
    assert len(first_pause.review_supervisors) == 5
    assert first_state["candidate_profile"] == profile
    assert first_state["review_status"] is ReviewStatus.PROPOSED
    assert first_state["discovery_round"] == 1
    assert [
        (attempt.provider_used, attempt.attempt_number, attempt.error_category)
        for attempt in first_round_attempts
    ] == [
        (SearchProvider.YOU, 1, SearchErrorCategory.TIMEOUT),
        (SearchProvider.YOU, 2, SearchErrorCategory.PROVIDER),
        (SearchProvider.TAVILY, 1, None),
    ]
    assert first_round_attempts[-1].result_count == 6
    assert first_round_attempts[-1].plausible_supervisor_count == 6
    assert first_state["fallback_search_used"] is True
    assert first_state["fallback_search_round"] == 1
    assert len(first_state["prospective_supervisors"]) == 6
    assert len(first_state["verified_supervisors"]) == 6
    assert len(first_state["research_fit_assessments"]) == 6
    assert len(first_state["research_fit_review_records"]) == 6
    assert first_state["shortlisted_supervisors"] == []
    assert first_state["supervisor_shortlist"] is None
    assert first_state["shortlist_briefing"] is None
    assert memory.load_calls == [profile.candidate_id]
    assert memory.store_calls == []
    assert planning_model.inputs[0].proposed_research_statement == (
        profile.proposed_research_statement
    )
    assert primary_search.calls == [initial_query]
    assert fallback_search.calls == [initial_query]
    assert alternate_search.calls == []
    print(
        "Candidate profile accepted: "
        f"{len(profile.research_topics)} research topics; applied orientation"
    )
    print(f"SearchPlan created: {len(initial_response.search_queries)} source-diverse queries")
    print("You.com route: timeout -> one retry -> retryable provider failure")
    print("Tavily fallback: 6 plausible profiles retained")
    print("Verification: 6 Verified Supervisors with source URLs")
    print("Research Fit: 6 assessments; independent reviews: 6")

    rejected_id = first_pause.review_supervisors[-1].supervisor_id
    rejection_reason = (
        "I want stronger applied design-science evidence before shortlisting this Supervisor."
    )
    second_pause = service.resume(
        thread_id,
        first_pause.checkpoint_token,
        CandidateRejectResponse(
            action="reject",
            rejections=(
                CandidateRejectionReason(
                    supervisor_id=rejected_id,
                    reason=rejection_reason,
                ),
            ),
        ),
    )
    second_state = _state(runtime, thread_id)
    second_round_attempts = [
        attempt for attempt in second_state["search_attempts"] if attempt.discovery_round == 2
    ]
    second_proposal_ids = tuple(item.supervisor_id for item in second_pause.review_supervisors)

    assert second_pause.stage is UiStage.REVIEW_SUPERVISORS
    assert second_pause.checkpoint_token != first_pause.checkpoint_token
    assert len(second_proposal_ids) == 5
    assert rejected_id not in second_proposal_ids
    assert second_state["review_status"] is ReviewStatus.PROPOSED
    assert second_state["discovery_round"] == 2
    assert second_state["retry_counts"]["review"] == 1
    assert all(attempt.provider_used is SearchProvider.YOU for attempt in second_round_attempts)
    assert [attempt.query for attempt in second_round_attempts] == list(refined_queries)
    assert all(attempt.error_category is None for attempt in second_round_attempts)
    assert primary_search.calls == [initial_query, *refined_queries]
    assert fallback_search.calls == [initial_query]
    assert planning_model.call_count == 2
    remembered_rejections = tuple(
        record
        for record in planning_model.inputs[1].remembered_candidate_memories
        if record.kind is CandidateMemoryKind.REJECTED_SUPERVISOR_REASON
    )
    assert len(remembered_rejections) == 1
    assert remembered_rejections[0].value == rejection_reason
    assert remembered_rejections[0].related_supervisor_id == rejected_id
    assert len(memory.store_calls) == 1
    stored_candidate_id, rejection_batch = memory.store_calls[0]
    assert stored_candidate_id == profile.candidate_id
    assert len(rejection_batch) == 1
    assert rejection_batch[0].source_action is CandidateMemorySourceAction.REJECTION
    assert second_state["shortlisted_supervisors"] == []
    assert second_state["supervisor_shortlist"] is None
    assert second_state["shortlist_briefing"] is None
    print("Candidate action: reject 1 Supervisor; shortlist writes: 0")
    print("Preference learning: rejection reason stored; planning round: 2")

    completed = service.resume(
        thread_id,
        second_pause.checkpoint_token,
        CandidateApproveResponse(action="approve", supervisor_ids=second_proposal_ids),
    )
    final_state = _state(runtime, thread_id)
    shortlist = final_state["supervisor_shortlist"]

    assert completed.stage is UiStage.SUPERVISOR_SHORTLIST
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert shortlist is not None
    assert SupervisorShortlist.model_validate_json(shortlist.model_dump_json()) == shortlist
    assert tuple(item.supervisor_id for item in shortlist.shortlisted_supervisors) == (
        second_proposal_ids
    )
    assert all(
        item.status is SupervisorLifecycleStatus.SHORTLISTED
        for item in shortlist.shortlisted_supervisors
    )
    assert final_state["shortlist_briefing"] == shortlist.briefing
    assert "5 Candidate-approved, evidence-backed Supervisor recommendations" in shortlist.briefing
    assert [decision.action for decision in final_state["candidate_feedback"]] == [
        CandidateReviewAction.REJECT,
        CandidateReviewAction.APPROVE,
    ]
    assert final_state["candidate_memory_processed_feedback_count"] == 2
    assert len(memory.store_calls) == 2
    approval_candidate_id, approval_batch = memory.store_calls[1]
    assert approval_candidate_id == profile.candidate_id
    assert {record.value for record in approval_batch} == set(
        refined_response.expanded_research_concepts
    )
    assert all(
        record.kind is CandidateMemoryKind.USEFUL_SEARCH_CONCEPT for record in approval_batch
    )
    assert all(
        record.source_action is CandidateMemorySourceAction.APPROVAL for record in approval_batch
    )
    print("Candidate action: approve 5 Supervisor IDs")
    print(f"Final briefing: {shortlist.briefing}")
    assert alternate_search.calls == []
    assert len(content_extractor.calls) == 11
    assert evidence_model.call_count == 11
    assert research_fit_model.call_count == 11
    assert review_model.call_count == 11

    node_counts = Counter(final_state["execution_log"])
    assert node_counts == Counter(
        {
            "load_candidate_preferences": 1,
            "plan_supervisor_searches": 2,
            "discover_prospective_supervisors": 2,
            "enough_supervisors_found": 3,
            "fallback_supervisor_search": 1,
            "deduplicate_supervisors": 2,
            "extract_supervisor_evidence": 2,
            "supervisor_evidence_sufficient": 2,
            "evaluate_research_fit": 2,
            "review_fit_assessments": 2,
            "synthesize_supervisor_shortlist": 2,
            "candidate_review_gate": 2,
            "learn_candidate_preferences": 2,
            "save_shortlisted_supervisors": 1,
            "generate_shortlist_briefing": 1,
        }
    )
