"""Focused tests for independent review and deterministic reconciliation."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast

import pytest
from pydantic import ValidationError

from scholarpath.agents.independent_review import (
    IndependentReviewAgent,
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewPolicy,
    IndependentReviewResult,
    eligible_overlooked_evidence_ids,
    reconcile_research_fit_assessment,
)
from scholarpath.agents.shortlist_synthesis import ShortlistSynthesisAgent
from scholarpath.domain import (
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewDecision,
    IndependentReviewFailureKind,
    IndependentReviewStatus,
    ProposedSupervisorRecommendation,
    ReconciledResearchFitAssessment,
)
from tests.fixtures import (
    make_candidate_profile,
    make_research_fit_assessment,
    make_verified_supervisor,
)


class FakeIndependentReviewModel:
    """Deterministic reviewer fake that never reaches a provider or network."""

    def __init__(self, outcome: IndependentReviewResult | Exception | object) -> None:
        self.outcome = outcome
        self.inputs: list[IndependentReviewInput] = []

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        self.inputs.append(review_input)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return cast(IndependentReviewResult, self.outcome)


def _accepted_result(score: int = 87) -> IndependentReviewResult:
    return IndependentReviewResult(
        decision=IndependentReviewDecision.ACCEPT,
        recommended_score=score,
        unsupported_claim_ids=[],
        overlooked_evidence_ids=[],
        confidence=EvidenceConfidence.HIGH,
        critique="The evidence citations and component scores are proportionate.",
    )


def _revised_result(
    score: int = 75,
    *,
    unsupported_claim_ids: list[str] | None = None,
    overlooked_evidence_ids: list[str] | None = None,
    confidence: EvidenceConfidence = EvidenceConfidence.MEDIUM,
) -> IndependentReviewResult:
    return IndependentReviewResult(
        decision=IndependentReviewDecision.REVISE,
        recommended_score=score,
        unsupported_claim_ids=unsupported_claim_ids or [],
        overlooked_evidence_ids=overlooked_evidence_ids or [],
        confidence=confidence,
        critique="The revised score better reflects the closed evidence record.",
    )


def test_accepted_assessment_preserves_the_complete_original() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)

    reconciled = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _accepted_result(),
    )

    assert reconciled.review_status is IndependentReviewStatus.ACCEPTED
    assert reconciled.initial_assessment == assessment
    assert reconciled.effective_score == assessment.overall_score
    assert reconciled.effective_rationale == assessment.rationale
    assert reconciled.effective_supporting_evidence_ids == assessment.supporting_evidence_ids
    assert reconciled.effective_confidence is assessment.confidence
    assert not reconciled.requires_candidate_attention


def test_valid_revision_uses_reviewed_score_and_explanation() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    result = _revised_result(score=80)

    reconciled = reconcile_research_fit_assessment(supervisor, assessment, result)

    assert reconciled.review_status is IndependentReviewStatus.REVISED
    assert reconciled.initial_assessment == assessment
    assert reconciled.effective_score == 80
    assert reconciled.effective_rationale == result.critique
    assert reconciled.effective_confidence is EvidenceConfidence.MEDIUM


def test_nonexistent_reviewer_evidence_makes_review_unavailable() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    result = _revised_result(overlooked_evidence_ids=["invented-evidence-id"])

    reconciled = reconcile_research_fit_assessment(supervisor, assessment, result)

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.INVALID_EVIDENCE_REFERENCE
    assert reconciled.effective_score == assessment.overall_score
    assert reconciled.effective_confidence is EvidenceConfidence.LOW
    assert reconciled.requires_candidate_attention


def test_valid_overlooked_evidence_is_added_without_model_created_evidence() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    publication = next(
        claim for claim in supervisor.evidence if claim.claim_type is EvidenceClaimType.PUBLICATION
    )
    overlooked = publication.model_copy(
        update={
            "evidence_id": "evidence-001-project",
            "claim_type": EvidenceClaimType.PROJECT,
            "claim": f"{supervisor.full_name} leads a responsible architecture project.",
            "confidence": EvidenceConfidence.LOW,
            "supporting_excerpt": (
                f"{supervisor.full_name} leads a responsible architecture project "
                f"in {publication.activity_year}."
            ),
        }
    )
    supervisor_with_project = supervisor.model_copy(
        update={"evidence": (*supervisor.evidence, overlooked)}
    )
    assert eligible_overlooked_evidence_ids(
        supervisor_with_project,
        assessment,
    ) == (overlooked.evidence_id,)

    reconciled = reconcile_research_fit_assessment(
        supervisor_with_project,
        assessment,
        _revised_result(overlooked_evidence_ids=[overlooked.evidence_id]),
    )

    assert reconciled.review_status is IndependentReviewStatus.REVISED
    assert reconciled.overlooked_evidence_ids == (overlooked.evidence_id,)
    assert reconciled.effective_supporting_evidence_ids[-1] == overlooked.evidence_id
    assert reconciled.effective_confidence is EvidenceConfidence.LOW


@pytest.mark.parametrize(
    "claim_type",
    (EvidenceClaimType.IDENTITY, EvidenceClaimType.CURRENT_AFFILIATION),
)
def test_non_fit_evidence_cannot_be_added_as_overlooked_support(
    claim_type: EvidenceClaimType,
) -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    unsuitable_id = next(
        claim.evidence_id for claim in supervisor.evidence if claim.claim_type is claim_type
    )

    reconciled = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _revised_result(overlooked_evidence_ids=[unsuitable_id]),
    )

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.INVALID_EVIDENCE_REFERENCE


def test_unsupported_claims_are_removed_from_effective_evidence() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    unsupported_id = assessment.supporting_evidence_ids[0]

    reconciled = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _revised_result(unsupported_claim_ids=[unsupported_id]),
    )

    assert reconciled.review_status is IndependentReviewStatus.REVISED
    assert unsupported_id in reconciled.initial_assessment.supporting_evidence_ids
    assert unsupported_id not in reconciled.effective_supporting_evidence_ids
    assert reconciled.unsupported_claim_ids == (unsupported_id,)


def test_removing_all_support_for_a_zero_score_forces_low_confidence() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)

    reconciled = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _revised_result(
            score=0,
            unsupported_claim_ids=list(assessment.supporting_evidence_ids),
            confidence=EvidenceConfidence.HIGH,
        ),
        policy=IndependentReviewPolicy(disagreement_threshold=100),
    )

    assert reconciled.review_status is IndependentReviewStatus.REVISED
    assert reconciled.effective_supporting_evidence_ids == ()
    assert reconciled.effective_confidence is EvidenceConfidence.LOW
    assert not reconciled.requires_candidate_attention


def test_large_disagreement_lowers_confidence_and_marks_candidate_attention() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)

    reconciled = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _revised_result(score=50, confidence=EvidenceConfidence.HIGH),
        policy=IndependentReviewPolicy(disagreement_threshold=15),
    )

    assert abs(reconciled.effective_score - assessment.overall_score) > 15
    assert reconciled.effective_confidence is EvidenceConfidence.LOW
    assert reconciled.requires_candidate_attention


def test_threshold_is_strictly_exceeded_before_attention_is_required() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)

    reconciled = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _revised_result(score=72),
        policy=IndependentReviewPolicy(disagreement_threshold=15),
    )

    assert not reconciled.requires_candidate_attention


@pytest.mark.parametrize(
    "critique",
    (
        "The Supervisor is accepting doctoral Candidates.",
        "The Supervisor is accepting Master's research students.",
        "The Supervisor has an opening for an MPhil student.",
        "The Supervisor is recruiting postgraduate research students.",
        "The Supervisor has room for doctoral Candidates.",
        "The Supervisor can supervise new PhD students.",
        "The Supervisor is able to supervise another doctoral Candidate.",
        "The Supervisor is looking to supervise PhD students.",
        "The Supervisor has an opening for a PhD student.",
        "The Supervisor is keen on supervising doctoral students.",
        "The Supervisor has funding for one doctoral researcher.",
        "The Supervisor could host another Candidate.",
        "The Supervisor welcomes applications.",
        "The Supervisor is open for applications.",
        "The Supervisor appears willing to consider applications.",
        "The Candidate has strong admission prospects.",
    ),
)
def test_reviewer_attempting_forbidden_inference_is_rejected(critique: str) -> None:
    malformed = {
        "decision": "revise",
        "recommended_score": 75,
        "unsupported_claim_ids": [],
        "overlooked_evidence_ids": [],
        "confidence": "medium",
        "critique": critique,
    }
    model = FakeIndependentReviewModel(malformed)

    reconciled = IndependentReviewAgent(model).review(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.INVALID_OUTPUT


def test_non_availability_application_research_remains_valid_review_prose() -> None:
    result = _accepted_result().model_copy(
        update={"critique": "The Supervisor studies enterprise applications of agentic AI."}
    )

    reconciled = IndependentReviewAgent(FakeIndependentReviewModel(result)).review(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )

    assert reconciled.review_status is IndependentReviewStatus.ACCEPTED


def test_reviewer_attempting_admission_probability_is_rejected() -> None:
    malformed = {
        "decision": "revise",
        "recommended_score": 75,
        "unsupported_claim_ids": [],
        "overlooked_evidence_ids": [],
        "confidence": "medium",
        "critique": "The Candidate has an 80% chance of being admitted.",
    }

    reconciled = IndependentReviewAgent(FakeIndependentReviewModel(malformed)).review(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.INVALID_OUTPUT


def test_reviewer_cannot_change_candidate_preferences() -> None:
    malformed = {
        "decision": "revise",
        "recommended_score": 75,
        "unsupported_claim_ids": [],
        "overlooked_evidence_ids": [],
        "confidence": "medium",
        "critique": "The score should be revised from the supplied evidence.",
        "revised_preferences": {"preferred_regions": ["Europe"]},
    }

    reconciled = IndependentReviewAgent(FakeIndependentReviewModel(malformed)).review(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.INVALID_OUTPUT


def test_nebius_timeout_preserves_score_and_reduces_confidence() -> None:
    model = FakeIndependentReviewModel(IndependentReviewModelInvocationError("synthetic timeout"))
    assessment = make_research_fit_assessment(1)

    reconciled = IndependentReviewAgent(model).review(
        make_candidate_profile(),
        make_verified_supervisor(1),
        assessment,
    )

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.MODEL_INVOCATION
    assert reconciled.initial_assessment == assessment
    assert reconciled.effective_score == assessment.overall_score
    assert reconciled.effective_confidence is EvidenceConfidence.LOW


def test_malformed_structured_response_is_a_safe_unavailable_review() -> None:
    model = FakeIndependentReviewModel(
        {
            "decision": "revise",
            "recommended_score": "seventy-five",
            "unsupported_claim_ids": [],
            "overlooked_evidence_ids": [],
            "confidence": "medium",
            "critique": "The evidence warrants revision.",
        }
    )

    reconciled = IndependentReviewAgent(model).review(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.INVALID_OUTPUT


def test_default_tests_use_the_fake_model_and_map_the_exact_domain_input() -> None:
    result = _accepted_result()
    model = FakeIndependentReviewModel(result)
    profile = make_candidate_profile()
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)

    reconciled = IndependentReviewAgent(model).review(profile, supervisor, assessment)

    assert reconciled.review_status is IndependentReviewStatus.ACCEPTED
    assert len(model.inputs) == 1
    assert model.inputs[0].candidate_profile == profile
    assert model.inputs[0].verified_supervisor == supervisor
    assert model.inputs[0].evidence_claims == supervisor.evidence
    assert model.inputs[0].initial_assessment == assessment
    assert model.inputs[0].removable_supporting_evidence_ids == assessment.supporting_evidence_ids
    assert model.inputs[0].eligible_overlooked_evidence_ids == ()


def test_review_input_rejects_a_tampered_overlooked_evidence_allowlist() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    review_input = IndependentReviewInput.from_domain(
        make_candidate_profile(),
        supervisor,
        assessment,
    )
    identity_id = next(
        claim.evidence_id
        for claim in supervisor.evidence
        if claim.claim_type is EvidenceClaimType.IDENTITY
    )

    with pytest.raises(ValidationError, match="deterministic allowlist"):
        IndependentReviewInput.model_validate(
            {
                **review_input.model_dump(mode="python"),
                "eligible_overlooked_evidence_ids": (identity_id,),
            }
        )


def test_accept_with_a_different_recommendation_still_preserves_original() -> None:
    assessment = make_research_fit_assessment(1)

    reconciled = reconcile_research_fit_assessment(
        make_verified_supervisor(1),
        assessment,
        _accepted_result(score=86),
    )

    assert reconciled.review_status is IndependentReviewStatus.ACCEPTED
    assert reconciled.failure_kind is None
    assert reconciled.effective_score == assessment.overall_score
    assert reconciled.effective_confidence is assessment.confidence


def test_proposed_recommendation_retains_review_audit_and_effective_score() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    review = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _revised_result(score=80),
    )

    recommendation = ProposedSupervisorRecommendation(
        rank=1,
        supervisor=supervisor,
        assessment=assessment,
        strengths=("The verified evidence supports a strong Research Fit.",),
        availability_status=supervisor.availability_status,
        evidence_confidence=review.effective_confidence,
        independent_review=review,
    )

    assert recommendation.effective_score == 80
    assert recommendation.effective_rationale == review.critique
    assert recommendation.assessment.overall_score == 87


def test_large_downward_revision_is_serialized_without_initial_strength_overclaim() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    review = reconcile_research_fit_assessment(
        supervisor,
        assessment,
        _revised_result(score=1, confidence=EvidenceConfidence.HIGH),
    )

    proposal = ShortlistSynthesisAgent(max_results=1).synthesize(
        "candidate-001",
        (supervisor,),
        (assessment,),
        datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
        (review,),
    )
    recommendation = proposal.recommendations[0]
    serialized = proposal.model_dump(mode="json")

    assert recommendation.strengths == (
        "Independent review requires Candidate attention before relying on the "
        "initial Research Fit strengths.",
    )
    assert review.critique in recommendation.concerns
    assert serialized["recommendations"][0]["independent_review"]["effective_score"] == 1
    assert (
        serialized["recommendations"][0]["independent_review"]["effective_rationale"]
        == review.critique
    )


def test_reconciliation_record_has_a_lossless_json_round_trip() -> None:
    record = reconcile_research_fit_assessment(
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
        _revised_result(score=80),
    )

    restored = ReconciledResearchFitAssessment.model_validate_json(record.model_dump_json())

    assert restored == record
    assert restored.initial_assessment.overall_score == 87
    assert restored.effective_score == 80


def test_reconciliation_record_rejects_unsanitized_effective_evidence() -> None:
    record = reconcile_research_fit_assessment(
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
        _revised_result(
            score=75,
            unsupported_claim_ids=["evidence-001-research"],
        ),
    )

    with pytest.raises(ValidationError, match="remove unsupported claims"):
        record.model_copy(
            update={
                "effective_supporting_evidence_ids": (
                    *record.effective_supporting_evidence_ids,
                    "evidence-001-research",
                )
            }
        )


def test_proposal_rejects_a_review_for_another_supervisor() -> None:
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    other_review = reconcile_research_fit_assessment(
        make_verified_supervisor(2),
        make_research_fit_assessment(2),
        _accepted_result(score=82),
    )

    with pytest.raises(ValidationError, match="review and proposed Supervisor must match"):
        ProposedSupervisorRecommendation(
            rank=1,
            supervisor=supervisor,
            assessment=assessment,
            strengths=("Evidence-backed Research Fit.",),
            availability_status=supervisor.availability_status,
            evidence_confidence=other_review.effective_confidence,
            independent_review=other_review,
        )


def test_result_rejects_overlapping_evidence_and_accepted_changes() -> None:
    with pytest.raises(ValidationError, match="same evidence"):
        _revised_result(
            unsupported_claim_ids=["evidence-001"],
            overlooked_evidence_ids=["evidence-001"],
        )

    with pytest.raises(ValidationError, match="accepted review cannot alter"):
        IndependentReviewResult(
            decision=IndependentReviewDecision.ACCEPT,
            recommended_score=87,
            unsupported_claim_ids=["evidence-001"],
            overlooked_evidence_ids=[],
            confidence=EvidenceConfidence.HIGH,
            critique="The score is otherwise supported.",
        )


@pytest.mark.parametrize("threshold", [-1, 101, True])
def test_review_policy_rejects_invalid_thresholds(threshold: object) -> None:
    with pytest.raises(ValidationError):
        IndependentReviewPolicy.model_validate({"disagreement_threshold": threshold})
