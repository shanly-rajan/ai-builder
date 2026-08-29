"""Graph tests for the M9 Candidate interrupt and in-memory persistence boundary."""

from dataclasses import dataclass
from typing import cast

from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from scholarpath.domain import (
    CandidatePreferenceRevision,
    CandidateReviewAction,
    SupervisorLifecycleStatus,
)
from scholarpath.graph import (
    CANDIDATE_REVIEW_GATE,
    CandidateApproveResponse,
    CandidateRejectionReason,
    CandidateRejectResponse,
    CandidateRequestMoreResponse,
    CandidateReviewInterruptPayload,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    build_scholarpath_graph,
    candidate_review_payload_from_graph_output,
    create_initial_state,
    create_test_checkpointer,
)
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
)

type _CompiledGraph = CompiledStateGraph[
    ScholarPathState,
    None,
    ScholarPathState,
    ScholarPathState,
]
type _ReviewResponse = (
    CandidateApproveResponse | CandidateRejectResponse | CandidateRequestMoreResponse
)


@dataclass(frozen=True, slots=True)
class _GraphHarness:
    """Keep one compiled graph, saver, and recording fakes together for resume tests."""

    graph: _CompiledGraph
    checkpointer: InMemorySaver
    graph_config: GraphFixtureConfig
    planning_model: FakePlanningModel
    supervisor_search: FakeSupervisorSearch

    @staticmethod
    def runnable_config(thread_id: str) -> RunnableConfig:
        return {
            "configurable": {"thread_id": thread_id},
            "recursion_limit": 128,
        }

    def start(self, thread_id: str) -> dict[str, object]:
        """Start one isolated run and return its first paused graph output."""
        output = self.graph.invoke(
            create_initial_state(self.graph_config.fixtures.candidate_profile),
            config=self.runnable_config(thread_id),
        )
        return cast(dict[str, object], output)

    def resume(
        self, thread_id: str, response: _ReviewResponse | dict[str, object]
    ) -> dict[str, object]:
        """Resume one interrupt with a JSON-safe response value."""
        resume_value = response if isinstance(response, dict) else response.model_dump(mode="json")
        output = self.graph.invoke(
            Command(resume=resume_value),
            config=self.runnable_config(thread_id),
        )
        return cast(dict[str, object], output)

    def state(self, thread_id: str) -> ScholarPathState:
        """Read the latest persisted values without advancing the graph."""
        snapshot = self.graph.get_state(self.runnable_config(thread_id))
        return cast(ScholarPathState, snapshot.values)


def _build_harness(config: GraphFixtureConfig | None = None) -> _GraphHarness:
    """Build a fully offline M9 graph with an explicit in-memory checkpointer."""
    resolved_config = config or GraphFixtureConfig()
    checkpointer = create_test_checkpointer()
    planning_model = FakePlanningModel()
    supervisor_search = FakeSupervisorSearch()
    graph = build_scholarpath_graph(
        resolved_config,
        checkpointer=checkpointer,
        planning_model=planning_model,
        supervisor_search=supervisor_search,
        tavily_search=FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        alternate_evidence_search=FakeSupervisorSearch(),
    )
    return _GraphHarness(
        graph=graph,
        checkpointer=checkpointer,
        graph_config=resolved_config,
        planning_model=planning_model,
        supervisor_search=supervisor_search,
    )


def _payload(output: dict[str, object]) -> CandidateReviewInterruptPayload:
    payload = candidate_review_payload_from_graph_output(output)
    assert payload is not None
    return payload


def test_graph_pauses_with_complete_candidate_review_payload() -> None:
    harness = _build_harness()

    output = harness.start("m9-payload")
    payload = _payload(output)

    assert "__interrupt__" in output
    assert payload.kind == "candidate_review_required"
    assert payload.allowed_actions == ("approve", "reject", "request_more")
    assert payload.review_iteration == 1
    assert len(payload.proposed_supervisor_shortlist) == 5
    for item in payload.proposed_supervisor_shortlist:
        assert 0 <= item.research_fit_score <= 100
        assert item.evidence_confidence.value in {"low", "medium", "high"}
        assert item.source_links
        assert item.availability_status.value
        assert isinstance(item.concerns, tuple)
        assert str(item.independent_review_outcome.review_status) in {
            "accepted",
            "revised",
            "unavailable",
        }
        assert item.independent_review_outcome.critique


def test_persisted_state_is_inspectable_while_candidate_review_is_paused() -> None:
    harness = _build_harness()
    thread_id = "m9-paused-state"

    harness.start(thread_id)
    snapshot = harness.graph.get_state(harness.runnable_config(thread_id))
    state = cast(ScholarPathState, snapshot.values)

    assert snapshot.next == (CANDIDATE_REVIEW_GATE,)
    assert snapshot.tasks[0].interrupts
    assert state["review_status"] is ReviewStatus.PROPOSED
    assert state["proposed_shortlist"] is not None
    assert state["candidate_feedback"] == []
    assert state["shortlisted_supervisors"] == []
    assert state["supervisor_shortlist"] is None


def test_resume_with_approve_saves_only_the_explicit_ordered_subset() -> None:
    harness = _build_harness()
    thread_id = "m9-approve-subset"
    proposal = _payload(harness.start(thread_id)).proposed_supervisor_shortlist
    approved_ids = (proposal[2].supervisor_id, proposal[0].supervisor_id)

    output = harness.resume(
        thread_id,
        CandidateApproveResponse(action="approve", supervisor_ids=approved_ids),
    )
    state = harness.state(thread_id)

    assert "__interrupt__" not in output
    assert state["review_status"] is ReviewStatus.COMPLETED
    assert tuple(item.supervisor_id for item in state["shortlisted_supervisors"]) == approved_ids
    assert all(
        item.status is SupervisorLifecycleStatus.SHORTLISTED
        for item in state["shortlisted_supervisors"]
    )
    assert state["candidate_feedback"][-1].action is CandidateReviewAction.APPROVE
    assert state["candidate_feedback"][-1].supervisor_ids == approved_ids


def test_resume_with_supervisor_specific_rejection_records_reason_and_repauses() -> None:
    harness = _build_harness()
    thread_id = "m9-reject"
    first_payload = _payload(harness.start(thread_id))
    rejected_id = first_payload.proposed_supervisor_shortlist[-1].supervisor_id
    reason = "The Supervisor's applied research orientation does not match my direction."

    output = harness.resume(
        thread_id,
        CandidateRejectResponse(
            action="reject",
            rejections=(CandidateRejectionReason(supervisor_id=rejected_id, reason=reason),),
        ),
    )
    second_payload = _payload(output)
    state = harness.state(thread_id)

    assert second_payload.review_iteration == 2
    assert rejected_id not in {
        item.supervisor_id for item in second_payload.proposed_supervisor_shortlist
    }
    assert [item.supervisor_id for item in state["rejected_supervisors"]] == [rejected_id]
    assert state["rejected_supervisors"][0].candidate_review_decision is not None
    assert state["rejected_supervisors"][0].candidate_review_decision.reason == reason
    assert state["candidate_feedback"][-1].reason == reason
    assert state["candidate_feedback"][-1].supervisor_ids == (rejected_id,)
    assert state["shortlisted_supervisors"] == []
    assert harness.planning_model.call_count == 2


def test_resume_with_request_more_updates_preferences_and_replans() -> None:
    harness = _build_harness()
    thread_id = "m9-request-more"
    harness.start(thread_id)
    revision = CandidatePreferenceRevision(
        research_topics=("public-sector AI assurance",),
        preferred_regions=("Netherlands",),
        constraints=("part-time registration",),
        exclusions=("purely theoretical programmes",),
    )

    output = harness.resume(
        thread_id,
        CandidateRequestMoreResponse(action="request_more", revised_preferences=revision),
    )
    state = harness.state(thread_id)

    assert _payload(output).review_iteration == 2
    assert state["candidate_preferences"][-1] == revision
    assert state["search_plan"] is not None
    assert state["search_plan"].target_regions == ("Netherlands",)
    assert harness.planning_model.call_count == 2
    assert harness.planning_model.inputs[-1].target_regions == ("Netherlands",)
    assert harness.planning_model.inputs[-1].exclusions == ("purely theoretical programmes",)
    assert harness.planning_model.inputs[-1].remembered_candidate_preferences[-1] == revision
    assert state["shortlisted_supervisors"] == []


def test_separate_thread_ids_never_share_candidate_research_state() -> None:
    harness = _build_harness()
    thread_a = "m9-thread-a"
    thread_b = "m9-thread-b"
    payload_a = _payload(harness.start(thread_a))
    _payload(harness.start(thread_b))
    approved_id = payload_a.proposed_supervisor_shortlist[0].supervisor_id

    harness.resume(
        thread_a,
        CandidateApproveResponse(action="approve", supervisor_ids=(approved_id,)),
    )
    state_a = harness.state(thread_a)
    state_b = harness.state(thread_b)

    assert state_a["review_status"] is ReviewStatus.COMPLETED
    assert [item.supervisor_id for item in state_a["shortlisted_supervisors"]] == [approved_id]
    assert state_b["review_status"] is ReviewStatus.PROPOSED
    assert state_b["candidate_feedback"] == []
    assert state_b["shortlisted_supervisors"] == []
    assert state_b["supervisor_shortlist"] is None
    assert harness.graph.get_state(harness.runnable_config(thread_b)).next == (
        CANDIDATE_REVIEW_GATE,
    )


def test_no_supervisor_is_saved_before_explicit_candidate_approval() -> None:
    harness = _build_harness()
    thread_id = "m9-no-early-save"

    harness.start(thread_id)
    state = harness.state(thread_id)
    proposal = state["proposed_shortlist"]

    assert proposal is not None
    assert all(
        recommendation.supervisor.status is SupervisorLifecycleStatus.VERIFIED
        for recommendation in proposal.recommendations
    )
    assert state["shortlisted_supervisors"] == []
    assert state["supervisor_shortlist"] is None
    assert "save_shortlisted_supervisors" not in state["execution_log"]
    assert "generate_shortlist_briefing" not in state["execution_log"]


def test_invalid_supervisor_ids_are_rejected_and_candidate_is_reprompted() -> None:
    harness = _build_harness()
    thread_id = "m9-invalid-id"
    harness.start(thread_id)

    invalid_output = harness.resume(
        thread_id,
        {"action": "approve", "supervisor_ids": ["supervisor-outside-proposal"]},
    )
    retry_payload = _payload(invalid_output)
    invalid_state = harness.state(thread_id)

    assert retry_payload.validation_error is not None
    assert invalid_state["review_status"] is ReviewStatus.PROPOSED
    assert invalid_state["candidate_review_error"] is not None
    assert invalid_state["retry_counts"]["review_input"] == 1
    assert invalid_state["tool_errors"][-1].code == "review_scope_invalid"
    assert invalid_state["tool_errors"][-1].recoverable is True
    assert invalid_state["candidate_feedback"] == []
    assert invalid_state["shortlisted_supervisors"] == []

    valid_id = retry_payload.proposed_supervisor_shortlist[0].supervisor_id
    harness.resume(
        thread_id,
        CandidateApproveResponse(action="approve", supervisor_ids=(valid_id,)),
    )
    final_state = harness.state(thread_id)
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["candidate_feedback"]) == 1
    assert [item.supervisor_id for item in final_state["shortlisted_supervisors"]] == [valid_id]


def test_repeated_request_more_stops_at_the_configured_iteration_limit() -> None:
    harness = _build_harness(GraphFixtureConfig(max_review_retries=1))
    thread_id = "m9-loop-limit"
    harness.start(thread_id)

    first_output = harness.resume(
        thread_id,
        CandidateRequestMoreResponse(
            action="request_more",
            revised_preferences=CandidatePreferenceRevision(preferred_regions=("Netherlands",)),
        ),
    )
    second_payload = _payload(first_output)
    assert second_payload.review_iteration == 2
    assert second_payload.maximum_review_iterations == 2

    final_output = harness.resume(
        thread_id,
        CandidateRequestMoreResponse(
            action="request_more",
            revised_preferences=CandidatePreferenceRevision(preferred_regions=("Germany",)),
        ),
    )
    state = harness.state(thread_id)

    assert "__interrupt__" not in final_output
    assert state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert state["retry_counts"]["review"] == 1
    assert len(state["candidate_feedback"]) == 2
    assert state["tool_errors"][-1].code == "review_retry_exhausted"
    assert state["shortlisted_supervisors"] == []
    assert state["supervisor_shortlist"] is None
    assert harness.planning_model.call_count == 2


def test_resume_reexecutes_only_the_interrupt_node_without_duplicate_updates() -> None:
    harness = _build_harness()
    thread_id = "m9-resume-idempotency"
    payload = _payload(harness.start(thread_id))
    paused_state = harness.state(thread_id)
    paused_log = tuple(paused_state["execution_log"])
    raw_result_count = len(paused_state["raw_search_results"])
    planning_calls = harness.planning_model.call_count
    search_calls = tuple(harness.supervisor_search.calls)
    approved_id = payload.proposed_supervisor_shortlist[0].supervisor_id

    harness.resume(
        thread_id,
        CandidateApproveResponse(action="approve", supervisor_ids=(approved_id,)),
    )
    state = harness.state(thread_id)

    assert tuple(state["execution_log"][: len(paused_log)]) == paused_log
    assert state["execution_log"].count(CANDIDATE_REVIEW_GATE) == 1
    assert state["execution_log"].count("save_shortlisted_supervisors") == 1
    assert state["execution_log"].count("generate_shortlist_briefing") == 1
    assert state["execution_log"].count("synthesize_supervisor_shortlist") == 1
    assert harness.planning_model.call_count == planning_calls == 1
    assert tuple(harness.supervisor_search.calls) == search_calls
    assert len(state["raw_search_results"]) == raw_result_count
    assert len(state["candidate_feedback"]) == 1
