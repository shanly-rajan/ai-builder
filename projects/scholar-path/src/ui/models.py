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
    SearchResultRejectionCounts,
    SourceKind,
    SupervisorLifecycleStatus,
    VerificationStatus,
)
from ..graph.verification import AlternateSourceRejectionCounts
from ..tools import SearchErrorCategory, SearchProvider

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


class UiDiscoveryRoute(StrEnum):
    """Privacy-safe current-round discovery outcome shown without search content."""

    PRIMARY = "primary"
    FALLBACK = "fallback"
    DOWNSTREAM = "downstream"
    STOPPED = "stopped"
    STOPPED_RECOVERABLY = "stopped_recoverably"


class DiscoveryAttemptView(BaseModel):
    """Aggregate facts for one provider attempt without its query or returned content."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    provider: SearchProvider
    attempt_number: Annotated[int, Field(strict=True, ge=1)]
    raw_result_count: Annotated[int, Field(strict=True, ge=0)]
    plausible_supervisor_count: Annotated[int, Field(strict=True, ge=0)]
    rejection_counts: SearchResultRejectionCounts | None = None
    error_category: SearchErrorCategory | None = None
    route: Literal[UiDiscoveryRoute.PRIMARY, UiDiscoveryRoute.FALLBACK]

    @model_validator(mode="after")
    def plausible_count_must_not_exceed_raw_count(self) -> DiscoveryAttemptView:
        """Prevent an impossible diagnostic from reaching the interface."""
        if self.plausible_supervisor_count > self.raw_result_count:
            raise ValueError("plausible_supervisor_count must not exceed raw_result_count")
        if self.error_category is not None and self.rejection_counts is not None:
            raise ValueError("a failed attempt cannot contain rejection_counts")
        if (
            self.error_category is None
            and self.rejection_counts is not None
            and self.rejection_counts.total + self.plausible_supervisor_count
            != self.raw_result_count
        ):
            raise ValueError("successful attempt counts must account for every raw result")
        return self


class DiscoveryDiagnosticsView(BaseModel):
    """Current-round provider diagnostics with all search content deliberately omitted."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    attempts: tuple[DiscoveryAttemptView, ...] = Field(min_length=1)
    raw_result_count: Annotated[int, Field(strict=True, ge=0)]
    plausible_supervisor_count: Annotated[int, Field(strict=True, ge=0)]
    retained_prospective_supervisor_count: Annotated[int, Field(strict=True, ge=0)]
    rejection_counts: SearchResultRejectionCounts | None = None
    fallback_search_used: bool
    route: UiDiscoveryRoute

    @model_validator(mode="after")
    def totals_must_match_attempts(self) -> DiscoveryDiagnosticsView:
        """Keep aggregate totals deterministic and auditable from attempt records."""
        if self.raw_result_count != sum(item.raw_result_count for item in self.attempts):
            raise ValueError("raw_result_count must equal the attempt total")
        if self.plausible_supervisor_count != sum(
            item.plausible_supervisor_count for item in self.attempts
        ):
            raise ValueError("plausible_supervisor_count must equal the attempt total")
        if self.fallback_search_used != any(
            item.route is UiDiscoveryRoute.FALLBACK for item in self.attempts
        ):
            raise ValueError("fallback_search_used must match the attempt routes")
        successful_attempts = tuple(item for item in self.attempts if item.error_category is None)
        rejection_breakdown_available = bool(successful_attempts) and all(
            item.rejection_counts is not None for item in successful_attempts
        )
        if not rejection_breakdown_available:
            if self.rejection_counts is not None:
                raise ValueError(
                    "rejection_counts must be absent when an attempt breakdown is unavailable"
                )
            return self
        expected_counts = SearchResultRejectionCounts()
        for attempt in successful_attempts:
            if attempt.rejection_counts is not None:
                expected_counts = expected_counts.combine(attempt.rejection_counts)
        if self.rejection_counts != expected_counts:
            raise ValueError("rejection_counts must equal the successful attempt totals")
        return self


class AlternateSourceDiagnosticsView(BaseModel):
    """Current-round alternate-profile diagnostics with all source content omitted."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    attempted_supervisor_count: Annotated[int, Field(strict=True, ge=1)]
    result_count: Annotated[int, Field(strict=True, ge=0)]
    eligible_result_count: Annotated[int, Field(strict=True, ge=0)]
    selected_source_count: Annotated[int, Field(strict=True, ge=0)]
    no_results_count: Annotated[int, Field(strict=True, ge=0)]
    rejected_all_count: Annotated[int, Field(strict=True, ge=0)]
    provider_error_count: Annotated[int, Field(strict=True, ge=0)]
    not_configured_count: Annotated[int, Field(strict=True, ge=0)]
    rejection_counts: AlternateSourceRejectionCounts

    @model_validator(mode="after")
    def aggregate_counts_must_be_consistent(self) -> AlternateSourceDiagnosticsView:
        """Prevent incomplete or impossible evidence-source diagnostics."""
        outcome_count = (
            self.selected_source_count
            + self.no_results_count
            + self.rejected_all_count
            + self.provider_error_count
            + self.not_configured_count
        )
        if outcome_count != self.attempted_supervisor_count:
            raise ValueError("Alternate-source outcomes must equal the attempt count")
        if self.eligible_result_count + self.rejection_counts.total != self.result_count:
            raise ValueError("Alternate-source result counts must be fully accounted for")
        if self.selected_source_count > self.eligible_result_count:
            raise ValueError("Selected sources cannot exceed eligible results")
        return self


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
    occurrence_count: Annotated[int, Field(strict=True, ge=1)] = 1


class UiRunSnapshot(BaseModel):
    """Read-only UI projection; deliberately not a copy of ScholarPathState."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    stage: UiStage
    checkpoint_token: NonEmptyUiText
    progress_events: tuple[GraphProgressEvent, ...] = ()
    discovery_diagnostics: DiscoveryDiagnosticsView | None = None
    alternate_source_diagnostics: AlternateSourceDiagnosticsView | None = None
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
