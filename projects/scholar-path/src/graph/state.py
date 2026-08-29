"""Typed state and reducers for the deterministic ScholarPath graph."""

from enum import StrEnum
from typing import Annotated, TypedDict

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool

from ..domain import (
    CandidatePreferenceRevision,
    CandidateProfile,
    CandidateReviewDecision,
    ProposedSupervisorShortlist,
    ProspectiveSupervisor,
    ReconciledResearchFitAssessment,
    ResearchFitAssessment,
    SearchPlan,
    SupervisorDiscoveryProvenance,
    SupervisorShortlist,
    SupervisorVerificationRecord,
    VerifiedSupervisor,
)
from .discovery import SearchAttempt
from .verification import EvidenceExtractionAttempt, EvidenceSourceReference


def append_items[T](left: list[T], right: list[T]) -> list[T]:
    """Return a new event list without mutating either reducer input."""
    return [*left, *right]


def merge_supervisors_by_id(
    left: list[VerifiedSupervisor], right: list[VerifiedSupervisor]
) -> list[VerifiedSupervisor]:
    """Append new Supervisor records while preserving stable identifier order."""
    merged = list(left)
    positions = {supervisor.supervisor_id: index for index, supervisor in enumerate(merged)}
    for supervisor in right:
        if supervisor.supervisor_id in positions:
            merged[positions[supervisor.supervisor_id]] = supervisor
        else:
            positions[supervisor.supervisor_id] = len(merged)
            merged.append(supervisor)
    return merged


class ReviewStatus(StrEnum):
    """Deterministic review and terminal statuses used by graph routing."""

    PENDING = "pending"
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"
    REQUEST_MORE = "request_more"
    COMPLETED = "completed"
    RETRY_EXHAUSTED = "retry_exhausted"
    DISCOVERY_INCOMPLETE = "discovery_incomplete"
    EVIDENCE_INCOMPLETE = "evidence_incomplete"


class RawSupervisorSearchResult(BaseModel):
    """Fixture-backed discovery result before domain conversion and deduplication."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    supervisor_id: str = Field(min_length=1)
    full_name: str = Field(min_length=1)
    institution: str = Field(min_length=1)
    department: str = Field(min_length=1)
    profile_url: HttpUrl
    discovery_source: str = Field(min_length=1)
    discovery_query: str = Field(min_length=1)
    discovery_provenance: tuple[SupervisorDiscoveryProvenance, ...] = ()
    discovery_round: int = Field(default=1, ge=1)

    @classmethod
    def from_prospective_supervisor(
        cls,
        supervisor: ProspectiveSupervisor,
        *,
        discovery_round: int = 1,
    ) -> "RawSupervisorSearchResult":
        """Project a validated Prospective Supervisor into the append-only raw channel."""
        return cls.model_validate(
            {
                **supervisor.model_dump(mode="python", exclude={"status"}),
                "discovery_round": discovery_round,
            }
        )

    def to_prospective_supervisor(self) -> ProspectiveSupervisor:
        """Convert the raw fixture result through the domain validation boundary."""
        return ProspectiveSupervisor.model_validate(
            self.model_dump(mode="python", exclude={"discovery_round"})
        )


class ToolErrorRecord(BaseModel):
    """Sanitized deterministic error recorded when a bounded route cannot continue."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    node: str = Field(min_length=1)
    code: str = Field(min_length=1)
    message: str = Field(min_length=1)
    recoverable: StrictBool


class ScholarPathState(TypedDict):
    """Complete typed state exchanged by every ScholarPath walking-skeleton node."""

    candidate_profile: CandidateProfile
    candidate_preferences: Annotated[list[CandidatePreferenceRevision], append_items]
    search_plan: SearchPlan | None
    raw_search_results: Annotated[list[RawSupervisorSearchResult], append_items]
    prospective_supervisors: list[ProspectiveSupervisor]
    verified_supervisors: list[VerifiedSupervisor]
    verification_records: list[SupervisorVerificationRecord]
    evidence_extraction_attempts: Annotated[list[EvidenceExtractionAttempt], append_items]
    alternate_evidence_sources: dict[str, EvidenceSourceReference]
    research_fit_assessments: list[ResearchFitAssessment]
    research_fit_review_records: list[ReconciledResearchFitAssessment]
    proposed_shortlist: ProposedSupervisorShortlist | None
    shortlisted_supervisors: list[VerifiedSupervisor]
    rejected_supervisors: Annotated[list[VerifiedSupervisor], merge_supervisors_by_id]
    candidate_feedback: Annotated[list[CandidateReviewDecision], append_items]
    tool_errors: Annotated[list[ToolErrorRecord], append_items]
    search_attempts: Annotated[list[SearchAttempt], append_items]
    fallback_search_used: bool
    fallback_search_round: int | None
    discovery_round: int
    retry_counts: dict[str, int]
    review_status: ReviewStatus
    execution_log: Annotated[list[str], append_items]
    supervisor_shortlist: SupervisorShortlist | None
    shortlist_briefing: str | None


class ScholarPathStateUpdate(TypedDict, total=False):
    """Partial state update returned by a deterministic graph node."""

    candidate_profile: CandidateProfile
    candidate_preferences: list[CandidatePreferenceRevision]
    search_plan: SearchPlan | None
    raw_search_results: list[RawSupervisorSearchResult]
    prospective_supervisors: list[ProspectiveSupervisor]
    verified_supervisors: list[VerifiedSupervisor]
    verification_records: list[SupervisorVerificationRecord]
    evidence_extraction_attempts: list[EvidenceExtractionAttempt]
    alternate_evidence_sources: dict[str, EvidenceSourceReference]
    research_fit_assessments: list[ResearchFitAssessment]
    research_fit_review_records: list[ReconciledResearchFitAssessment]
    proposed_shortlist: ProposedSupervisorShortlist | None
    shortlisted_supervisors: list[VerifiedSupervisor]
    rejected_supervisors: list[VerifiedSupervisor]
    candidate_feedback: list[CandidateReviewDecision]
    tool_errors: list[ToolErrorRecord]
    search_attempts: list[SearchAttempt]
    fallback_search_used: bool
    fallback_search_round: int | None
    discovery_round: int
    retry_counts: dict[str, int]
    review_status: ReviewStatus
    execution_log: list[str]
    supervisor_shortlist: SupervisorShortlist | None
    shortlist_briefing: str | None


def create_initial_state(candidate_profile: CandidateProfile) -> ScholarPathState:
    """Create a complete initial state with no hidden or missing channels."""
    return ScholarPathState(
        candidate_profile=candidate_profile,
        candidate_preferences=[],
        search_plan=None,
        raw_search_results=[],
        prospective_supervisors=[],
        verified_supervisors=[],
        verification_records=[],
        evidence_extraction_attempts=[],
        alternate_evidence_sources={},
        research_fit_assessments=[],
        research_fit_review_records=[],
        proposed_shortlist=None,
        shortlisted_supervisors=[],
        rejected_supervisors=[],
        candidate_feedback=[],
        tool_errors=[],
        search_attempts=[],
        fallback_search_used=False,
        fallback_search_round=None,
        discovery_round=0,
        retry_counts={"discovery": 0, "evidence": 0, "review": 0},
        review_status=ReviewStatus.PENDING,
        execution_log=[],
        supervisor_shortlist=None,
        shortlist_briefing=None,
    )
