"""Evidence-bound Research Fit evaluation through an injected structured model."""

from __future__ import annotations

from enum import StrEnum
from typing import Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    field_validator,
    model_validator,
)

from ..domain import (
    CandidatePreferenceRevision,
    CandidateProfile,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    ResearchFitAssessment,
    ResearchFitBreakdown,
    ResearchFitComponentAssessment,
    ResearchFitRubric,
    SourceKind,
    VerifiedSupervisor,
    derive_research_fit_confidence,
    validate_research_fit_evidence,
    validate_research_fit_scoring_prose,
)

MAX_RESEARCH_FIT_OUTPUT_ATTEMPTS = 2

_COMPONENT_NAMES = (
    "topic_alignment",
    "methodological_alignment",
    "research_orientation_alignment",
    "recent_research_alignment",
    "practical_constraint_alignment",
)
_ALLOWED_EVIDENCE_TYPES: dict[str, frozenset[EvidenceClaimType]] = {
    "topic_alignment": frozenset(
        {
            EvidenceClaimType.RESEARCH_INTEREST,
            EvidenceClaimType.PUBLICATION,
            EvidenceClaimType.PROJECT,
        }
    ),
    "methodological_alignment": frozenset(
        {
            EvidenceClaimType.METHODOLOGY,
            EvidenceClaimType.RESEARCH_INTEREST,
            EvidenceClaimType.PUBLICATION,
            EvidenceClaimType.PROJECT,
        }
    ),
    "research_orientation_alignment": frozenset(
        {
            EvidenceClaimType.RESEARCH_INTEREST,
            EvidenceClaimType.METHODOLOGY,
            EvidenceClaimType.PUBLICATION,
            EvidenceClaimType.PROJECT,
        }
    ),
    "recent_research_alignment": frozenset(
        {
            EvidenceClaimType.PUBLICATION,
            EvidenceClaimType.PROJECT,
        }
    ),
    "practical_constraint_alignment": frozenset({EvidenceClaimType.CURRENT_AFFILIATION}),
}
_CONFIDENCE_RANK = {
    EvidenceConfidence.LOW: 1,
    EvidenceConfidence.MEDIUM: 2,
    EvidenceConfidence.HIGH: 3,
}


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


class ResearchFitEvidenceSummary(BaseModel):
    """Minimal directly supported evidence exposed to the scoring model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    evidence_id: str = Field(min_length=1)
    claim_type: EvidenceClaimType
    claim: str = Field(min_length=1)
    supporting_excerpt: str = Field(min_length=1)
    confidence: EvidenceConfidence
    source_kind: SourceKind
    activity_year: int | None


class ResearchFitInput(BaseModel):
    """Privacy-minimized Candidate and Supervisor context sent to a model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    research_topics: tuple[str, ...] = Field(min_length=1)
    methodological_interests: tuple[str, ...]
    preferred_research_orientation: str | None
    preferred_regions: tuple[str, ...]
    preferred_study_modes: tuple[str, ...]
    exclusions: tuple[str, ...]
    supervisor_id: str = Field(min_length=1)
    supervisor_name: str = Field(min_length=1)
    supervisor_institution: str = Field(min_length=1)
    supervisor_department: str = Field(min_length=1)
    evidence: tuple[ResearchFitEvidenceSummary, ...]

    @model_validator(mode="after")
    def evidence_identifiers_must_be_unique(self) -> Self:
        """Keep model-visible evidence citations unambiguous."""
        evidence_ids = [item.evidence_id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Research Fit input evidence identifiers must be unique")
        return self

    @classmethod
    def from_domain(
        cls,
        candidate_profile: CandidateProfile,
        supervisor: VerifiedSupervisor,
        preferences: CandidatePreferenceRevision | None = None,
    ) -> Self:
        """Map only scoring inputs, excluding Candidate identity and full research prose."""

        research_topics = (
            preferences.research_topics
            if preferences is not None and preferences.research_topics is not None
            else candidate_profile.research_topics
        )
        methodological_interests = (
            preferences.methodological_interests
            if preferences is not None and preferences.methodological_interests is not None
            else candidate_profile.methodological_interests
        )
        preferred_research_orientation = (
            preferences.preferred_research_orientation
            if preferences is not None and preferences.preferred_research_orientation is not None
            else candidate_profile.preferred_research_orientation
        )
        preferred_regions = (
            preferences.preferred_regions
            if preferences is not None and preferences.preferred_regions is not None
            else candidate_profile.preferred_regions
        )
        preferred_study_modes = (
            preferences.preferred_study_modes
            if preferences is not None and preferences.preferred_study_modes is not None
            else candidate_profile.preferred_study_modes
        )
        exclusions = (
            preferences.exclusions
            if preferences is not None and preferences.exclusions is not None
            else candidate_profile.exclusions
        )

        evidence = tuple(
            ResearchFitEvidenceSummary(
                evidence_id=claim.evidence_id,
                claim_type=claim.claim_type,
                claim=claim.claim,
                supporting_excerpt=claim.supporting_excerpt,
                confidence=claim.confidence,
                source_kind=claim.source_kind,
                activity_year=claim.activity_year,
            )
            for claim in supervisor.evidence
            if claim.directly_supported
            and claim.supporting_excerpt is not None
            and claim.claim_type is not EvidenceClaimType.AVAILABILITY
        )
        return cls(
            research_topics=research_topics,
            methodological_interests=methodological_interests,
            preferred_research_orientation=preferred_research_orientation,
            preferred_regions=preferred_regions,
            preferred_study_modes=preferred_study_modes,
            exclusions=exclusions,
            supervisor_id=supervisor.supervisor_id,
            supervisor_name=supervisor.full_name,
            supervisor_institution=supervisor.institution,
            supervisor_department=supervisor.department,
            evidence=evidence,
        )


class StructuredResearchFitComponent(BaseModel):
    """One model-proposed component score with explicit evidence citations."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    score: StrictInt
    rationale: str
    supporting_evidence_ids: list[str]
    confidence: EvidenceConfidence
    evidence_gap: str | None

    @field_validator("score")
    @classmethod
    def score_must_be_an_integer_in_global_range(cls, value: int) -> int:
        """Validate global bounds outside the provider JSON-schema metadata."""
        if isinstance(value, bool) or not 0 <= value <= 100:
            raise ValueError("Research Fit component score must be between 0 and 100")
        return value

    @field_validator("rationale")
    @classmethod
    def rationale_must_not_be_blank(cls, value: str) -> str:
        """Reject empty reasoning without adding strict-schema constraints."""
        if not value.strip():
            raise ValueError("Research Fit component rationale must not be blank")
        return value

    @field_validator("supporting_evidence_ids")
    @classmethod
    def citations_must_be_nonblank_and_unique(cls, values: list[str]) -> list[str]:
        """Reject ambiguous or repeated citations before domain conversion."""
        if any(not value.strip() for value in values):
            raise ValueError("Research Fit evidence identifiers must not be blank")
        if len(values) != len(set(values)):
            raise ValueError("Research Fit evidence identifiers must be unique")
        return values

    @model_validator(mode="after")
    def missing_evidence_must_receive_no_points(self) -> Self:
        """Make evidence gaps explicit and prevent unsupported points."""
        if self.score > 0 and not self.supporting_evidence_ids:
            raise ValueError("A positive Research Fit component requires evidence")
        if not self.supporting_evidence_ids:
            if self.confidence is not EvidenceConfidence.LOW:
                raise ValueError("A Research Fit component without evidence must be low confidence")
            if self.evidence_gap is None or not self.evidence_gap.strip():
                raise ValueError("A Research Fit component without evidence needs an evidence gap")
        return self


class StructuredResearchFitResult(BaseModel):
    """Complete structured model output; arithmetic is intentionally absent."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    topic_alignment: StructuredResearchFitComponent
    methodological_alignment: StructuredResearchFitComponent
    research_orientation_alignment: StructuredResearchFitComponent
    recent_research_alignment: StructuredResearchFitComponent
    practical_constraint_alignment: StructuredResearchFitComponent
    overall_rationale: str
    concerns: list[str]

    @field_validator("overall_rationale")
    @classmethod
    def overall_rationale_must_not_be_blank(cls, value: str) -> str:
        """Reject empty reasoning without adding strict-schema constraints."""
        if not value.strip():
            raise ValueError("Overall Research Fit rationale must not be blank")
        return value

    @field_validator("concerns")
    @classmethod
    def concerns_must_be_nonblank_and_unique(cls, values: list[str]) -> list[str]:
        """Keep concerns concise enough to reference deterministically."""
        if any(not value.strip() for value in values):
            raise ValueError("Research Fit concerns must not be blank")
        normalized = [_normalized_text(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("Research Fit concerns must be distinct")
        return values


class ResearchFitModelPort(Protocol):
    """Provider-neutral boundary implemented by OpenAI and offline fakes."""

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        """Return typed component proposals without calculating a total."""
        ...


class ResearchFitModelError(RuntimeError):
    """Base error raised by a Research Fit model adapter."""


class ResearchFitModelInvocationError(ResearchFitModelError):
    """The provider request failed before a structured response was returned."""


class ResearchFitModelOutputError(ResearchFitModelError):
    """The provider response failed the structured Research Fit contract."""


class ResearchFitFailureKind(StrEnum):
    """Sanitized Research Fit failure categories safe for graph state."""

    MODEL_INVOCATION = "model_invocation"
    INVALID_OUTPUT = "invalid_output"


class ResearchFitEvaluationError(RuntimeError):
    """Sanitized terminal error after the bounded evaluation policy is applied."""

    def __init__(self, kind: ResearchFitFailureKind, attempts: int) -> None:
        super().__init__("Research Fit evaluation failed at the typed model boundary.")
        self.kind = kind
        self.attempts = attempts


class ResearchFitEvaluationAgent:
    """Build, validate, and total one evidence-grounded Research Fit assessment."""

    def __init__(self, model: ResearchFitModelPort) -> None:
        self._model = model

    def evaluate(
        self,
        candidate_profile: CandidateProfile,
        supervisor: VerifiedSupervisor,
        *,
        preferences: CandidatePreferenceRevision | None = None,
        rubric: ResearchFitRubric | None = None,
    ) -> ResearchFitAssessment:
        """Evaluate one Verified Supervisor with one bounded invalid-output retry."""
        resolved_rubric = rubric or ResearchFitRubric()
        fit_input = ResearchFitInput.from_domain(
            candidate_profile,
            supervisor,
            preferences,
        )

        for attempt in range(1, MAX_RESEARCH_FIT_OUTPUT_ATTEMPTS + 1):
            try:
                raw_result = self._model.evaluate(fit_input, resolved_rubric)
                result = StructuredResearchFitResult.model_validate(raw_result)
                return self._to_assessment(
                    result,
                    fit_input,
                    supervisor,
                    resolved_rubric,
                )
            except ResearchFitModelInvocationError as error:
                raise ResearchFitEvaluationError(
                    ResearchFitFailureKind.MODEL_INVOCATION,
                    attempt,
                ) from error
            except (
                ResearchFitModelOutputError,
                ValidationError,
                ValueError,
            ) as error:
                if attempt == MAX_RESEARCH_FIT_OUTPUT_ATTEMPTS:
                    raise ResearchFitEvaluationError(
                        ResearchFitFailureKind.INVALID_OUTPUT,
                        attempt,
                    ) from error
            except Exception as error:
                raise ResearchFitEvaluationError(
                    ResearchFitFailureKind.MODEL_INVOCATION,
                    attempt,
                ) from error

        raise AssertionError("The bounded Research Fit loop must return or raise")

    @staticmethod
    def _component_items(
        result: StructuredResearchFitResult,
    ) -> tuple[tuple[str, StructuredResearchFitComponent], ...]:
        return tuple((name, getattr(result, name)) for name in _COMPONENT_NAMES)

    @classmethod
    def _to_assessment(
        cls,
        result: StructuredResearchFitResult,
        fit_input: ResearchFitInput,
        supervisor: VerifiedSupervisor,
        rubric: ResearchFitRubric,
    ) -> ResearchFitAssessment:
        """Apply all deterministic evidence, bounds, confidence, and arithmetic rules."""
        cls._reject_disallowed_scoring_prose(result)
        visible_evidence = {item.evidence_id: item for item in fit_input.evidence}
        domain_evidence = {claim.evidence_id: claim for claim in supervisor.evidence}
        components: dict[str, ResearchFitComponentAssessment] = {}

        for component_name, draft in cls._component_items(result):
            maximum = rubric.weights[component_name]
            if draft.score > maximum:
                raise ResearchFitModelOutputError(
                    f"{component_name} exceeds the configured Research Fit rubric weight."
                )
            cited_claims = cls._validate_component_citations(
                component_name,
                draft,
                fit_input,
                visible_evidence,
                domain_evidence,
                rubric,
            )
            confidence = cls._bounded_component_confidence(draft.confidence, cited_claims)
            components[component_name] = ResearchFitComponentAssessment(
                score=draft.score,
                rationale=draft.rationale,
                supporting_evidence_ids=tuple(draft.supporting_evidence_ids),
                confidence=confidence,
                evidence_gap=draft.evidence_gap,
            )

        breakdown = ResearchFitBreakdown(**components)
        supporting_evidence_ids = tuple(
            dict.fromkeys(
                evidence_id
                for component_name in _COMPONENT_NAMES
                for evidence_id in getattr(
                    breakdown,
                    component_name,
                ).supporting_evidence_ids
            )
        )
        overall_score = sum(
            getattr(breakdown, component_name).score for component_name in _COMPONENT_NAMES
        )
        aggregate_confidence = derive_research_fit_confidence(breakdown, rubric)
        assessment = ResearchFitAssessment(
            supervisor_id=supervisor.supervisor_id,
            rubric=rubric,
            overall_score=overall_score,
            breakdown=breakdown,
            rationale=result.overall_rationale,
            supporting_evidence_ids=supporting_evidence_ids,
            confidence=aggregate_confidence,
            concerns=tuple(result.concerns),
        )
        validate_research_fit_evidence(supervisor, assessment)
        return assessment

    @staticmethod
    def _validate_component_citations(
        component_name: str,
        draft: StructuredResearchFitComponent,
        fit_input: ResearchFitInput,
        visible_evidence: dict[str, ResearchFitEvidenceSummary],
        domain_evidence: dict[str, EvidenceClaim],
        rubric: ResearchFitRubric,
    ) -> tuple[EvidenceClaim, ...]:
        if (
            component_name == "research_orientation_alignment"
            and draft.score > 0
            and fit_input.preferred_research_orientation is None
        ):
            raise ResearchFitModelOutputError(
                "Research-orientation points require a stated Candidate preference."
            )
        if component_name == "practical_constraint_alignment" and draft.score > 0:
            raise ResearchFitModelOutputError(
                "Practical-constraint points require typed region or study-mode evidence."
            )
        claims: list[EvidenceClaim] = []
        allowed_types = _ALLOWED_EVIDENCE_TYPES[component_name]
        for evidence_id in draft.supporting_evidence_ids:
            summary = visible_evidence.get(evidence_id)
            claim = domain_evidence.get(evidence_id)
            if summary is None or claim is None:
                raise ResearchFitModelOutputError(
                    f"{component_name} cites evidence outside the verified record."
                )
            if not claim.directly_supported or claim.claim_type is EvidenceClaimType.AVAILABILITY:
                raise ResearchFitModelOutputError(
                    f"{component_name} cites evidence that cannot support Research Fit."
                )
            if claim.claim_type not in allowed_types:
                raise ResearchFitModelOutputError(
                    f"{component_name} cites a semantically invalid evidence category."
                )
            claims.append(claim)
        if component_name == "recent_research_alignment" and draft.score > 0:
            for claim in claims:
                if claim.activity_year is None:
                    raise ResearchFitModelOutputError(
                        "Recent-research points require an explicit typed activity year."
                    )
                if (
                    claim.retrieved_at.year - claim.activity_year
                    > rubric.recent_activity_window_years
                ):
                    raise ResearchFitModelOutputError(
                        "Recent-research points cite activity outside the freshness window."
                    )
        return tuple(claims)

    @staticmethod
    def _bounded_component_confidence(
        model_confidence: EvidenceConfidence,
        cited_claims: tuple[EvidenceClaim, ...],
    ) -> EvidenceConfidence:
        if not cited_claims:
            return EvidenceConfidence.LOW
        weakest_evidence_rank = min(_CONFIDENCE_RANK[claim.confidence] for claim in cited_claims)
        bounded_rank = min(_CONFIDENCE_RANK[model_confidence], weakest_evidence_rank)
        return next(
            confidence for confidence, rank in _CONFIDENCE_RANK.items() if rank == bounded_rank
        )

    @classmethod
    def _reject_disallowed_scoring_prose(
        cls,
        result: StructuredResearchFitResult,
    ) -> None:
        prose = [result.overall_rationale, *result.concerns]
        for _, component in cls._component_items(result):
            prose.append(component.rationale)
            if component.evidence_gap is not None:
                prose.append(component.evidence_gap)
        try:
            validate_research_fit_scoring_prose(prose)
        except ValueError as error:
            raise ResearchFitModelOutputError(str(error)) from error
