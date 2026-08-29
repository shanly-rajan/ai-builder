"""Typed, privacy-minimizing presentation contracts for the ScholarPath UI."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    model_validator,
)

from ..domain import (
    AvailabilityStatus,
    CandidateProfile,
    EvidenceConfidence,
    SourceKind,
    SupervisorLifecycleStatus,
    VerificationStatus,
)

NonEmptyUiText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class UiStage(StrEnum):
    """Candidate-facing stages without duplicating LangGraph workflow state."""

    RESEARCH_PROFILE = "research_profile"
    SEARCH_PROGRESS = "search_progress"
    PROSPECTIVE_SUPERVISORS = "prospective_supervisors"
    VERIFIED_SUPERVISORS = "verified_supervisors"
    REVIEW_SUPERVISORS = "review_supervisors"
    SUPERVISOR_SHORTLIST = "supervisor_shortlist"
    STOPPED = "stopped"


class CandidateResearchProfileSubmission(BaseModel):
    """Candidate-entered research preferences before an opaque identity is attached."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    proposed_research_statement: NonEmptyUiText
    research_topics: tuple[NonEmptyUiText, ...] = Field(min_length=1)
    preferred_regions: tuple[NonEmptyUiText, ...] = ()
    study_modes: tuple[NonEmptyUiText, ...] = ()
    research_orientation: NonEmptyUiText | None = None
    methodological_interests: tuple[NonEmptyUiText, ...] = ()
    exclusions: tuple[NonEmptyUiText, ...] = ()

    def to_candidate_profile(self, candidate_id: str) -> CandidateProfile:
        """Create the authoritative domain profile with an opaque Candidate identifier."""
        return CandidateProfile(
            candidate_id=candidate_id,
            proposed_research_statement=self.proposed_research_statement,
            research_topics=self.research_topics,
            preferred_regions=self.preferred_regions,
            preferred_study_modes=self.study_modes,
            preferred_research_orientation=self.research_orientation,
            methodological_interests=self.methodological_interests,
            exclusions=self.exclusions,
        )


class GraphProgressEvent(BaseModel):
    """One safe progress item containing only an allowlisted canonical node name."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    sequence: Annotated[int, Field(strict=True, ge=1)]
    node_name: NonEmptyUiText


class EvidenceSourceView(BaseModel):
    """Concise evidence provenance suitable for Candidate display."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    evidence_id: NonEmptyUiText
    claim: NonEmptyUiText
    source_url: HttpUrl
    source_kind: SourceKind
    confidence: EvidenceConfidence
    directly_supported: bool


class ProspectiveSupervisorView(BaseModel):
    """Discovery-only Supervisor projection for the prospective-results stage."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    supervisor_id: NonEmptyUiText
    full_name: NonEmptyUiText
    institution: NonEmptyUiText
    department: NonEmptyUiText
    profile_url: HttpUrl
    status: Literal[SupervisorLifecycleStatus.PROSPECTIVE]


class VerifiedSupervisorView(BaseModel):
    """Evidence-backed Supervisor result with optional Research Fit evaluation."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    supervisor_id: NonEmptyUiText
    full_name: NonEmptyUiText
    institution: NonEmptyUiText
    department: NonEmptyUiText
    profile_url: HttpUrl
    verification_status: VerificationStatus
    research_fit_score: Annotated[int, Field(strict=True, ge=0, le=100)] | None = None
    fit_explanation: NonEmptyUiText | None = None
    evidence_confidence: EvidenceConfidence
    evidence_sources: tuple[EvidenceSourceView, ...] = Field(min_length=1)
    source_links: tuple[HttpUrl, ...] = Field(min_length=1)
    availability_status: AvailabilityStatus
    concerns: tuple[NonEmptyUiText, ...] = ()
    independent_review_status: NonEmptyUiText = "not_reviewed"
    requires_candidate_attention: bool = False


class RecoverableUiError(BaseModel):
    """Sanitized graph/provider problem that is safe to render to a Candidate."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    code: NonEmptyUiText
    message: NonEmptyUiText
    recoverable: bool


class UiRunSnapshot(BaseModel):
    """Read-only UI projection; deliberately not a copy of ScholarPathState."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    stage: UiStage
    checkpoint_token: NonEmptyUiText
    progress_events: tuple[GraphProgressEvent, ...] = ()
    prospective_supervisors: tuple[ProspectiveSupervisorView, ...] = ()
    verified_supervisors: tuple[VerifiedSupervisorView, ...] = ()
    review_supervisors: tuple[VerifiedSupervisorView, ...] = ()
    shortlisted_supervisors: tuple[VerifiedSupervisorView, ...] = ()
    review_iteration: Annotated[int, Field(strict=True, ge=1)] | None = None
    maximum_review_iterations: Annotated[int, Field(strict=True, ge=1)] | None = None
    shortlist_briefing: NonEmptyUiText | None = None
    errors: tuple[RecoverableUiError, ...] = ()

    @model_validator(mode="after")
    def active_stage_must_have_its_required_projection(self) -> UiRunSnapshot:
        """Prevent the renderer from inferring missing workflow state."""
        if self.stage is UiStage.REVIEW_SUPERVISORS:
            if not self.review_supervisors:
                raise ValueError("Candidate review requires proposed Verified Supervisors")
            if self.review_iteration is None or self.maximum_review_iterations is None:
                raise ValueError("Candidate review requires bounded iteration information")
        if self.stage is UiStage.SUPERVISOR_SHORTLIST and not self.shortlisted_supervisors:
            raise ValueError("The shortlist stage requires approved Shortlisted Supervisors")
        return self
