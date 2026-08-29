"""Deterministic UI application service fake for Streamlit AppTest."""

from __future__ import annotations

from dataclasses import dataclass

from scholarpath.domain import CandidateProfile, SupervisorLifecycleStatus
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRejectResponse,
    CandidateReviewResponse,
)
from scholarpath.ui import (
    EvidenceSourceView,
    GraphProgressEvent,
    ProspectiveSupervisorView,
    ScholarPathApplicationError,
    UiRunSnapshot,
    UiStage,
    VerifiedSupervisorView,
)
from scholarpath.ui.service import ProgressSink
from tests.fixtures import (
    make_prospective_supervisor,
    make_research_fit_assessment,
    make_verified_supervisor,
)


def _verified_view(index: int) -> VerifiedSupervisorView:
    supervisor = make_verified_supervisor(index)
    assessment = make_research_fit_assessment(index)
    return VerifiedSupervisorView(
        supervisor_id=supervisor.supervisor_id,
        full_name=supervisor.full_name,
        institution=supervisor.institution,
        department=supervisor.department,
        profile_url=supervisor.profile_url,
        verification_status=supervisor.verification_status,
        research_fit_score=assessment.overall_score,
        fit_explanation=assessment.rationale,
        evidence_confidence=assessment.confidence,
        evidence_sources=tuple(
            EvidenceSourceView(
                evidence_id=claim.evidence_id,
                claim=claim.claim,
                source_url=claim.source_url,
                source_kind=claim.source_kind,
                confidence=claim.confidence,
                directly_supported=claim.directly_supported,
            )
            for claim in supervisor.evidence
        ),
        source_links=(
            supervisor.profile_url,
            *(claim.source_url for claim in supervisor.evidence),
        ),
        availability_status=supervisor.availability_status,
        concerns=assessment.concerns,
        independent_review_status="accepted",
    )


def make_ui_review_snapshot(*, checkpoint_token: str = "ui-checkpoint-001") -> UiRunSnapshot:
    """Return a two-result evidence-backed proposal for AppTest."""
    prospective = tuple(
        ProspectiveSupervisorView(
            supervisor_id=item.supervisor_id,
            full_name=item.full_name,
            institution=item.institution,
            department=item.department,
            profile_url=item.profile_url,
            status=SupervisorLifecycleStatus.PROSPECTIVE,
        )
        for item in (make_prospective_supervisor(1), make_prospective_supervisor(2))
    )
    verified = (_verified_view(1), _verified_view(2))
    return UiRunSnapshot(
        stage=UiStage.REVIEW_SUPERVISORS,
        checkpoint_token=checkpoint_token,
        progress_events=(
            GraphProgressEvent(sequence=1, node_name="load_candidate_preferences"),
            GraphProgressEvent(sequence=2, node_name="plan_supervisor_searches"),
            GraphProgressEvent(sequence=3, node_name="discover_prospective_supervisors"),
            GraphProgressEvent(sequence=4, node_name="extract_supervisor_evidence"),
            GraphProgressEvent(sequence=5, node_name="evaluate_research_fit"),
            GraphProgressEvent(sequence=6, node_name="candidate_review_gate"),
        ),
        prospective_supervisors=prospective,
        verified_supervisors=verified,
        review_supervisors=verified,
        review_iteration=1,
        maximum_review_iterations=2,
    )


@dataclass(frozen=True, slots=True)
class UiStartCall:
    candidate_profile: CandidateProfile
    thread_id: str


@dataclass(frozen=True, slots=True)
class UiResumeCall:
    thread_id: str
    checkpoint_token: str
    response: CandidateReviewResponse


class FakeScholarPathApplication:
    """Store typed projections per thread while recording every UI command."""

    def __init__(
        self,
        *,
        start_snapshot: UiRunSnapshot | None = None,
        start_error: Exception | None = None,
        resume_error: Exception | None = None,
    ) -> None:
        self.start_snapshot = start_snapshot or make_ui_review_snapshot()
        self.start_error = start_error
        self.resume_error = resume_error
        self.start_calls: list[UiStartCall] = []
        self.inspect_calls: list[str] = []
        self.resume_calls: list[UiResumeCall] = []
        self._snapshots: dict[str, UiRunSnapshot] = {}

    def start(
        self,
        candidate_profile: CandidateProfile,
        thread_id: str,
        progress_sink: ProgressSink | None = None,
    ) -> UiRunSnapshot:
        if self.start_error is not None:
            raise self.start_error
        self.start_calls.append(UiStartCall(candidate_profile, thread_id))
        self._snapshots[thread_id] = self.start_snapshot
        if progress_sink is not None:
            for event in self.start_snapshot.progress_events:
                progress_sink(event)
        return self.start_snapshot

    def inspect(self, thread_id: str) -> UiRunSnapshot | None:
        self.inspect_calls.append(thread_id)
        return self._snapshots.get(thread_id)

    def resume(
        self,
        thread_id: str,
        checkpoint_token: str,
        response: CandidateReviewResponse,
        progress_sink: ProgressSink | None = None,
    ) -> UiRunSnapshot:
        if self.resume_error is not None:
            raise self.resume_error
        current = self._snapshots.get(thread_id)
        if current is None or current.checkpoint_token != checkpoint_token:
            raise ScholarPathApplicationError("stale_fake_thread", "The fake thread is stale.")
        self.resume_calls.append(UiResumeCall(thread_id, checkpoint_token, response))
        next_sequence = len(current.progress_events) + 1
        event = GraphProgressEvent(
            sequence=next_sequence,
            node_name="learn_candidate_preferences",
        )
        if progress_sink is not None:
            progress_sink(event)

        if isinstance(response, CandidateApproveResponse):
            by_id = {item.supervisor_id: item for item in current.review_supervisors}
            approved = tuple(by_id[item] for item in response.supervisor_ids)
            updated = current.model_copy(
                update={
                    "stage": UiStage.SUPERVISOR_SHORTLIST,
                    "checkpoint_token": "ui-checkpoint-completed",
                    "progress_events": (
                        *current.progress_events,
                        event,
                        GraphProgressEvent(
                            sequence=next_sequence + 1,
                            node_name="save_shortlisted_supervisors",
                        ),
                        GraphProgressEvent(
                            sequence=next_sequence + 2,
                            node_name="generate_shortlist_briefing",
                        ),
                    ),
                    "review_supervisors": (),
                    "shortlisted_supervisors": approved,
                    "review_iteration": None,
                    "maximum_review_iterations": None,
                    "shortlist_briefing": "Candidate-approved evidence-backed shortlist.",
                }
            )
        else:
            remaining = current.review_supervisors
            if isinstance(response, CandidateRejectResponse):
                rejected_ids = {item.supervisor_id for item in response.rejections}
                remaining = tuple(
                    item
                    for item in current.review_supervisors
                    if item.supervisor_id not in rejected_ids
                )
            updated = current.model_copy(
                update={
                    "checkpoint_token": "ui-checkpoint-002",
                    "progress_events": (*current.progress_events, event),
                    "review_supervisors": remaining,
                    "review_iteration": 2,
                }
            )
        updated = UiRunSnapshot.model_validate(updated)
        self._snapshots[thread_id] = updated
        return updated
