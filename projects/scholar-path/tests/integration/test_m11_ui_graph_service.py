"""Offline integration tests for the M11 LangGraph application-service boundary."""

from dataclasses import dataclass
from datetime import datetime
from typing import cast

import pytest

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.domain import CandidateProfile
from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    CandidateApproveResponse,
    GraphFixtureConfig,
    ScholarPathRuntime,
    ScholarPathState,
    UtcClockPort,
    build_scholarpath_runtime,
    create_test_checkpointer,
)
from scholarpath.ui import (
    GraphProgressEvent,
    ScholarPathApplicationError,
    ScholarPathApplicationService,
    UiStage,
)
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
)
from tests.fixtures import make_candidate_profile


class _FixedUtcClock:
    """Return the fixture timestamp so learned-memory records are reproducible."""

    def __init__(self, timestamp: datetime) -> None:
        self._timestamp = timestamp

    def now(self) -> datetime:
        return self._timestamp


@dataclass(frozen=True, slots=True)
class _ServiceHarness:
    """Keep the service and its inspectable offline dependencies together."""

    service: ScholarPathApplicationService
    runtime: ScholarPathRuntime
    memory: FakeCandidatePreferenceMemory
    candidate_profile: CandidateProfile


def _build_harness() -> _ServiceHarness:
    graph_config = GraphFixtureConfig()
    fallback_search = FakeSupervisorSearch()
    memory = FakeCandidatePreferenceMemory()
    clock: UtcClockPort = _FixedUtcClock(graph_config.fixtures.generated_at)
    runtime = build_scholarpath_runtime(
        graph_config,
        checkpointer=create_test_checkpointer(),
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=fallback_search,
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        candidate_preference_memory=memory,
        alternate_evidence_search=fallback_search,
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.OFF,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
        utc_clock=clock,
    )
    candidate_profile = make_candidate_profile(
        candidate_id="candidate-ui-service-001",
        proposed_research_statement=(
            "Study how enterprise architecture enables responsible AI assurance."
        ),
    )
    return _ServiceHarness(
        service=ScholarPathApplicationService(runtime),
        runtime=runtime,
        memory=memory,
        candidate_profile=candidate_profile,
    )


def test_offline_service_streams_safe_progress_and_pauses_in_the_correct_thread() -> None:
    harness = _build_harness()
    thread_id = "m11-ui-paused-thread"
    streamed: list[GraphProgressEvent] = []

    paused = harness.service.start(harness.candidate_profile, thread_id, streamed.append)
    inspected = harness.service.inspect(thread_id)
    persisted = harness.runtime.graph.get_state(harness.runtime.runnable_config(thread_id))
    state = cast(ScholarPathState, persisted.values)

    assert paused.stage is UiStage.REVIEW_SUPERVISORS
    assert paused.checkpoint_token
    assert len(paused.review_supervisors) == 5
    assert inspected == paused
    assert harness.service.inspect("m11-ui-unrelated-thread") is None
    assert tuple(streamed) == paused.progress_events
    assert streamed
    assert all(event.node_name in CANONICAL_NODE_NAMES for event in streamed)
    assert all(set(event.model_dump()) == {"sequence", "node_name"} for event in streamed)
    assert state["candidate_profile"] == harness.candidate_profile
    assert state["shortlisted_supervisors"] == []
    assert state["supervisor_shortlist"] is None
    assert persisted.tasks[0].interrupts


def test_offline_service_resumes_the_current_checkpoint_with_explicit_approval() -> None:
    harness = _build_harness()
    thread_id = "m11-ui-approved-thread"
    start_events: list[GraphProgressEvent] = []
    paused = harness.service.start(harness.candidate_profile, thread_id, start_events.append)
    approved_ids = (
        paused.review_supervisors[1].supervisor_id,
        paused.review_supervisors[0].supervisor_id,
    )
    resume_events: list[GraphProgressEvent] = []

    completed = harness.service.resume(
        thread_id,
        paused.checkpoint_token,
        CandidateApproveResponse(action="approve", supervisor_ids=approved_ids),
        resume_events.append,
    )
    inspected = harness.service.inspect(thread_id)

    assert completed.stage is UiStage.SUPERVISOR_SHORTLIST
    assert tuple(item.supervisor_id for item in completed.shortlisted_supervisors) == approved_ids
    assert inspected == completed
    assert tuple((*start_events, *resume_events)) == completed.progress_events
    assert [event.node_name for event in resume_events] == [
        "candidate_review_gate",
        "learn_candidate_preferences",
        "save_shortlisted_supervisors",
        "generate_shortlist_briefing",
    ]
    assert harness.memory.store_calls
    assert harness.memory.store_calls[0][0] == harness.candidate_profile.candidate_id


def test_service_rejects_wrong_thread_and_stale_checkpoint_without_advancing_state() -> None:
    harness = _build_harness()
    thread_id = "m11-ui-stale-thread"
    paused = harness.service.start(harness.candidate_profile, thread_id)
    approved_id = paused.review_supervisors[0].supervisor_id
    approval = CandidateApproveResponse(action="approve", supervisor_ids=(approved_id,))

    with pytest.raises(ScholarPathApplicationError) as missing_thread_error:
        harness.service.resume(
            "m11-ui-wrong-thread",
            paused.checkpoint_token,
            approval,
        )
    with pytest.raises(ScholarPathApplicationError) as stale_checkpoint_error:
        harness.service.resume(thread_id, "stale-checkpoint-token", approval)

    assert missing_thread_error.value.code == "thread_not_found"
    assert stale_checkpoint_error.value.code == "stale_candidate_review"
    assert harness.service.inspect(thread_id) == paused
    assert harness.memory.store_calls == []
