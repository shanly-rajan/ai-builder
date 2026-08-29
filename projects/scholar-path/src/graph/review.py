"""Typed Candidate-review interrupt payloads and resume-value contracts."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StringConstraints,
    TypeAdapter,
)

from ..domain import (
    AvailabilityStatus,
    CandidatePreferenceRevision,
    EvidenceConfidence,
    IndependentReviewDecision,
    IndependentReviewStatus,
    ProposedSupervisorRecommendation,
    ProposedSupervisorShortlist,
)

NonEmptyReviewString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1),
]


class CandidateRejectionReason(BaseModel):
    """One explicit Candidate rejection and its Supervisor-specific reason."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    supervisor_id: NonEmptyReviewString
    reason: NonEmptyReviewString


class CandidateApproveResponse(BaseModel):
    """Candidate approval for an explicit ordered subset of the proposal."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    action: Literal["approve"]
    supervisor_ids: tuple[NonEmptyReviewString, ...] = Field(min_length=1, max_length=5)

    def model_post_init(self, __context: object) -> None:
        """Reject duplicate identifiers without changing Candidate ordering."""
        del __context
        if len(self.supervisor_ids) != len(set(self.supervisor_ids)):
            raise ValueError("Approved Supervisor identifiers must be unique")


class CandidateRejectResponse(BaseModel):
    """Candidate rejection response carrying one reason per Supervisor."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    action: Literal["reject"]
    rejections: tuple[CandidateRejectionReason, ...] = Field(min_length=1, max_length=5)

    def model_post_init(self, __context: object) -> None:
        """Reject duplicate rejection targets deterministically."""
        del __context
        supervisor_ids = [item.supervisor_id for item in self.rejections]
        if len(supervisor_ids) != len(set(supervisor_ids)):
            raise ValueError("Rejected Supervisor identifiers must be unique")


class CandidateRequestMoreResponse(BaseModel):
    """Candidate request to refine planning with explicit preference changes."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    action: Literal["request_more"]
    revised_preferences: CandidatePreferenceRevision


type CandidateReviewResponse = Annotated[
    CandidateApproveResponse | CandidateRejectResponse | CandidateRequestMoreResponse,
    Field(discriminator="action"),
]

_CANDIDATE_REVIEW_RESPONSE_ADAPTER: TypeAdapter[CandidateReviewResponse] = TypeAdapter(
    CandidateReviewResponse
)


class CandidateIndependentReviewOutcome(BaseModel):
    """Safe independent-review projection shown at the Candidate approval boundary."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    review_status: IndependentReviewStatus | Literal["not_reviewed"]
    decision: IndependentReviewDecision | None
    effective_score: Annotated[int, Field(strict=True, ge=0, le=100)]
    confidence: EvidenceConfidence
    critique: NonEmptyReviewString
    requires_candidate_attention: bool


class CandidateSupervisorReviewItem(BaseModel):
    """One evidence-backed proposed Supervisor rendered in the interrupt payload."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    rank: Annotated[int, Field(strict=True, ge=1, le=5)]
    supervisor_id: NonEmptyReviewString
    full_name: NonEmptyReviewString
    institution: NonEmptyReviewString
    department: NonEmptyReviewString
    profile_url: HttpUrl
    research_fit_score: Annotated[int, Field(strict=True, ge=0, le=100)]
    evidence_confidence: EvidenceConfidence
    source_links: tuple[HttpUrl, ...] = Field(min_length=1)
    availability_status: AvailabilityStatus
    concerns: tuple[NonEmptyReviewString, ...] = ()
    independent_review_outcome: CandidateIndependentReviewOutcome


class CandidateReviewInterruptPayload(BaseModel):
    """JSON-safe proposal presented when the graph pauses for Candidate control."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    kind: Literal["candidate_review_required"] = "candidate_review_required"
    candidate_id: NonEmptyReviewString
    question: NonEmptyReviewString = (
        "Review the proposed Supervisors and approve, reject, or request more options."
    )
    proposed_supervisor_shortlist: tuple[CandidateSupervisorReviewItem, ...] = Field(
        min_length=1,
        max_length=5,
    )
    allowed_actions: tuple[Literal["approve", "reject", "request_more"], ...] = (
        "approve",
        "reject",
        "request_more",
    )
    review_iteration: Annotated[int, Field(strict=True, ge=1)]
    maximum_review_iterations: Annotated[int, Field(strict=True, ge=1)]
    validation_error: str | None = None


def parse_candidate_review_response(value: object) -> CandidateReviewResponse:
    """Validate one JSON-compatible resume value against its action-specific schema."""
    return _CANDIDATE_REVIEW_RESPONSE_ADAPTER.validate_python(value)


def candidate_review_response_value(response: CandidateReviewResponse) -> dict[str, object]:
    """Return the JSON-compatible value supplied to ``Command(resume=...)``."""
    return response.model_dump(mode="json")


def _source_links(recommendation: ProposedSupervisorRecommendation) -> tuple[HttpUrl, ...]:
    """Collect stable unique profile and evidence URLs without page content."""
    ordered_urls = (
        recommendation.supervisor.profile_url,
        *(claim.source_url for claim in recommendation.supervisor.evidence),
    )
    deduplicated: list[HttpUrl] = []
    seen: set[str] = set()
    for source_url in ordered_urls:
        if str(source_url) not in seen:
            seen.add(str(source_url))
            deduplicated.append(source_url)
    return tuple(deduplicated)


def _independent_review_outcome(
    recommendation: ProposedSupervisorRecommendation,
) -> CandidateIndependentReviewOutcome:
    """Project the reconciled M8 review, including an explicit unavailable state."""
    review = recommendation.independent_review
    if review is None:
        return CandidateIndependentReviewOutcome(
            review_status="not_reviewed",
            decision=None,
            effective_score=recommendation.assessment.overall_score,
            confidence=recommendation.assessment.confidence,
            critique="Independent review was not available for this proposal.",
            requires_candidate_attention=True,
        )
    return CandidateIndependentReviewOutcome(
        review_status=review.review_status,
        decision=review.decision,
        effective_score=review.effective_score,
        confidence=review.effective_confidence,
        critique=review.critique,
        requires_candidate_attention=review.requires_candidate_attention,
    )


def build_candidate_review_interrupt_payload(
    proposal: ProposedSupervisorShortlist,
    *,
    review_iteration: int,
    maximum_review_iterations: int,
    validation_error: str | None = None,
) -> CandidateReviewInterruptPayload:
    """Build the deterministic, provenance-preserving Candidate review projection."""
    items = tuple(
        CandidateSupervisorReviewItem(
            rank=recommendation.rank,
            supervisor_id=recommendation.supervisor.supervisor_id,
            full_name=recommendation.supervisor.full_name,
            institution=recommendation.supervisor.institution,
            department=recommendation.supervisor.department,
            profile_url=recommendation.supervisor.profile_url,
            research_fit_score=recommendation.effective_score,
            evidence_confidence=recommendation.evidence_confidence,
            source_links=_source_links(recommendation),
            availability_status=recommendation.availability_status,
            concerns=recommendation.concerns,
            independent_review_outcome=_independent_review_outcome(recommendation),
        )
        for recommendation in proposal.recommendations
    )
    return CandidateReviewInterruptPayload(
        candidate_id=proposal.candidate_id,
        proposed_supervisor_shortlist=items,
        review_iteration=review_iteration,
        maximum_review_iterations=maximum_review_iterations,
        validation_error=validation_error,
    )


def candidate_review_payload_from_graph_output(
    output: Mapping[str, object],
) -> CandidateReviewInterruptPayload | None:
    """Restore the first typed Candidate payload from LangGraph's v1 invoke output."""
    raw_interrupts = output.get("__interrupt__")
    if not isinstance(raw_interrupts, Sequence) or isinstance(raw_interrupts, (str, bytes)):
        return None
    for interrupt_record in raw_interrupts:
        raw_value = getattr(interrupt_record, "value", None)
        if raw_value is not None:
            return CandidateReviewInterruptPayload.model_validate(raw_value)
    return None
