"""Typed, privacy-safe contracts for ScholarPath evaluation scenarios and outputs."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    JsonValue,
    StringConstraints,
    TypeAdapter,
    field_validator,
    model_validator,
)

from ..domain import (
    AvailabilityStatus,
    CandidateReviewAction,
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewStatus,
    ResearchFitAssessment,
    SearchPlan,
    VerificationStatus,
)
from ..graph import ReviewStatus
from ..tools import SearchErrorCategory, SearchProvider

NonEmptyEvaluationString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class EvaluationModel(BaseModel):
    """Strict immutable base for dataset and target-output contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )


class EvaluationTargetKind(StrEnum):
    """Target families supported by the M12 evaluation suite."""

    SEARCH_PLANNING = "search_planning"
    EVIDENCE_VERIFICATION = "evidence_verification"
    RESEARCH_FIT = "research_fit"
    GRAPH_FAKE = "graph_fake"
    GRAPH_LIVE = "graph_live"


class CandidateReviewOutcome(StrEnum):
    """Privacy-safe outcome attached to an evaluation trace."""

    NOT_APPLICABLE = "not_applicable"
    AWAITING_REVIEW = "awaiting_review"
    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_MORE = "request_more"


class CandidatePreferenceProjection(EvaluationModel):
    """Candidate preferences needed for evaluation, without identity or full prose."""

    research_topics: tuple[NonEmptyEvaluationString, ...] = Field(min_length=1)
    preferred_regions: tuple[NonEmptyEvaluationString, ...] = ()
    preferred_study_modes: tuple[NonEmptyEvaluationString, ...] = ()
    preferred_research_orientation: NonEmptyEvaluationString | None = None
    methodological_interests: tuple[NonEmptyEvaluationString, ...] = ()
    exclusions: tuple[NonEmptyEvaluationString, ...] = ()


class EvaluationExpectation(EvaluationModel):
    """Optional deterministic expectations attached to one curated scenario."""

    expected_availability_status: AvailabilityStatus | None = None
    expected_fallback_search_used: bool | None = None
    expected_review_outcome: CandidateReviewOutcome | None = None
    expected_interrupted: bool | None = None
    expected_supervisor_ids: tuple[NonEmptyEvaluationString, ...] = ()
    expected_proposed_supervisor_ids: tuple[NonEmptyEvaluationString, ...] = ()
    expected_shortlisted_supervisor_ids: tuple[NonEmptyEvaluationString, ...] = ()
    expected_rejected_supervisor_ids: tuple[NonEmptyEvaluationString, ...] = ()
    minimum_research_fit_score: Annotated[int, Field(strict=True, ge=0, le=100)] | None = None
    maximum_research_fit_score: Annotated[int, Field(strict=True, ge=0, le=100)] | None = None
    maximum_duplicate_supervisor_rate: Annotated[
        float,
        Field(strict=True, ge=0.0, le=1.0),
    ] = 0.0
    minimum_you_attempts: Annotated[int, Field(strict=True, ge=0)] = 0
    minimum_tavily_attempts: Annotated[int, Field(strict=True, ge=0)] = 0
    minimum_multi_query_provenance_count: Annotated[int, Field(strict=True, ge=0)] = 0

    @model_validator(mode="after")
    def score_bounds_must_be_ordered(self) -> Self:
        """Reject an impossible expected Research Fit interval."""
        if (
            self.minimum_research_fit_score is not None
            and self.maximum_research_fit_score is not None
            and self.minimum_research_fit_score > self.maximum_research_fit_score
        ):
            raise ValueError("minimum Research Fit Score must not exceed maximum")
        return self


class EvaluationScenario(EvaluationModel):
    """One synthetic dataset row routed to an evaluation target."""

    scenario_id: NonEmptyEvaluationString
    title: NonEmptyEvaluationString
    description: NonEmptyEvaluationString
    target: EvaluationTargetKind
    tags: tuple[NonEmptyEvaluationString, ...] = ()
    splits: tuple[NonEmptyEvaluationString, ...] = Field(min_length=1)
    candidate_preferences: CandidatePreferenceProjection | None = None
    inputs: dict[str, JsonValue] = Field(default_factory=dict)
    config: dict[str, JsonValue] = Field(default_factory=dict)
    expected: EvaluationExpectation = Field(default_factory=EvaluationExpectation)

    @field_validator("tags", "splits")
    @classmethod
    def labels_must_be_unique(cls, values: tuple[str, ...]) -> tuple[str, ...]:
        """Keep dataset routing labels deterministic."""
        normalized = [value.casefold() for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Evaluation labels must be unique")
        return values


class SearchAttemptProjection(EvaluationModel):
    """Provider audit data with the originating query deliberately omitted."""

    provider_used: SearchProvider
    attempt_number: Annotated[int, Field(strict=True, ge=1)]
    result_count: Annotated[int, Field(strict=True, ge=0)]
    plausible_supervisor_count: Annotated[int, Field(strict=True, ge=0)]
    error_category: SearchErrorCategory | None = None
    retryable: bool = False
    discovery_round: Annotated[int, Field(strict=True, ge=1)]

    @model_validator(mode="after")
    def counts_must_be_consistent(self) -> Self:
        """Reject impossible privacy-safe attempt summaries."""
        if self.plausible_supervisor_count > self.result_count:
            raise ValueError("plausible Supervisor count cannot exceed result count")
        if self.error_category is None and self.retryable:
            raise ValueError("a successful attempt cannot be retryable")
        if self.error_category is not None and self.plausible_supervisor_count:
            raise ValueError("a failed attempt cannot retain plausible profiles")
        return self


class EvidenceReferenceProjection(EvaluationModel):
    """Bounded evidence projection that omits supporting excerpts and page content."""

    evidence_id: NonEmptyEvaluationString
    supervisor_id: NonEmptyEvaluationString
    claim_type: EvidenceClaimType
    claim_summary: NonEmptyEvaluationString
    source_url: HttpUrl
    directly_supported: bool
    confidence: EvidenceConfidence
    availability_status: AvailabilityStatus | None = None

    @model_validator(mode="after")
    def availability_value_must_match_claim_type(self) -> Self:
        """Retain the domain separation between evidence and availability."""
        if self.claim_type is EvidenceClaimType.AVAILABILITY:
            if self.availability_status not in {
                AvailabilityStatus.CONFIRMED_ACCEPTING,
                AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
            }:
                raise ValueError("availability evidence requires an explicit supported status")
        elif self.availability_status is not None:
            raise ValueError("only availability evidence may carry an availability status")
        return self


class VerificationRecordProjection(EvaluationModel):
    """Verification outcome without Supervisor identity prose or extracted pages."""

    supervisor_id: NonEmptyEvaluationString
    verification_status: VerificationStatus
    availability_status: AvailabilityStatus
    evidence: tuple[EvidenceReferenceProjection, ...] = ()
    verification_concerns: tuple[NonEmptyEvaluationString, ...] = ()
    missing_required_evidence: tuple[NonEmptyEvaluationString, ...] = ()
    verified_supervisor_present: bool

    @model_validator(mode="after")
    def evidence_must_belong_to_record(self) -> Self:
        """Keep every projected claim scoped to the same Supervisor."""
        if any(item.supervisor_id != self.supervisor_id for item in self.evidence):
            raise ValueError("verification evidence must reference this Supervisor")
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("verification evidence identifiers must be unique")
        return self


class ResearchFitAssessmentProjection(EvaluationModel):
    """One typed assessment plus the bounded evidence visible to evaluators."""

    assessment: ResearchFitAssessment
    evidence: tuple[EvidenceReferenceProjection, ...]

    @model_validator(mode="after")
    def assessment_and_evidence_must_match(self) -> Self:
        """Reject cross-Supervisor evidence before evaluators inspect citations."""
        if any(item.supervisor_id != self.assessment.supervisor_id for item in self.evidence):
            raise ValueError("Research Fit evidence must reference the assessed Supervisor")
        return self


class IndependentReviewProjection(EvaluationModel):
    """Evidence-ID-based independent-review outcome without the original inputs."""

    supervisor_id: NonEmptyEvaluationString
    review_status: IndependentReviewStatus
    effective_score: Annotated[int, Field(strict=True, ge=0, le=100)]
    effective_rationale: NonEmptyEvaluationString
    effective_confidence: EvidenceConfidence
    unsupported_claim_ids: tuple[NonEmptyEvaluationString, ...] = ()
    overlooked_evidence_ids: tuple[NonEmptyEvaluationString, ...] = ()
    critique: NonEmptyEvaluationString
    requires_candidate_attention: bool


class SupervisorProvenanceProjection(EvaluationModel):
    """Aggregate discovery provenance without search queries or URLs."""

    supervisor_id: NonEmptyEvaluationString
    provenance_count: Annotated[int, Field(strict=True, ge=1)]


class CandidateReviewProjection(EvaluationModel):
    """Explicit Candidate action without identity, preference prose, or reasons."""

    action: CandidateReviewAction
    supervisor_ids: tuple[NonEmptyEvaluationString, ...] = ()

    @model_validator(mode="after")
    def identifiers_must_match_action(self) -> Self:
        """Require explicit IDs for approval and rejection only."""
        if (
            self.action in {CandidateReviewAction.APPROVE, CandidateReviewAction.REJECT}
            and not self.supervisor_ids
        ):
            raise ValueError("approval and rejection require Supervisor identifiers")
        if len(self.supervisor_ids) != len(set(self.supervisor_ids)):
            raise ValueError("Candidate review Supervisor identifiers must be unique")
        return self


class ShortlistRecommendationProjection(EvaluationModel):
    """Candidate-facing recommendation fields used only by qualitative judges."""

    rank: Annotated[int, Field(strict=True, ge=1, le=5)]
    supervisor_id: NonEmptyEvaluationString
    institution: NonEmptyEvaluationString
    effective_score: Annotated[int, Field(strict=True, ge=0, le=100)]
    evidence_confidence: EvidenceConfidence
    availability_status: AvailabilityStatus
    strengths: tuple[NonEmptyEvaluationString, ...] = Field(min_length=1)
    concerns: tuple[NonEmptyEvaluationString, ...] = ()
    source_urls: tuple[HttpUrl, ...] = Field(min_length=1)


class SearchPlanningTargetOutput(EvaluationModel):
    """Typed result of the search-planning evaluation target."""

    target: Literal[EvaluationTargetKind.SEARCH_PLANNING]
    scenario_id: NonEmptyEvaluationString
    search_plan: SearchPlan


class EvidenceVerificationTargetOutput(EvaluationModel):
    """Typed result of the evidence-verification evaluation target."""

    target: Literal[EvaluationTargetKind.EVIDENCE_VERIFICATION]
    scenario_id: NonEmptyEvaluationString
    verification_records: tuple[VerificationRecordProjection, ...] = Field(min_length=1)


class ResearchFitTargetOutput(EvaluationModel):
    """Typed result of the Research Fit evaluation target."""

    target: Literal[EvaluationTargetKind.RESEARCH_FIT]
    scenario_id: NonEmptyEvaluationString
    candidate_preferences: CandidatePreferenceProjection
    assessments: tuple[ResearchFitAssessmentProjection, ...] = Field(min_length=1)


class GraphTargetOutput(EvaluationModel):
    """Bounded end-to-end graph projection safe for regression evaluation."""

    target: Literal[EvaluationTargetKind.GRAPH_FAKE, EvaluationTargetKind.GRAPH_LIVE]
    scenario_id: NonEmptyEvaluationString
    candidate_preferences: CandidatePreferenceProjection
    review_status: ReviewStatus
    interrupted: bool
    execution_log: tuple[NonEmptyEvaluationString, ...]
    fallback_search_used: bool
    search_attempts: tuple[SearchAttemptProjection, ...]
    raw_search_result_count: Annotated[int, Field(strict=True, ge=0)]
    plausible_profile_count: Annotated[int, Field(strict=True, ge=0)]
    prospective_supervisor_ids: tuple[NonEmptyEvaluationString, ...]
    supervisor_provenance: tuple[SupervisorProvenanceProjection, ...]
    verification_records: tuple[VerificationRecordProjection, ...]
    assessments: tuple[ResearchFitAssessmentProjection, ...]
    independent_reviews: tuple[IndependentReviewProjection, ...]
    proposed_supervisor_ids: tuple[NonEmptyEvaluationString, ...]
    shortlist_recommendations: tuple[ShortlistRecommendationProjection, ...]
    shortlisted_supervisor_ids: tuple[NonEmptyEvaluationString, ...]
    rejected_supervisor_ids: tuple[NonEmptyEvaluationString, ...]
    candidate_reviews: tuple[CandidateReviewProjection, ...]
    tool_error_codes: tuple[NonEmptyEvaluationString, ...]

    @model_validator(mode="after")
    def aggregate_counts_and_identifiers_must_be_consistent(self) -> Self:
        """Reject impossible count and identifier projections."""
        if self.plausible_profile_count > self.raw_search_result_count:
            raise ValueError("plausible profile count cannot exceed raw result count")
        proposed_ids = [item.supervisor_id for item in self.shortlist_recommendations]
        if proposed_ids and tuple(proposed_ids) != self.proposed_supervisor_ids:
            raise ValueError("recommendation identifiers must match proposed Supervisor order")
        return self


type EvaluationTargetOutput = Annotated[
    SearchPlanningTargetOutput
    | EvidenceVerificationTargetOutput
    | ResearchFitTargetOutput
    | GraphTargetOutput,
    Field(discriminator="target"),
]

EVALUATION_TARGET_OUTPUT_ADAPTER: TypeAdapter[EvaluationTargetOutput] = TypeAdapter(
    EvaluationTargetOutput
)


def parse_evaluation_target_output(value: object) -> EvaluationTargetOutput:
    """Validate an arbitrary LangSmith target result through the output union."""
    return EVALUATION_TARGET_OUTPUT_ADAPTER.validate_python(value)
