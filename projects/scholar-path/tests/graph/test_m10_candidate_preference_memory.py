"""Graph tests for M10 persistent, Candidate-scoped preference memory."""

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import cast

import pytest

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRejectionReason,
    CandidateRejectResponse,
    CandidateReviewResponse,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    UtcClockPort,
    default_review_decision,
    run_scholarpath_graph,
)
from scholarpath.memory import (
    CandidateMemoryKind,
    CandidateMemoryRecord,
    CandidateMemorySourceAction,
    make_candidate_memory_record,
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


class _FixedUtcClock:
    """Keep learned-memory timestamps deterministic in graph assertions."""

    def __init__(self, timestamp: datetime) -> None:
        self._timestamp = timestamp

    def now(self) -> datetime:
        return self._timestamp


def _remembered_record(
    kind: CandidateMemoryKind,
    value: str,
) -> CandidateMemoryRecord:
    return make_candidate_memory_record(
        kind,
        value,
        CandidateMemorySourceAction.DIRECT_PREFERENCE_SUBMISSION,
        datetime(2026, 8, 20, 9, 0, tzinfo=UTC),
    )


def _run_graph(
    memory: FakeCandidatePreferenceMemory,
    *,
    responses: Sequence[CandidateReviewResponse] = (),
    planning_model: FakePlanningModel | None = None,
    thread_id: str,
) -> tuple[dict[str, object], ScholarPathState, FakePlanningModel]:
    config = GraphFixtureConfig()
    resolved_planning_model = planning_model or FakePlanningModel()
    primary_search = FakeSupervisorSearch()
    fallback_search = FakeSupervisorSearch()
    clock: UtcClockPort = _FixedUtcClock(config.fixtures.generated_at)
    output = run_scholarpath_graph(
        config,
        thread_id=thread_id,
        candidate_review_responses=responses,
        planning_model=resolved_planning_model,
        supervisor_search=primary_search,
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
    output_dict = cast(dict[str, object], output)
    return output_dict, cast(ScholarPathState, output), resolved_planning_model


def test_candidate_memory_is_loaded_at_graph_start() -> None:
    config = GraphFixtureConfig()
    candidate_id = config.fixtures.candidate_profile.candidate_id
    remembered = _remembered_record(
        CandidateMemoryKind.PREFERRED_RESEARCH_THEME,
        "public-sector AI assurance",
    )
    memory = FakeCandidatePreferenceMemory({candidate_id: (remembered,)})

    output, state, _ = _run_graph(memory, thread_id="m10-memory-load")

    assert "__interrupt__" in output
    assert memory.load_calls == [candidate_id]
    assert state["candidate_memory_records"] == [remembered]
    assert state["candidate_memory_available"] is True
    assert state["candidate_preferences"][-1].research_topics is not None
    assert "public-sector AI assurance" in state["candidate_preferences"][-1].research_topics


def test_rejection_reason_is_stored_only_after_explicit_rejection() -> None:
    candidate_id = GraphFixtureConfig().fixtures.candidate_profile.candidate_id
    rejected_id = default_review_decision().supervisor_ids[0]
    reason = "The methodological orientation does not match my intended direction."
    memory = FakeCandidatePreferenceMemory()
    rejection = CandidateRejectResponse(
        action="reject",
        rejections=(CandidateRejectionReason(supervisor_id=rejected_id, reason=reason),),
    )

    output, state, _ = _run_graph(
        memory,
        responses=(rejection,),
        thread_id="m10-rejection-memory",
    )

    assert "__interrupt__" in output
    assert len(memory.store_calls) == 1
    stored_candidate_id, stored_batch = memory.store_calls[0]
    assert stored_candidate_id == candidate_id
    assert len(stored_batch) == 1
    record = stored_batch[0]
    assert record.kind is CandidateMemoryKind.REJECTED_SUPERVISOR_REASON
    assert record.source_action is CandidateMemorySourceAction.REJECTION
    assert record.value == reason
    assert record.related_supervisor_id == rejected_id
    assert memory.records_for(candidate_id) == (record,)
    assert state["candidate_memory_processed_feedback_count"] == 1


def test_approval_stores_useful_search_concepts_after_explicit_approval() -> None:
    candidate_id = GraphFixtureConfig().fixtures.candidate_profile.candidate_id
    memory = FakeCandidatePreferenceMemory()
    approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )

    output, state, _ = _run_graph(
        memory,
        responses=(approval,),
        thread_id="m10-approval-memory",
    )

    assert "__interrupt__" not in output
    assert state["review_status"] is ReviewStatus.COMPLETED
    assert state["search_plan"] is not None
    assert len(memory.store_calls) == 1
    stored_candidate_id, stored_batch = memory.store_calls[0]
    assert stored_candidate_id == candidate_id
    assert {record.value for record in stored_batch} == set(
        state["search_plan"].expanded_research_concepts
    )
    assert all(record.kind is CandidateMemoryKind.USEFUL_SEARCH_CONCEPT for record in stored_batch)
    assert all(
        record.source_action is CandidateMemorySourceAction.APPROVAL for record in stored_batch
    )
    assert memory.records_for(candidate_id) == stored_batch


def test_viewing_candidate_review_results_does_not_write_memory() -> None:
    memory = FakeCandidatePreferenceMemory()

    output, state, _ = _run_graph(memory, thread_id="m10-view-without-action")

    assert "__interrupt__" in output
    assert state["review_status"] is ReviewStatus.PROPOSED
    assert state["candidate_feedback"] == []
    assert state["candidate_memory_processed_feedback_count"] == 0
    assert memory.store_calls == []
    assert "learn_candidate_preferences" not in state["execution_log"]


def test_retrieved_preferences_are_supplied_to_fake_planning_model() -> None:
    config = GraphFixtureConfig()
    candidate_id = config.fixtures.candidate_profile.candidate_id
    remembered_region = _remembered_record(CandidateMemoryKind.PREFERRED_REGION, "Canada")
    remembered_theme = _remembered_record(
        CandidateMemoryKind.PREFERRED_RESEARCH_THEME,
        "public-sector AI assurance",
    )
    memory = FakeCandidatePreferenceMemory({candidate_id: (remembered_region, remembered_theme)})
    planning_model = FakePlanningModel()

    _, _, recorded_model = _run_graph(
        memory,
        planning_model=planning_model,
        thread_id="m10-planning-memory-input",
    )

    planning_input = recorded_model.inputs[0]
    assert planning_input.remembered_candidate_memories == (
        remembered_region,
        remembered_theme,
    )
    assert planning_input.remembered_candidate_preferences[-1].preferred_regions is not None
    assert "Canada" in planning_input.remembered_candidate_preferences[-1].preferred_regions
    assert "Canada" in planning_input.target_regions
    assert "public-sector AI assurance" in (
        planning_input.remembered_candidate_preferences[-1].research_topics or ()
    )


def test_memory_load_failure_is_non_fatal_and_current_profile_drives_planning() -> None:
    memory = FakeCandidatePreferenceMemory(
        load_error=RuntimeError("provider detail containing private-secret")
    )

    output, state, planning_model = _run_graph(
        memory,
        thread_id="m10-memory-load-failure",
    )

    assert "__interrupt__" in output
    assert state["review_status"] is ReviewStatus.PROPOSED
    assert state["candidate_memory_available"] is False
    assert state["candidate_memory_records"] == []
    assert state["tool_errors"][0].code == "candidate_memory_load_unavailable"
    assert state["tool_errors"][0].recoverable is True
    assert "private-secret" not in state["tool_errors"][0].message
    assert planning_model.inputs[0].target_regions == (state["candidate_profile"].preferred_regions)


def test_memory_store_failure_does_not_block_an_approved_shortlist() -> None:
    memory = FakeCandidatePreferenceMemory(
        store_error=RuntimeError("provider detail containing private-secret")
    )
    approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )

    output, state, _ = _run_graph(
        memory,
        responses=(approval,),
        thread_id="m10-memory-store-failure",
    )

    assert "__interrupt__" not in output
    assert state["review_status"] is ReviewStatus.COMPLETED
    assert state["supervisor_shortlist"] is not None
    assert state["candidate_memory_available"] is False
    assert len(memory.store_calls) == 1
    memory_error = next(
        error
        for error in state["tool_errors"]
        if error.code == "candidate_memory_store_unavailable"
    )
    assert memory_error.recoverable is True
    assert "private-secret" not in memory_error.message


def test_injected_fake_prevents_default_graph_test_from_constructing_mem0(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_mem0_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Offline graph tests must not construct the Mem0 adapter")

    monkeypatch.setattr(
        "scholarpath.graph.workflow.Mem0CandidatePreferenceAdapter",
        fail_if_mem0_is_constructed,
    )
    memory = FakeCandidatePreferenceMemory()

    output, state, _ = _run_graph(memory, thread_id="m10-no-live-memory")

    assert "__interrupt__" in output
    assert state["candidate_memory_available"] is True
    assert memory.load_calls == [state["candidate_profile"].candidate_id]
    assert memory.store_calls == []
