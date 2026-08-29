"""Focused M7 tests for evidence-cited Research Fit and proposal contracts."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    AvailabilityStatus,
    CandidateReviewAction,
    CandidateReviewDecision,
    EvidenceClaimType,
    EvidenceConfidence,
    ProposedSupervisorRecommendation,
    ProposedSupervisorShortlist,
    ResearchFitAssessment,
    ResearchFitBreakdown,
    ResearchFitComponentAssessment,
    ResearchFitEvidenceError,
    ResearchFitRubric,
    apply_candidate_review,
    validate_research_fit_evidence,
)
from tests.fixtures import make_verified_supervisor


def _claim_id(supervisor_index: int, claim_type: EvidenceClaimType) -> str:
    supervisor = make_verified_supervisor(supervisor_index)
    return next(
        claim.evidence_id for claim in supervisor.evidence if claim.claim_type is claim_type
    )


def _component(
    score: int,
    evidence_ids: tuple[str, ...],
    *,
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
) -> ResearchFitComponentAssessment:
    if not evidence_ids:
        return ResearchFitComponentAssessment(
            score=0,
            rationale="No directly supported evidence is available for this component.",
            supporting_evidence_ids=(),
            confidence=EvidenceConfidence.LOW,
            evidence_gap="The component has no suitable typed evidence.",
        )
    return ResearchFitComponentAssessment(
        score=score,
        rationale="The cited evidence supports this bounded component score.",
        supporting_evidence_ids=evidence_ids,
        confidence=confidence,
    )


def _assessment(supervisor_index: int = 1) -> ResearchFitAssessment:
    research_id = _claim_id(supervisor_index, EvidenceClaimType.RESEARCH_INTEREST)
    methodology_id = _claim_id(supervisor_index, EvidenceClaimType.METHODOLOGY)
    publication_id = _claim_id(supervisor_index, EvidenceClaimType.PUBLICATION)
    breakdown = ResearchFitBreakdown(
        topic_alignment=_component(
            32,
            (research_id, publication_id),
            confidence=EvidenceConfidence.MEDIUM,
        ),
        methodological_alignment=_component(
            16,
            (methodology_id,),
            confidence=EvidenceConfidence.MEDIUM,
        ),
        research_orientation_alignment=_component(
            12,
            (research_id, methodology_id),
            confidence=EvidenceConfidence.MEDIUM,
        ),
        recent_research_alignment=_component(12, (publication_id,)),
        practical_constraint_alignment=_component(0, ()),
    )
    return ResearchFitAssessment(
        supervisor_id=f"supervisor-{supervisor_index:03d}",
        overall_score=72,
        breakdown=breakdown,
        rationale="The evidence indicates a strong, but not perfect, Research Fit.",
        supporting_evidence_ids=(
            research_id,
            publication_id,
            methodology_id,
        ),
        confidence=EvidenceConfidence.MEDIUM,
        concerns=("Study mode is not directly stated in the cited affiliation evidence.",),
    )


def _recommendation(supervisor_index: int = 1, rank: int = 1) -> ProposedSupervisorRecommendation:
    supervisor = make_verified_supervisor(supervisor_index)
    assessment = _assessment(supervisor_index)
    return ProposedSupervisorRecommendation(
        rank=rank,
        supervisor=supervisor,
        assessment=assessment,
        strengths=("Strong evidence-backed topic and methodological alignment.",),
        concerns=assessment.concerns,
        availability_status=supervisor.availability_status,
        evidence_confidence=assessment.confidence,
    )


def test_default_research_fit_rubric_has_the_contractual_weights() -> None:
    rubric = ResearchFitRubric()

    assert rubric.version == "research-fit-rubric-v1"
    assert rubric.weights == {
        "topic_alignment": 40,
        "methodological_alignment": 20,
        "research_orientation_alignment": 15,
        "recent_research_alignment": 15,
        "practical_constraint_alignment": 10,
    }


def test_configurable_rubric_must_still_total_one_hundred() -> None:
    with pytest.raises(ValidationError, match="sum to exactly 100"):
        ResearchFitRubric(topic_alignment=39)


@pytest.mark.parametrize("score", [-1, 101])
def test_component_score_is_constrained_to_zero_through_one_hundred(score: int) -> None:
    with pytest.raises(ValidationError, match="score"):
        _component(score, ("evidence-001-research",))


def test_positive_component_score_requires_evidence_citations() -> None:
    with pytest.raises(ValidationError, match="positive component score requires"):
        ResearchFitComponentAssessment(
            score=1,
            rationale="A positive score without evidence is invalid.",
            supporting_evidence_ids=(),
            confidence=EvidenceConfidence.LOW,
            evidence_gap="No supporting evidence exists.",
        )


def test_component_without_evidence_is_zero_low_confidence_and_explains_gap() -> None:
    component = ResearchFitComponentAssessment(
        score=0,
        rationale="No direct methodological evidence was retrieved.",
        supporting_evidence_ids=(),
        confidence=EvidenceConfidence.LOW,
        evidence_gap="No directly supported methodology claim is available.",
    )

    assert component.score == 0
    assert component.evidence_gap is not None


@pytest.mark.parametrize(
    ("confidence", "evidence_gap"),
    [
        (EvidenceConfidence.MEDIUM, "Evidence is missing."),
        (EvidenceConfidence.LOW, None),
    ],
)
def test_missing_evidence_contract_rejects_hidden_confidence(
    confidence: EvidenceConfidence,
    evidence_gap: str | None,
) -> None:
    with pytest.raises(ValidationError):
        ResearchFitComponentAssessment(
            score=0,
            rationale="No direct evidence was retrieved.",
            confidence=confidence,
            evidence_gap=evidence_gap,
        )


def test_assessment_score_must_equal_the_deterministic_component_sum() -> None:
    assessment = _assessment()

    with pytest.raises(ValidationError, match="deterministic component sum"):
        assessment.model_copy(update={"overall_score": 73})


def test_component_score_cannot_exceed_its_configured_weight() -> None:
    assessment = _assessment()
    too_high = assessment.breakdown.model_copy(
        update={
            "practical_constraint_alignment": _component(
                11,
                (_claim_id(1, EvidenceClaimType.CURRENT_AFFILIATION),),
            )
        }
    )

    with pytest.raises(ValidationError, match="practical_constraint_alignment score exceeds"):
        assessment.model_copy(update={"overall_score": 83, "breakdown": too_high})


def test_assessment_evidence_is_exactly_the_union_of_component_citations() -> None:
    assessment = _assessment()

    with pytest.raises(ValidationError, match="exactly match component citations"):
        assessment.model_copy(
            update={"supporting_evidence_ids": (*assessment.supporting_evidence_ids, "extra")}
        )


@pytest.mark.parametrize(
    "prohibited_rationale",
    [
        "Acceptance is likely.",
        "The Supervisor welcomes PhD applications.",
    ],
)
def test_rehydrated_assessment_rejects_admission_and_availability_scoring_prose(
    prohibited_rationale: str,
) -> None:
    with pytest.raises(ValidationError):
        _assessment().model_copy(update={"rationale": prohibited_rationale})


def test_assessment_confidence_must_match_deterministic_component_aggregate() -> None:
    with pytest.raises(ValidationError, match="deterministic component aggregate"):
        _assessment().model_copy(update={"confidence": EvidenceConfidence.HIGH})


def test_every_scored_component_accepts_owned_suitable_grounded_evidence() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = _assessment()

    validate_research_fit_evidence(supervisor, assessment)


def test_cross_contract_rejects_component_confidence_above_weakest_claim() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = _assessment()
    inflated_topic = assessment.breakdown.topic_alignment.model_copy(
        update={"confidence": EvidenceConfidence.HIGH}
    )
    breakdown = assessment.breakdown.model_copy(update={"topic_alignment": inflated_topic})
    inflated = assessment.model_copy(update={"breakdown": breakdown})

    with pytest.raises(ResearchFitEvidenceError, match="weakest cited evidence"):
        validate_research_fit_evidence(supervisor, inflated)


def test_cross_contract_rejects_practical_points_from_affiliation_prose() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = _assessment()
    affiliation_id = _claim_id(1, EvidenceClaimType.CURRENT_AFFILIATION)
    practical = _component(8, (affiliation_id,))
    breakdown = assessment.breakdown.model_copy(
        update={"practical_constraint_alignment": practical}
    )
    cited_ids = (*assessment.supporting_evidence_ids, affiliation_id)
    unsupported = assessment.model_copy(
        update={
            "overall_score": 80,
            "breakdown": breakdown,
            "supporting_evidence_ids": cited_ids,
        }
    )

    with pytest.raises(ResearchFitEvidenceError, match="typed region or study-mode"):
        validate_research_fit_evidence(supervisor, unsupported)


def test_recent_points_require_fresh_typed_activity_year() -> None:
    supervisor = make_verified_supervisor(1)
    publication = next(
        claim for claim in supervisor.evidence if claim.claim_type is EvidenceClaimType.PUBLICATION
    )
    assert publication.supporting_excerpt is not None
    stale_publication = publication.model_copy(
        update={
            "activity_year": 2010,
            "supporting_excerpt": publication.supporting_excerpt.replace("2025", "2010"),
        }
    )
    stale_supervisor = supervisor.model_copy(
        update={
            "evidence": tuple(
                stale_publication if claim.evidence_id == publication.evidence_id else claim
                for claim in supervisor.evidence
            )
        }
    )

    with pytest.raises(ResearchFitEvidenceError, match="freshness window"):
        validate_research_fit_evidence(stale_supervisor, _assessment())


def test_activity_year_must_be_typed_grounded_and_not_future_dated() -> None:
    supervisor = make_verified_supervisor(1)
    publication = next(
        claim for claim in supervisor.evidence if claim.claim_type is EvidenceClaimType.PUBLICATION
    )
    research = next(
        claim
        for claim in supervisor.evidence
        if claim.claim_type is EvidenceClaimType.RESEARCH_INTEREST
    )
    assert publication.supporting_excerpt is not None
    assert research.supporting_excerpt is not None

    with pytest.raises(ValidationError, match="explicit in the supporting excerpt"):
        publication.model_copy(update={"activity_year": 2024})
    with pytest.raises(ValidationError, match="later than retrieval year"):
        publication.model_copy(
            update={
                "activity_year": 2027,
                "supporting_excerpt": publication.supporting_excerpt.replace("2025", "2027"),
            }
        )
    with pytest.raises(ValidationError, match="Only publication or project"):
        research.model_copy(
            update={
                "activity_year": 2025,
                "supporting_excerpt": f"{research.supporting_excerpt} 2025",
            }
        )


def test_scoring_rejects_a_claim_type_unsuitable_for_the_component() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = _assessment()
    identity_id = _claim_id(1, EvidenceClaimType.IDENTITY)
    topic = _component(32, (identity_id,))
    breakdown = assessment.breakdown.model_copy(update={"topic_alignment": topic})
    cited_ids = tuple(
        dict.fromkeys(
            evidence_id
            for component in (
                breakdown.topic_alignment,
                breakdown.methodological_alignment,
                breakdown.research_orientation_alignment,
                breakdown.recent_research_alignment,
                breakdown.practical_constraint_alignment,
            )
            for evidence_id in component.supporting_evidence_ids
        )
    )
    unsupported = assessment.model_copy(
        update={"breakdown": breakdown, "supporting_evidence_ids": cited_ids}
    )

    with pytest.raises(ResearchFitEvidenceError, match="unsuitable evidence claim type"):
        validate_research_fit_evidence(supervisor, unsupported)


def test_availability_evidence_cannot_contribute_to_research_fit() -> None:
    supervisor = make_verified_supervisor(2)
    assessment = _assessment(2)
    availability_id = _claim_id(2, EvidenceClaimType.AVAILABILITY)
    topic = _component(32, (availability_id,))
    breakdown = assessment.breakdown.model_copy(update={"topic_alignment": topic})
    cited_ids = tuple(
        dict.fromkeys(
            evidence_id
            for component in (
                breakdown.topic_alignment,
                breakdown.methodological_alignment,
                breakdown.research_orientation_alignment,
                breakdown.recent_research_alignment,
                breakdown.practical_constraint_alignment,
            )
            for evidence_id in component.supporting_evidence_ids
        )
    )
    invalid = assessment.model_copy(
        update={"breakdown": breakdown, "supporting_evidence_ids": cited_ids}
    )

    with pytest.raises(ResearchFitEvidenceError, match="availability evidence must not"):
        validate_research_fit_evidence(supervisor, invalid)


def test_indirect_or_ungrounded_claim_cannot_contribute_to_research_fit() -> None:
    supervisor = make_verified_supervisor(6)
    assessment = _assessment(6)
    indirect_id = next(
        claim.evidence_id for claim in supervisor.evidence if not claim.directly_supported
    )
    topic = _component(32, (indirect_id,))
    breakdown = assessment.breakdown.model_copy(update={"topic_alignment": topic})
    cited_ids = tuple(
        dict.fromkeys(
            evidence_id
            for component in (
                breakdown.topic_alignment,
                breakdown.methodological_alignment,
                breakdown.research_orientation_alignment,
                breakdown.recent_research_alignment,
                breakdown.practical_constraint_alignment,
            )
            for evidence_id in component.supporting_evidence_ids
        )
    )
    invalid = assessment.model_copy(
        update={"breakdown": breakdown, "supporting_evidence_ids": cited_ids}
    )

    with pytest.raises(ResearchFitEvidenceError, match="directly supported, grounded"):
        validate_research_fit_evidence(supervisor, invalid)


def test_proposal_preserves_not_stated_availability_and_verified_status() -> None:
    recommendation = _recommendation()

    assert recommendation.availability_status is AvailabilityStatus.NOT_STATED
    assert recommendation.supervisor.status.value == "verified"


def test_proposal_rejects_a_supervisor_already_moved_to_shortlisted_status() -> None:
    recommendation = _recommendation()
    decision = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=(recommendation.supervisor.supervisor_id,),
        reason="The Candidate approved this evidence-backed recommendation.",
    )
    approved_supervisor = apply_candidate_review(recommendation.supervisor, decision)

    with pytest.raises(ValidationError, match="must contain a Verified Supervisor"):
        ProposedSupervisorRecommendation(
            rank=1,
            supervisor=approved_supervisor,
            assessment=recommendation.assessment,
            strengths=recommendation.strengths,
            availability_status=approved_supervisor.availability_status,
            evidence_confidence=recommendation.evidence_confidence,
        )


def test_proposed_shortlist_requires_unique_contiguous_ranks_and_at_most_five() -> None:
    generated_at = datetime(2026, 8, 29, 12, tzinfo=UTC)
    recommendations = tuple(_recommendation(index, index) for index in range(1, 6))
    proposed = ProposedSupervisorShortlist(
        candidate_id="candidate-001",
        recommendations=recommendations,
        generated_at=generated_at,
        summary="Five evidence-backed recommendations await Candidate review.",
    )

    assert len(proposed.recommendations) == 5
    assert ProposedSupervisorShortlist.model_validate_json(proposed.model_dump_json()) == proposed

    with pytest.raises(ValidationError, match="at most 5 items"):
        ProposedSupervisorShortlist(
            candidate_id="candidate-001",
            recommendations=(*recommendations, _recommendation(6, 6)),
            generated_at=generated_at,
            summary="Too many recommendations.",
        )

    with pytest.raises(ValidationError, match="contiguous and ordered"):
        ProposedSupervisorShortlist(
            candidate_id="candidate-001",
            recommendations=(_recommendation(1, 2),),
            generated_at=generated_at,
            summary="A non-contiguous rank.",
        )
