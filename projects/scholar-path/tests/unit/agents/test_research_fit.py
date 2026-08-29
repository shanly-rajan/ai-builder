"""Offline tests for evidence-bound Research Fit evaluation."""

from collections.abc import Sequence

import pytest

from scholarpath.agents.research_fit import (
    ResearchFitEvaluationAgent,
    ResearchFitEvaluationError,
    ResearchFitFailureKind,
    ResearchFitInput,
    ResearchFitModelOutputError,
    StructuredResearchFitComponent,
    StructuredResearchFitResult,
)
from scholarpath.domain import (
    AvailabilityStatus,
    CandidatePreferenceRevision,
    EvidenceClaimType,
    EvidenceConfidence,
    ResearchFitRubric,
)
from tests.fakes import (
    make_strong_research_fit_response,
    make_superficial_keyword_research_fit_response,
    make_weak_research_fit_response,
)
from tests.fixtures import make_candidate_profile, make_verified_supervisor


class FakeResearchFitModel:
    """Deterministic model boundary used by all default Research Fit tests."""

    def __init__(
        self,
        outcomes: Sequence[StructuredResearchFitResult | Exception],
    ) -> None:
        self._outcomes = list(outcomes)
        self.inputs: list[ResearchFitInput] = []
        self.rubrics: list[ResearchFitRubric] = []

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        self.inputs.append(fit_input)
        self.rubrics.append(rubric)
        outcome = self._outcomes[min(len(self.inputs) - 1, len(self._outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _component(
    score: int,
    evidence_id: str | None,
    *,
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
    rationale: str = "Direct evidence supports this component of Research Fit.",
) -> StructuredResearchFitComponent:
    return StructuredResearchFitComponent(
        score=score,
        rationale=rationale,
        supporting_evidence_ids=[] if evidence_id is None else [evidence_id],
        confidence=EvidenceConfidence.LOW if evidence_id is None else confidence,
        evidence_gap=(
            "No directly supported evidence is available for this component."
            if evidence_id is None
            else None
        ),
    )


def _evidence_id(claim_type: EvidenceClaimType, *, supervisor_index: int = 1) -> str:
    supervisor = make_verified_supervisor(supervisor_index)
    return next(
        claim.evidence_id for claim in supervisor.evidence if claim.claim_type is claim_type
    )


def make_strong_fit_result(*, supervisor_index: int = 1) -> StructuredResearchFitResult:
    """Return the shared strong-fit scenario for one fixture Supervisor."""
    return make_strong_research_fit_response(
        ResearchFitInput.from_domain(
            make_candidate_profile(),
            make_verified_supervisor(supervisor_index),
        )
    )


def make_weak_fit_result() -> StructuredResearchFitResult:
    """Return the shared evidence-gap scenario."""
    return make_weak_research_fit_response()


def test_candidate_and_supervisor_map_to_a_privacy_minimized_fit_input() -> None:
    profile = make_candidate_profile(
        proposed_research_statement="Sensitive full synthetic statement that must be omitted."
    )
    supervisor = make_verified_supervisor(2)
    preferences = CandidatePreferenceRevision(
        preferred_regions=("Ghana",),
        preferred_study_modes=("online",),
        exclusions=("fully residential",),
    )
    model = FakeResearchFitModel((make_strong_fit_result(supervisor_index=2),))

    ResearchFitEvaluationAgent(model).evaluate(
        profile,
        supervisor,
        preferences=preferences,
    )

    fit_input = model.inputs[0]
    assert fit_input.research_topics == profile.research_topics
    assert fit_input.methodological_interests == profile.methodological_interests
    assert fit_input.preferred_regions == ("Ghana",)
    assert fit_input.preferred_study_modes == ("online",)
    assert fit_input.exclusions == ("fully residential",)
    assert fit_input.supervisor_id == supervisor.supervisor_id
    assert fit_input.supervisor_name == supervisor.full_name
    assert "proposed_research_statement" not in type(fit_input).model_fields
    assert "candidate_id" not in type(fit_input).model_fields
    assert all(item.claim_type is not EvidenceClaimType.AVAILABILITY for item in fit_input.evidence)
    assert all(
        item.evidence_id != _evidence_id(EvidenceClaimType.AVAILABILITY, supervisor_index=2)
        for item in fit_input.evidence
    )


def test_agent_sums_components_and_preserves_every_component_citation() -> None:
    result = make_strong_fit_result()
    supervisor = make_verified_supervisor(1)

    assessment = ResearchFitEvaluationAgent(FakeResearchFitModel((result,))).evaluate(
        make_candidate_profile(),
        supervisor,
    )

    assert assessment.overall_score == 78
    assert assessment.overall_score == sum(
        (
            assessment.breakdown.topic_alignment.score,
            assessment.breakdown.methodological_alignment.score,
            assessment.breakdown.research_orientation_alignment.score,
            assessment.breakdown.recent_research_alignment.score,
            assessment.breakdown.practical_constraint_alignment.score,
        )
    )
    for component in (
        assessment.breakdown.topic_alignment,
        assessment.breakdown.methodological_alignment,
        assessment.breakdown.research_orientation_alignment,
        assessment.breakdown.recent_research_alignment,
        assessment.breakdown.practical_constraint_alignment,
    ):
        assert component.supporting_evidence_ids or component.score == 0
    assert assessment.confidence is EvidenceConfidence.MEDIUM


def test_missing_evidence_awards_zero_and_lowers_confidence() -> None:
    assessment = ResearchFitEvaluationAgent(
        FakeResearchFitModel((make_weak_fit_result(),))
    ).evaluate(make_candidate_profile(), make_verified_supervisor(1))

    assert assessment.overall_score == 0
    assert assessment.supporting_evidence_ids == ()
    assert assessment.confidence is EvidenceConfidence.LOW
    assert all(
        component.evidence_gap is not None
        for component in (
            assessment.breakdown.topic_alignment,
            assessment.breakdown.methodological_alignment,
            assessment.breakdown.research_orientation_alignment,
            assessment.breakdown.recent_research_alignment,
            assessment.breakdown.practical_constraint_alignment,
        )
    )


def test_component_score_above_rubric_weight_is_rejected_after_one_retry() -> None:
    invalid = make_strong_fit_result().model_copy(
        update={
            "topic_alignment": _component(
                41,
                _evidence_id(EvidenceClaimType.RESEARCH_INTEREST),
            )
        }
    )
    model = FakeResearchFitModel((invalid, invalid))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            make_verified_supervisor(1),
        )

    error = captured.value
    assert error.kind is ResearchFitFailureKind.INVALID_OUTPUT
    assert error.attempts == 2
    assert len(model.inputs) == 2


def test_unknown_evidence_is_retried_once_then_valid_output_is_used() -> None:
    invalid = make_strong_fit_result().model_copy(
        update={"topic_alignment": _component(20, "invented-evidence-id")}
    )
    valid = make_strong_fit_result()
    model = FakeResearchFitModel((invalid, valid))

    assessment = ResearchFitEvaluationAgent(model).evaluate(
        make_candidate_profile(),
        make_verified_supervisor(1),
    )

    assert assessment.overall_score == 78
    assert len(model.inputs) == 2
    assert model.inputs[0] == model.inputs[1]


def test_superficial_identity_keyword_cannot_support_topic_points() -> None:
    fit_input = ResearchFitInput.from_domain(
        make_candidate_profile(),
        make_verified_supervisor(1),
    )
    superficial = make_superficial_keyword_research_fit_response(fit_input)
    model = FakeResearchFitModel((superficial, superficial))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            make_verified_supervisor(1),
        )

    assert captured.value.kind is ResearchFitFailureKind.INVALID_OUTPUT


def test_unstated_region_or_study_mode_cannot_earn_practical_points() -> None:
    unstated = make_strong_fit_result().model_copy(
        update={
            "practical_constraint_alignment": _component(
                8,
                _evidence_id(EvidenceClaimType.CURRENT_AFFILIATION),
                rationale="The institution is assumed to satisfy the preferred region.",
            )
        }
    )
    model = FakeResearchFitModel((unstated, unstated))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            make_verified_supervisor(1),
        )

    assert captured.value.kind is ResearchFitFailureKind.INVALID_OUTPUT


@pytest.mark.parametrize(
    "rationale",
    (
        "The admission probability is high.",
        "The Candidate has a strong chance of being admitted.",
        "The Candidate is likely to be accepted.",
        "There is an 80% chance the Candidate will be admitted.",
    ),
)
def test_admission_likelihood_prose_is_rejected(rationale: str) -> None:
    prohibited = make_strong_fit_result().model_copy(update={"overall_rationale": rationale})
    model = FakeResearchFitModel((prohibited, prohibited))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            make_verified_supervisor(1),
        )

    assert captured.value.kind is ResearchFitFailureKind.INVALID_OUTPUT


def test_availability_prose_cannot_be_hidden_in_a_component_score() -> None:
    prohibited = make_strong_fit_result().model_copy(
        update={
            "practical_constraint_alignment": _component(
                8,
                _evidence_id(EvidenceClaimType.CURRENT_AFFILIATION),
                rationale="The Supervisor is accepting doctoral enquiries.",
            )
        }
    )
    model = FakeResearchFitModel((prohibited, prohibited))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            make_verified_supervisor(1),
        )

    assert captured.value.kind is ResearchFitFailureKind.INVALID_OUTPUT


@pytest.mark.parametrize(
    "prohibited_rationale",
    [
        "The Supervisor welcomes PhD applications.",
        "PhD applications are open this year.",
        "The profile has confirmed_accepting status.",
    ],
)
def test_semantic_availability_phrases_are_rejected(
    prohibited_rationale: str,
) -> None:
    prohibited = make_strong_fit_result().model_copy(
        update={"overall_rationale": prohibited_rationale}
    )
    model = FakeResearchFitModel((prohibited, prohibited))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            make_verified_supervisor(1),
        )

    assert captured.value.kind is ResearchFitFailureKind.INVALID_OUTPUT


def test_bare_doctoral_candidate_research_prose_is_not_misclassified_as_availability() -> None:
    allowed = make_strong_fit_result().model_copy(
        update={
            "overall_rationale": (
                "The cited work studies doctoral Candidate decision support as a research topic."
            )
        }
    )

    assessment = ResearchFitEvaluationAgent(FakeResearchFitModel((allowed,))).evaluate(
        make_candidate_profile(),
        make_verified_supervisor(1),
    )

    assert assessment.overall_score == 78


def test_positive_orientation_is_rejected_when_candidate_orientation_is_unset() -> None:
    result = make_strong_fit_result()
    model = FakeResearchFitModel((result, result))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(preferred_research_orientation=None),
            make_verified_supervisor(1),
        )

    assert captured.value.kind is ResearchFitFailureKind.INVALID_OUTPUT


def test_recent_research_points_require_a_typed_activity_year() -> None:
    supervisor = make_verified_supervisor(1)
    evidence = tuple(
        claim.model_copy(update={"activity_year": None})
        if claim.claim_type is EvidenceClaimType.PUBLICATION
        else claim
        for claim in supervisor.evidence
    )
    supervisor_without_year = supervisor.model_copy(update={"evidence": evidence})
    result = make_strong_fit_result()
    model = FakeResearchFitModel((result, result))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            supervisor_without_year,
        )

    assert captured.value.kind is ResearchFitFailureKind.INVALID_OUTPUT


def test_availability_is_excluded_from_scoring_and_remains_unchanged() -> None:
    supervisor = make_verified_supervisor(2)
    assert supervisor.availability_status is AvailabilityStatus.CONFIRMED_ACCEPTING

    model = FakeResearchFitModel((make_strong_fit_result(supervisor_index=2),))
    assessment = ResearchFitEvaluationAgent(model).evaluate(make_candidate_profile(), supervisor)

    assert supervisor.availability_status is AvailabilityStatus.CONFIRMED_ACCEPTING
    assert all(
        evidence.claim_type is not EvidenceClaimType.AVAILABILITY
        for evidence in model.inputs[0].evidence
    )
    assert "accept" not in assessment.rationale.casefold()


def test_model_output_error_is_typed_and_retried_once() -> None:
    model = FakeResearchFitModel(
        (
            ResearchFitModelOutputError("synthetic malformed output"),
            make_strong_fit_result(),
        )
    )

    assessment = ResearchFitEvaluationAgent(model).evaluate(
        make_candidate_profile(),
        make_verified_supervisor(1),
    )

    assert assessment.overall_score == 78
    assert len(model.inputs) == 2


def test_unexpected_model_failure_is_sanitized_without_retry() -> None:
    sensitive_message = "provider failure containing private Candidate content"
    model = FakeResearchFitModel((RuntimeError(sensitive_message),))

    with pytest.raises(ResearchFitEvaluationError) as captured:
        ResearchFitEvaluationAgent(model).evaluate(
            make_candidate_profile(),
            make_verified_supervisor(1),
        )

    assert captured.value.kind is ResearchFitFailureKind.MODEL_INVOCATION
    assert captured.value.attempts == 1
    assert sensitive_message not in str(captured.value)
    assert len(model.inputs) == 1
