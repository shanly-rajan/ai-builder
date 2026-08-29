"""Unit tests for deterministic preliminary Supervisor shortlist synthesis."""

from datetime import UTC, datetime
from typing import cast

import pytest

from scholarpath.agents.shortlist_synthesis import ShortlistSynthesisAgent
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    EvidenceConfidence,
    ProposedSupervisorShortlist,
    ResearchFitAssessment,
    ResearchFitBreakdown,
    ResearchFitComponentAssessment,
    ResearchFitRubric,
    SupervisorLifecycleStatus,
    VerifiedSupervisor,
    derive_research_fit_confidence,
)
from tests.fixtures import make_prospective_supervisor, make_verified_supervisor

GENERATED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
_CONFIDENCE_RANK = {
    EvidenceConfidence.LOW: 1,
    EvidenceConfidence.MEDIUM: 2,
    EvidenceConfidence.HIGH: 3,
}


def _bounded_confidence(
    requested: EvidenceConfidence,
    evidence: EvidenceConfidence,
) -> EvidenceConfidence:
    bounded_rank = min(_CONFIDENCE_RANK[requested], _CONFIDENCE_RANK[evidence])
    return next(value for value, rank in _CONFIDENCE_RANK.items() if rank == bounded_rank)


def _evidence_id(
    supervisor: VerifiedSupervisor,
    claim_type: EvidenceClaimType,
) -> str:
    return next(
        claim.evidence_id for claim in supervisor.evidence if claim.claim_type is claim_type
    )


def _component(
    score: int,
    rationale: str,
    evidence_id: str,
    dimension: str,
    confidence: EvidenceConfidence,
) -> ResearchFitComponentAssessment:
    if score == 0:
        return ResearchFitComponentAssessment(
            score=0,
            rationale=rationale,
            confidence=EvidenceConfidence.LOW,
            evidence_gap=f"No direct evidence supports {dimension}.",
        )
    return ResearchFitComponentAssessment(
        score=score,
        rationale=rationale,
        supporting_evidence_ids=(evidence_id,),
        confidence=confidence,
    )


def _assessment(
    supervisor: VerifiedSupervisor,
    *,
    scores: tuple[int, int, int, int, int] = (30, 15, 10, 10, 0),
    confidence: EvidenceConfidence = EvidenceConfidence.HIGH,
    concerns: tuple[str, ...] = (),
) -> ResearchFitAssessment:
    research_id = _evidence_id(supervisor, EvidenceClaimType.RESEARCH_INTEREST)
    methodology_id = _evidence_id(supervisor, EvidenceClaimType.METHODOLOGY)
    publication_id = _evidence_id(supervisor, EvidenceClaimType.PUBLICATION)
    affiliation_id = _evidence_id(supervisor, EvidenceClaimType.CURRENT_AFFILIATION)
    confidence_by_id = {claim.evidence_id: claim.confidence for claim in supervisor.evidence}
    breakdown = ResearchFitBreakdown(
        topic_alignment=_component(
            scores[0],
            f"Topic evidence supports {supervisor.full_name}.",
            research_id,
            "topic alignment",
            _bounded_confidence(confidence, confidence_by_id[research_id]),
        ),
        methodological_alignment=_component(
            scores[1],
            f"Method evidence supports {supervisor.full_name}.",
            methodology_id,
            "methodological alignment",
            _bounded_confidence(confidence, confidence_by_id[methodology_id]),
        ),
        research_orientation_alignment=_component(
            scores[2],
            f"Orientation evidence supports {supervisor.full_name}.",
            research_id,
            "research orientation alignment",
            _bounded_confidence(confidence, confidence_by_id[research_id]),
        ),
        recent_research_alignment=_component(
            scores[3],
            f"Recent research evidence supports {supervisor.full_name}.",
            publication_id,
            "recent research alignment",
            _bounded_confidence(confidence, confidence_by_id[publication_id]),
        ),
        practical_constraint_alignment=_component(
            scores[4],
            f"Affiliation evidence supports {supervisor.full_name}.",
            affiliation_id,
            "practical constraint alignment",
            _bounded_confidence(confidence, confidence_by_id[affiliation_id]),
        ),
    )
    evidence_ids = tuple(
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
    return ResearchFitAssessment(
        supervisor_id=supervisor.supervisor_id,
        rubric=ResearchFitRubric(),
        overall_score=sum(scores),
        breakdown=breakdown,
        rationale=f"Evidence-backed Research Fit assessment for {supervisor.full_name}.",
        supporting_evidence_ids=evidence_ids,
        confidence=derive_research_fit_confidence(breakdown, ResearchFitRubric()),
        concerns=concerns,
    )


def _synthesize(
    supervisors: tuple[VerifiedSupervisor, ...],
    assessments: tuple[ResearchFitAssessment, ...],
    *,
    max_results: int = 5,
) -> ProposedSupervisorShortlist:
    return ShortlistSynthesisAgent(max_results=max_results).synthesize(
        "candidate-001",
        supervisors,
        assessments,
        GENERATED_AT,
    )


def test_deterministic_ties_use_confidence_then_normalized_name() -> None:
    amara = make_verified_supervisor(1)
    elias = make_verified_supervisor(2)
    sofia = make_verified_supervisor(4)
    scores = (25, 15, 10, 10, 0)

    proposal = _synthesize(
        (sofia, amara, elias),
        (
            _assessment(sofia, scores=scores, confidence=EvidenceConfidence.LOW),
            _assessment(amara, scores=scores, confidence=EvidenceConfidence.LOW),
            _assessment(elias, scores=scores, confidence=EvidenceConfidence.MEDIUM),
        ),
    )

    assert [item.supervisor.full_name for item in proposal.recommendations] == [
        "Professor Elias Hart",
        "Dr Amara Ndlovu",
        "Professor Sofia Mensah",
    ]
    assert [item.rank for item in proposal.recommendations] == [1, 2, 3]


def test_overall_score_is_the_primary_ordering_rule() -> None:
    amara = make_verified_supervisor(1)
    sofia = make_verified_supervisor(4)

    proposal = _synthesize(
        (amara, sofia),
        (
            _assessment(
                amara,
                scores=(5, 0, 0, 0, 0),
                confidence=EvidenceConfidence.HIGH,
            ),
            _assessment(
                sofia,
                scores=(30, 15, 10, 10, 0),
                confidence=EvidenceConfidence.LOW,
            ),
        ),
    )

    assert [item.supervisor.full_name for item in proposal.recommendations] == [
        "Professor Sofia Mensah",
        "Dr Amara Ndlovu",
    ]


def test_only_strictly_verified_supervisors_are_ranked() -> None:
    prospective = cast(VerifiedSupervisor, make_prospective_supervisor(1))
    verified = make_verified_supervisor(2)

    proposal = _synthesize(
        (prospective, verified),
        (_assessment(verified),),
    )

    assert [item.supervisor.supervisor_id for item in proposal.recommendations] == [
        verified.supervisor_id
    ]
    assert proposal.recommendations[0].supervisor.status is SupervisorLifecycleStatus.VERIFIED


def test_proposal_contains_at_most_five_results() -> None:
    supervisors = tuple(make_verified_supervisor(index) for index in range(1, 7))
    assessments = tuple(_assessment(supervisor) for supervisor in supervisors)

    proposal = _synthesize(supervisors, assessments)

    assert len(proposal.recommendations) == 5
    assert [item.rank for item in proposal.recommendations] == [1, 2, 3, 4, 5]


@pytest.mark.parametrize("max_results", [0, 6, True, 1.5])
def test_max_results_is_strictly_bounded(max_results: object) -> None:
    with pytest.raises(ValueError, match="integer between 1 and 5"):
        ShortlistSynthesisAgent(max_results=max_results)  # type: ignore[arg-type]


def test_availability_not_stated_is_reported_separately_and_unchanged() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = _assessment(supervisor)

    recommendation = _synthesize((supervisor,), (assessment,)).recommendations[0]

    assert recommendation.availability_status is AvailabilityStatus.NOT_STATED
    assert recommendation.supervisor.availability_status is AvailabilityStatus.NOT_STATED
    cited_claim_types = {
        claim.claim_type
        for claim in supervisor.evidence
        if claim.evidence_id in assessment.supporting_evidence_ids
    }
    assert EvidenceClaimType.AVAILABILITY not in cited_claim_types


def test_explanations_prioritize_weighted_strengths_and_combine_concerns() -> None:
    supervisor = make_verified_supervisor(3)
    assessment = _assessment(
        supervisor,
        scores=(38, 10, 8, 7, 0),
        concerns=("The topic evidence covers only one recent project.",),
    )

    recommendation = _synthesize((supervisor,), (assessment,)).recommendations[0]

    assert recommendation.strengths[0] == (f"Topic evidence supports {supervisor.full_name}.")
    assert recommendation.concerns == (
        "The topic evidence covers only one recent project.",
        "No direct evidence supports practical constraint alignment.",
        "The source states that the Supervisor is not currently accepting enquiries.",
    )
    assert recommendation.availability_status is AvailabilityStatus.CONFIRMED_NOT_ACCEPTING
    assert recommendation.assessment.breakdown.practical_constraint_alignment.score == 0


def test_synthesis_does_not_change_lifecycle_or_create_admission_claims() -> None:
    supervisors = (make_verified_supervisor(1), make_verified_supervisor(2))
    proposal = _synthesize(
        supervisors,
        tuple(_assessment(supervisor) for supervisor in supervisors),
    )

    assert all(
        item.supervisor.status is SupervisorLifecycleStatus.VERIFIED
        for item in proposal.recommendations
    )
    rendered = proposal.model_dump_json().casefold()
    assert "admission probability" not in rendered
    assert "admission likelihood" not in rendered
    assert "candidate approval is required" in proposal.summary.casefold()


def test_a_matching_assessment_is_required() -> None:
    with pytest.raises(ValueError, match="matching Research Fit assessment"):
        _synthesize((make_verified_supervisor(1),), ())
