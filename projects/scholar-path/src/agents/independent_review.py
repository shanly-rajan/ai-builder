"""Provider-neutral independent review and deterministic assessment reconciliation."""

from __future__ import annotations

import re
from typing import Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from ..domain import (
    CandidateProfile,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewDecision,
    IndependentReviewFailureKind,
    IndependentReviewStatus,
    ReconciledResearchFitAssessment,
    ResearchFitAssessment,
    VerifiedSupervisor,
    evidence_claim_is_grounded_for_supervisor,
    lower_evidence_confidence,
    validate_research_fit_evidence,
    validate_research_fit_scoring_prose,
)

_CONFIDENCE_RANK = {
    EvidenceConfidence.LOW: 1,
    EvidenceConfidence.MEDIUM: 2,
    EvidenceConfidence.HIGH: 3,
}
_REVIEWABLE_FIT_EVIDENCE_TYPES = frozenset(
    {
        EvidenceClaimType.RESEARCH_INTEREST,
        EvidenceClaimType.METHODOLOGY,
        EvidenceClaimType.PUBLICATION,
        EvidenceClaimType.PROJECT,
    }
)
_REVIEW_AVAILABILITY_AUDIENCE_PATTERN = re.compile(
    r"\b(?:doctoral|phd|candidates?|students?|researchers?)\b",
    re.IGNORECASE,
)
_REVIEW_AVAILABILITY_ACTION_PATTERN = re.compile(
    r"\b(?:supervis(?:e|es|ed|ing|ion)|host(?:s|ed|ing)?|mentor(?:s|ed|ing)?|"
    r"accept(?:s|ed|ing)?|recruit(?:s|ed|ing)?|take\s+on|takes\s+on|taking\s+on|"
    r"openings?|room|space|capacity|bandwidth|slots?|funding|looking|keen|willing)\b",
    re.IGNORECASE,
)
_REVIEW_ADMISSION_ESTIMATE_PATTERN = re.compile(
    r"\b(?:strong|good|poor|high|low|promising|limited)\s+"
    r"(?:admission|acceptance)\s+(?:prospects?|outlook|chances?|odds?)\b|"
    r"\b(?:admission|acceptance)\s+(?:prospects?|outlook|chances?|odds?)\s+"
    r"(?:are|appear|seem)\b",
    re.IGNORECASE,
)


class IndependentReviewInput(BaseModel):
    """Complete, closed-world context supplied to the independent reviewer."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
        revalidate_instances="always",
    )

    candidate_profile: CandidateProfile
    verified_supervisor: VerifiedSupervisor
    evidence_claims: tuple[EvidenceClaim, ...]
    initial_assessment: ResearchFitAssessment

    @model_validator(mode="after")
    def records_must_describe_one_verified_supervisor(self) -> Self:
        """Prevent a reviewer from receiving mixed Supervisor evidence or scores."""
        supervisor = self.verified_supervisor
        if self.initial_assessment.supervisor_id != supervisor.supervisor_id:
            raise ValueError("Review assessment and Verified Supervisor identifiers must match")
        if self.evidence_claims != supervisor.evidence:
            raise ValueError("Review evidence must exactly match the verified evidence collection")
        validate_research_fit_evidence(supervisor, self.initial_assessment)
        return self

    @classmethod
    def from_domain(
        cls,
        candidate_profile: CandidateProfile,
        supervisor: VerifiedSupervisor,
        assessment: ResearchFitAssessment,
    ) -> Self:
        """Build a closed-world review input without searching or adding evidence."""
        return cls(
            candidate_profile=candidate_profile,
            verified_supervisor=supervisor,
            evidence_claims=supervisor.evidence,
            initial_assessment=assessment,
        )


class IndependentReviewResult(BaseModel):
    """Strict structured output proposed by an independent review model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    decision: IndependentReviewDecision
    recommended_score: StrictInt
    unsupported_claim_ids: list[str]
    overlooked_evidence_ids: list[str]
    confidence: EvidenceConfidence
    critique: str

    @field_validator("recommended_score")
    @classmethod
    def recommended_score_must_be_bounded(cls, value: int) -> int:
        """Keep provider schema simple while enforcing domain bounds locally."""
        if isinstance(value, bool) or not 0 <= value <= 100:
            raise ValueError("Recommended Research Fit Score must be between 0 and 100")
        return value

    @field_validator("unsupported_claim_ids", "overlooked_evidence_ids")
    @classmethod
    def evidence_identifiers_must_be_nonblank_and_unique(
        cls,
        values: list[str],
    ) -> list[str]:
        """Reject ambiguous reviewer references before reconciliation."""
        if any(not value.strip() for value in values):
            raise ValueError("Independent review evidence identifiers must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("Independent review evidence identifiers must be unique")
        return values

    @field_validator("critique")
    @classmethod
    def critique_must_be_safe_and_nonblank(cls, value: str) -> str:
        """Reject availability inference and admission likelihood from review prose."""
        if not value.strip():
            raise ValueError("Independent review critique must not be blank")
        if len(value.split()) > 120:
            raise ValueError("Independent review critique must not exceed 120 words")
        validate_research_fit_scoring_prose((value,))
        if _REVIEW_AVAILABILITY_AUDIENCE_PATTERN.search(
            value
        ) and _REVIEW_AVAILABILITY_ACTION_PATTERN.search(value):
            raise ValueError("Independent review must not infer Supervisor availability")
        if _REVIEW_ADMISSION_ESTIMATE_PATTERN.search(value):
            raise ValueError("Independent review must not estimate admission likelihood")
        return value

    @model_validator(mode="after")
    def decision_and_references_must_be_consistent(self) -> Self:
        """An accepted assessment cannot simultaneously request evidence changes."""
        if set(self.unsupported_claim_ids) & set(self.overlooked_evidence_ids):
            raise ValueError("The same evidence cannot be unsupported and overlooked")
        if self.decision is IndependentReviewDecision.ACCEPT and (
            self.unsupported_claim_ids or self.overlooked_evidence_ids
        ):
            raise ValueError("An accepted review cannot alter evidence references")
        return self


class IndependentReviewModelPort(Protocol):
    """Provider-neutral boundary implemented by Nebius and offline fakes."""

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        """Return a typed recommendation from only the supplied review context."""
        ...


class IndependentReviewModelError(RuntimeError):
    """Base error raised at the independent-review provider boundary."""


class IndependentReviewModelInvocationError(IndependentReviewModelError):
    """The provider request failed before a structured result was returned."""


class IndependentReviewModelOutputError(IndependentReviewModelError):
    """The provider response failed the structured review contract."""


class IndependentReviewPolicy(BaseModel):
    """Deterministic thresholds used to reconcile a model review."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    disagreement_threshold: StrictInt = 15

    @field_validator("disagreement_threshold")
    @classmethod
    def threshold_must_be_bounded(cls, value: int) -> int:
        """Constrain the threshold without exposing provider-specific configuration."""
        if isinstance(value, bool) or not 0 <= value <= 100:
            raise ValueError("Independent review disagreement threshold must be 0 through 100")
        return value


def _lower_of(
    first: EvidenceConfidence,
    second: EvidenceConfidence,
) -> EvidenceConfidence:
    return first if _CONFIDENCE_RANK[first] <= _CONFIDENCE_RANK[second] else second


def _unavailable_review(
    assessment: ResearchFitAssessment,
    failure_kind: IndependentReviewFailureKind,
) -> ReconciledResearchFitAssessment:
    """Build the required safe fallback while retaining the complete M7 assessment."""
    return ReconciledResearchFitAssessment(
        supervisor_id=assessment.supervisor_id,
        initial_assessment=assessment,
        effective_score=assessment.overall_score,
        effective_rationale=assessment.rationale,
        effective_supporting_evidence_ids=assessment.supporting_evidence_ids,
        effective_confidence=lower_evidence_confidence(assessment.confidence),
        review_status=IndependentReviewStatus.UNAVAILABLE,
        critique="Independent review was unavailable; the original assessment was preserved.",
        requires_candidate_attention=True,
        failure_kind=failure_kind,
    )


def reconcile_research_fit_assessment(
    supervisor: VerifiedSupervisor,
    assessment: ResearchFitAssessment,
    result: IndependentReviewResult | None,
    *,
    policy: IndependentReviewPolicy | None = None,
    failure_kind: IndependentReviewFailureKind | None = None,
) -> ReconciledResearchFitAssessment:
    """Reconcile one review using only validated evidence and deterministic rules."""
    if assessment.supervisor_id != supervisor.supervisor_id:
        raise ValueError("Review reconciliation requires matching Supervisor identifiers")
    validate_research_fit_evidence(supervisor, assessment)
    resolved_policy = policy or IndependentReviewPolicy()

    if result is None:
        return _unavailable_review(
            assessment,
            failure_kind or IndependentReviewFailureKind.MODEL_INVOCATION,
        )
    if failure_kind is not None:
        raise ValueError("A completed review result cannot also contain a failure category")

    if result.decision is IndependentReviewDecision.ACCEPT:
        return ReconciledResearchFitAssessment(
            supervisor_id=assessment.supervisor_id,
            initial_assessment=assessment,
            effective_score=assessment.overall_score,
            effective_rationale=assessment.rationale,
            effective_supporting_evidence_ids=assessment.supporting_evidence_ids,
            effective_confidence=assessment.confidence,
            review_status=IndependentReviewStatus.ACCEPTED,
            decision=result.decision,
            reviewer_confidence=result.confidence,
            critique=result.critique,
        )

    evidence_by_id = {claim.evidence_id: claim for claim in supervisor.evidence}
    initial_ids = assessment.supporting_evidence_ids
    initial_id_set = set(initial_ids)
    unsupported_ids = set(result.unsupported_claim_ids)
    overlooked_ids = set(result.overlooked_evidence_ids)
    referenced_ids = unsupported_ids | overlooked_ids
    references_unknown_evidence = not referenced_ids.issubset(evidence_by_id)
    unsupported_not_in_assessment = not unsupported_ids.issubset(initial_id_set)
    overlooked_already_used = bool(overlooked_ids & initial_id_set)
    unusable_overlooked_evidence = any(
        claim.claim_type not in _REVIEWABLE_FIT_EVIDENCE_TYPES
        or not claim.directly_supported
        or not evidence_claim_is_grounded_for_supervisor(claim, supervisor)
        for evidence_id in overlooked_ids
        if (claim := evidence_by_id.get(evidence_id)) is not None
    )
    if (
        references_unknown_evidence
        or unsupported_not_in_assessment
        or overlooked_already_used
        or unusable_overlooked_evidence
    ):
        return _unavailable_review(
            assessment,
            IndependentReviewFailureKind.INVALID_EVIDENCE_REFERENCE,
        )

    effective_ids = tuple(
        evidence_id for evidence_id in initial_ids if evidence_id not in unsupported_ids
    )
    effective_ids += tuple(
        claim.evidence_id for claim in supervisor.evidence if claim.evidence_id in overlooked_ids
    )
    if result.recommended_score > 0 and not effective_ids:
        return _unavailable_review(
            assessment,
            IndependentReviewFailureKind.INVALID_OUTPUT,
        )

    disagreement = abs(result.recommended_score - assessment.overall_score)
    effective_confidence = _lower_of(assessment.confidence, result.confidence)
    if effective_ids:
        weakest_effective_confidence = min(
            (evidence_by_id[evidence_id].confidence for evidence_id in effective_ids),
            key=_CONFIDENCE_RANK.__getitem__,
        )
        effective_confidence = _lower_of(
            effective_confidence,
            weakest_effective_confidence,
        )
    else:
        effective_confidence = EvidenceConfidence.LOW
    requires_attention = disagreement > resolved_policy.disagreement_threshold
    if requires_attention:
        effective_confidence = _lower_of(
            effective_confidence,
            lower_evidence_confidence(assessment.confidence),
        )

    return ReconciledResearchFitAssessment(
        supervisor_id=assessment.supervisor_id,
        initial_assessment=assessment,
        effective_score=result.recommended_score,
        effective_rationale=result.critique,
        effective_supporting_evidence_ids=effective_ids,
        effective_confidence=effective_confidence,
        review_status=IndependentReviewStatus.REVISED,
        decision=result.decision,
        reviewer_confidence=result.confidence,
        critique=result.critique,
        unsupported_claim_ids=tuple(result.unsupported_claim_ids),
        overlooked_evidence_ids=tuple(result.overlooked_evidence_ids),
        requires_candidate_attention=requires_attention,
    )


class IndependentReviewAgent:
    """Invoke an independent model and safely reconcile its structured review."""

    def __init__(
        self,
        model: IndependentReviewModelPort,
        *,
        policy: IndependentReviewPolicy | None = None,
    ) -> None:
        self._model = model
        self._policy = policy or IndependentReviewPolicy()

    def review(
        self,
        candidate_profile: CandidateProfile,
        supervisor: VerifiedSupervisor,
        assessment: ResearchFitAssessment,
    ) -> ReconciledResearchFitAssessment:
        """Review once; malformed or unavailable model output degrades safely."""
        review_input = IndependentReviewInput.from_domain(
            candidate_profile,
            supervisor,
            assessment,
        )
        try:
            raw_result = self._model.review(review_input)
            result = IndependentReviewResult.model_validate(raw_result)
        except IndependentReviewModelInvocationError:
            return reconcile_research_fit_assessment(
                supervisor,
                assessment,
                None,
                policy=self._policy,
                failure_kind=IndependentReviewFailureKind.MODEL_INVOCATION,
            )
        except (IndependentReviewModelOutputError, ValidationError, ValueError):
            return reconcile_research_fit_assessment(
                supervisor,
                assessment,
                None,
                policy=self._policy,
                failure_kind=IndependentReviewFailureKind.INVALID_OUTPUT,
            )
        except Exception:
            return reconcile_research_fit_assessment(
                supervisor,
                assessment,
                None,
                policy=self._policy,
                failure_kind=IndependentReviewFailureKind.MODEL_INVOCATION,
            )
        return reconcile_research_fit_assessment(
            supervisor,
            assessment,
            result,
            policy=self._policy,
        )
