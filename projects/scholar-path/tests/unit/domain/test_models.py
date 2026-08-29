"""Unit tests for immutable ScholarPath Pydantic contracts."""

from datetime import datetime
from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from scholarpath.domain import (
    AvailabilityStatus,
    CandidatePreferenceRevision,
    CandidateReviewAction,
    CandidateReviewDecision,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    ProspectiveSupervisor,
    ResearchFitAssessment,
    ResearchFitBreakdown,
    ResearchFitEvidenceError,
    SearchPlan,
    SupervisorLifecycleStatus,
    SupervisorShortlist,
    VerificationStatus,
    VerifiedSupervisor,
    apply_candidate_review,
    validate_research_fit_evidence,
)
from tests.fixtures import (
    FIXED_RETRIEVED_AT,
    make_candidate_profile,
    make_evidence_claims,
    make_prospective_supervisor,
    make_research_fit_assessment,
    make_search_plan,
    make_verified_supervisor,
)


def _replace(model: BaseModel, **updates: object) -> dict[str, Any]:
    return {**model.model_dump(mode="python"), **updates}


def _shortlisted_supervisor(index: int = 1) -> VerifiedSupervisor:
    verified = make_verified_supervisor(index)
    decision = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=(verified.supervisor_id,),
        reason="The Candidate approved the evidence-backed recommendation.",
    )
    return apply_candidate_review(verified, decision)


def test_every_m1_model_constructs_and_serializes() -> None:
    candidate = make_candidate_profile()
    search_plan = make_search_plan()
    prospective = make_prospective_supervisor(1)
    evidence = make_evidence_claims(1)[0]
    verified = make_verified_supervisor(1)
    breakdown = make_research_fit_assessment(1).breakdown
    assessment = make_research_fit_assessment(1)
    revision = CandidatePreferenceRevision(preferred_regions=("South Africa",))
    decision = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=(verified.supervisor_id,),
        reason="The verified research profile is relevant.",
        revised_preferences=revision,
    )
    shortlist = SupervisorShortlist(
        candidate_id=candidate.candidate_id,
        shortlisted_supervisors=(_shortlisted_supervisor(),),
        generated_at=FIXED_RETRIEVED_AT,
        briefing="One evidence-backed Supervisor approved by the Candidate.",
    )

    models: tuple[BaseModel, ...] = (
        candidate,
        search_plan,
        prospective,
        evidence,
        verified,
        breakdown,
        assessment,
        revision,
        decision,
        shortlist,
    )
    for model in models:
        payload = model.model_dump(mode="json")
        assert isinstance(payload, dict)
        assert model.model_dump_json().startswith("{")


@pytest.mark.parametrize(
    "model",
    [
        make_candidate_profile(),
        make_search_plan(),
        make_prospective_supervisor(1),
        make_evidence_claims(1)[0],
        make_verified_supervisor(1),
        make_research_fit_assessment(1).breakdown,
        make_research_fit_assessment(1),
        CandidatePreferenceRevision(exclusions=("fully residential",)),
        CandidateReviewDecision(
            action=CandidateReviewAction.REQUEST_MORE,
            supervisor_ids=("supervisor-001",),
            reason="Retrieve another institutional source.",
        ),
        SupervisorShortlist(
            candidate_id="candidate-001",
            shortlisted_supervisors=(_shortlisted_supervisor(),),
            generated_at=FIXED_RETRIEVED_AT,
            briefing="Candidate-approved shortlist.",
        ),
    ],
)
def test_model_json_round_trip(model: BaseModel) -> None:
    restored = type(model).model_validate_json(model.model_dump_json())

    assert restored == model


@pytest.mark.parametrize("bad_url", ["not-a-url", "/relative/profile", "ftp://example.test"])
def test_prospective_supervisor_rejects_invalid_profile_url(bad_url: str) -> None:
    prospective = make_prospective_supervisor(1)

    with pytest.raises(ValidationError, match="profile_url"):
        ProspectiveSupervisor.model_validate(_replace(prospective, profile_url=bad_url))


def test_evidence_claim_rejects_invalid_source_url() -> None:
    evidence = make_evidence_claims(1)[0]

    with pytest.raises(ValidationError, match="source_url"):
        EvidenceClaim.model_validate(_replace(evidence, source_url="not-a-url"))


@pytest.mark.parametrize("invalid_value", [1, 0, "yes", "false"])
def test_evidence_direct_support_flag_rejects_coercible_values(
    invalid_value: object,
) -> None:
    evidence = make_evidence_claims(1)[0]

    with pytest.raises(ValidationError, match="directly_supported"):
        EvidenceClaim.model_validate(_replace(evidence, directly_supported=invalid_value))


@pytest.mark.parametrize(
    ("model_type", "payload", "field_name"),
    [
        (
            type(make_candidate_profile()),
            _replace(make_candidate_profile(), candidate_id="   "),
            "candidate_id",
        ),
        (
            type(make_candidate_profile()),
            _replace(make_candidate_profile(), proposed_research_statement=""),
            "proposed_research_statement",
        ),
        (
            type(make_candidate_profile()),
            _replace(make_candidate_profile(), research_topics=()),
            "research_topics",
        ),
        (
            SearchPlan,
            _replace(make_search_plan(), search_queries=()),
            "search_queries",
        ),
        (
            SearchPlan,
            _replace(make_search_plan(), expanded_research_concepts=()),
            "expanded_research_concepts",
        ),
        (
            ProspectiveSupervisor,
            _replace(make_prospective_supervisor(1), full_name=""),
            "full_name",
        ),
        (
            EvidenceClaim,
            _replace(make_evidence_claims(1)[0], claim=""),
            "claim",
        ),
        (
            VerifiedSupervisor,
            _replace(make_verified_supervisor(1), evidence=()),
            "evidence",
        ),
        (
            ResearchFitAssessment,
            _replace(make_research_fit_assessment(1), supporting_evidence_ids=()),
            "Assessment evidence identifiers",
        ),
        (
            CandidateReviewDecision,
            {
                "action": CandidateReviewAction.REJECT,
                "supervisor_ids": (),
                "reason": "No fit.",
            },
            "supervisor_ids",
        ),
        (
            SupervisorShortlist,
            {
                "candidate_id": "candidate-001",
                "shortlisted_supervisors": (),
                "generated_at": FIXED_RETRIEVED_AT,
                "briefing": "Candidate-approved shortlist.",
            },
            "shortlisted_supervisors",
        ),
    ],
)
def test_models_reject_empty_required_fields(
    model_type: type[BaseModel], payload: dict[str, object], field_name: str
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        model_type.model_validate(payload)


@pytest.mark.parametrize("score", [-1, 101])
@pytest.mark.parametrize(
    "field_name",
    [
        "topic_alignment",
        "methodological_alignment",
        "research_orientation_alignment",
        "recent_research_alignment",
        "practical_constraint_alignment",
    ],
)
def test_research_fit_breakdown_rejects_scores_outside_range(field_name: str, score: int) -> None:
    breakdown = make_research_fit_assessment(1).breakdown

    with pytest.raises(ValidationError, match=field_name):
        ResearchFitBreakdown.model_validate(_replace(breakdown, **{field_name: score}))


@pytest.mark.parametrize("score", [-1, 101])
def test_research_fit_assessment_rejects_overall_score_outside_range(score: int) -> None:
    assessment = make_research_fit_assessment(1)

    with pytest.raises(ValidationError, match="overall_score"):
        ResearchFitAssessment.model_validate(_replace(assessment, overall_score=score))


@pytest.mark.parametrize("invalid_score", [True, "90", 84.5])
def test_research_fit_scores_reject_coercible_values(invalid_score: object) -> None:
    assessment = make_research_fit_assessment(1)

    with pytest.raises(ValidationError, match="overall_score"):
        ResearchFitAssessment.model_validate(_replace(assessment, overall_score=invalid_score))
    with pytest.raises(ValidationError, match="topic_alignment"):
        ResearchFitBreakdown.model_validate(
            _replace(assessment.breakdown, topic_alignment=invalid_score)
        )


def test_verified_supervisor_rejects_duplicate_evidence_identifiers() -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(ValidationError, match="Evidence identifiers must be unique"):
        VerifiedSupervisor.model_validate(
            _replace(verified, evidence=(*verified.evidence, verified.evidence[0]))
        )


def test_verified_supervisor_rejects_evidence_owned_by_another_supervisor() -> None:
    verified = make_verified_supervisor(1)
    foreign = EvidenceClaim.model_validate(
        _replace(verified.evidence[0], supervisor_id="supervisor-999")
    )

    with pytest.raises(ValidationError, match="reference this Supervisor"):
        VerifiedSupervisor.model_validate(
            _replace(verified, evidence=(foreign, *verified.evidence[1:]))
        )


def test_verified_supervisor_rejects_stated_availability_without_provenance() -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(ValidationError, match="Availability status must match"):
        VerifiedSupervisor.model_validate(
            _replace(verified, availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING)
        )


def test_availability_evidence_requires_a_typed_outcome() -> None:
    evidence = make_evidence_claims(1)[0]

    with pytest.raises(ValidationError, match="must assert accepting or not-accepting"):
        EvidenceClaim.model_validate(_replace(evidence, claim_type=EvidenceClaimType.AVAILABILITY))


def test_non_availability_evidence_rejects_an_availability_outcome() -> None:
    evidence = make_evidence_claims(1)[0]

    with pytest.raises(ValidationError, match="Only availability evidence"):
        EvidenceClaim.model_validate(
            _replace(
                evidence,
                availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
            )
        )


def test_verified_supervisor_rejects_mismatched_availability_outcome() -> None:
    verified = make_verified_supervisor(2)

    with pytest.raises(ValidationError, match="Availability status must match"):
        VerifiedSupervisor.model_validate(
            _replace(
                verified,
                availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
            )
        )


def test_conflicting_availability_requires_both_explicit_outcomes() -> None:
    verified = make_verified_supervisor(2)

    with pytest.raises(ValidationError, match="Availability status must match"):
        VerifiedSupervisor.model_validate(
            _replace(
                verified,
                availability_status=AvailabilityStatus.CONFLICTING_EVIDENCE,
            )
        )


def test_conflicting_availability_requires_distinct_sources() -> None:
    verified = make_verified_supervisor(4)
    availability_claims = [
        claim for claim in verified.evidence if claim.claim_type is EvidenceClaimType.AVAILABILITY
    ]
    repeated_source_claim = EvidenceClaim.model_validate(
        _replace(availability_claims[1], source_url=availability_claims[0].source_url)
    )
    evidence = tuple(
        repeated_source_claim if claim.evidence_id == repeated_source_claim.evidence_id else claim
        for claim in verified.evidence
    )

    with pytest.raises(ValidationError, match="requires distinct evidence sources"):
        VerifiedSupervisor.model_validate(_replace(verified, evidence=evidence))


@pytest.mark.parametrize(
    ("verification_status", "concerns"),
    [
        (VerificationStatus.VERIFIED, ("Unresolved identity variant.",)),
        (VerificationStatus.VERIFIED_WITH_CONCERNS, ()),
    ],
)
def test_verified_supervisor_requires_consistent_concern_status(
    verification_status: VerificationStatus, concerns: tuple[str, ...]
) -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(ValidationError, match="must be consistent"):
        VerifiedSupervisor.model_validate(
            _replace(
                verified,
                verification_status=verification_status,
                verification_concerns=concerns,
            )
        )


def test_fit_assessment_rejects_duplicate_supporting_evidence() -> None:
    assessment = make_research_fit_assessment(1)
    duplicated = (assessment.supporting_evidence_ids[0],) * 2

    with pytest.raises(ValidationError, match="Supporting evidence identifiers must be unique"):
        ResearchFitAssessment.model_validate(
            _replace(assessment, supporting_evidence_ids=duplicated)
        )


def test_fit_evidence_validation_rejects_another_supervisor() -> None:
    with pytest.raises(ResearchFitEvidenceError, match="identifiers must match"):
        validate_research_fit_evidence(
            make_verified_supervisor(2),
            make_research_fit_assessment(1),
        )


def test_fit_evidence_validation_rejects_unknown_evidence_id() -> None:
    supervisor = make_verified_supervisor(1)
    original = make_research_fit_assessment(1)
    topic_alignment = original.breakdown.topic_alignment.model_copy(
        update={"supporting_evidence_ids": ("evidence-unknown",)}
    )
    breakdown = original.breakdown.model_copy(update={"topic_alignment": topic_alignment})
    supporting_evidence_ids = tuple(
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
    assessment = original.model_copy(
        update={
            "breakdown": breakdown,
            "supporting_evidence_ids": supporting_evidence_ids,
        }
    )

    with pytest.raises(ResearchFitEvidenceError, match="outside the Verified Supervisor"):
        validate_research_fit_evidence(supervisor, assessment)


def test_fit_evidence_validation_accepts_owned_evidence() -> None:
    validate_research_fit_evidence(
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )


def test_empty_candidate_preference_revision_is_invalid() -> None:
    with pytest.raises(ValidationError, match="At least one revised preference"):
        CandidatePreferenceRevision()


def test_candidate_review_decision_rejects_duplicate_supervisor_ids() -> None:
    with pytest.raises(ValidationError, match="Supervisor identifiers must be unique"):
        CandidateReviewDecision(
            action=CandidateReviewAction.APPROVE,
            supervisor_ids=("supervisor-001", "supervisor-001"),
            reason="Approve the evidence-backed recommendation.",
        )


@pytest.mark.parametrize(
    ("status", "decision"),
    [
        (SupervisorLifecycleStatus.SHORTLISTED, None),
        (SupervisorLifecycleStatus.REJECTED, None),
        (
            SupervisorLifecycleStatus.SHORTLISTED,
            CandidateReviewDecision(
                action=CandidateReviewAction.REJECT,
                supervisor_ids=("supervisor-001",),
                reason="The Candidate rejected this record.",
            ),
        ),
    ],
)
def test_terminal_supervisor_status_requires_matching_candidate_decision(
    status: SupervisorLifecycleStatus,
    decision: CandidateReviewDecision | None,
) -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(ValidationError, match="requires the matching Candidate decision"):
        VerifiedSupervisor.model_validate(
            _replace(
                verified,
                status=status,
                candidate_review_decision=decision,
            )
        )


def test_verified_status_rejects_non_request_more_decision() -> None:
    verified = make_verified_supervisor(1)
    approval = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=(verified.supervisor_id,),
        reason="The Candidate approved this record.",
    )

    with pytest.raises(ValidationError, match="request-more decision"):
        VerifiedSupervisor.model_validate(_replace(verified, candidate_review_decision=approval))


def test_model_copy_revalidates_lifecycle_updates() -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(ValidationError, match="requires the matching Candidate decision"):
        verified.model_copy(update={"status": SupervisorLifecycleStatus.SHORTLISTED})


def test_model_copy_without_updates_preserves_a_valid_record() -> None:
    verified = make_verified_supervisor(1)

    assert verified.model_copy() == verified


def test_shortlist_rejects_duplicate_supervisors() -> None:
    supervisor = _shortlisted_supervisor()

    with pytest.raises(ValidationError, match="identifiers must be unique"):
        SupervisorShortlist(
            candidate_id="candidate-001",
            shortlisted_supervisors=(supervisor, supervisor),
            generated_at=FIXED_RETRIEVED_AT,
            briefing="Candidate-approved shortlist.",
        )


def test_shortlist_rejects_supervisor_without_shortlisted_status() -> None:
    with pytest.raises(ValidationError, match="must have shortlisted status"):
        SupervisorShortlist(
            candidate_id="candidate-001",
            shortlisted_supervisors=(make_verified_supervisor(1),),
            generated_at=FIXED_RETRIEVED_AT,
            briefing="Candidate-approved shortlist.",
        )


@pytest.mark.parametrize(
    ("model_type", "payload", "field_name"),
    [
        (
            EvidenceClaim,
            _replace(
                make_evidence_claims(1)[0],
                retrieved_at=datetime(2026, 8, 1, 9, 30),
            ),
            "retrieved_at",
        ),
        (
            SupervisorShortlist,
            {
                "candidate_id": "candidate-001",
                "shortlisted_supervisors": (_shortlisted_supervisor(),),
                "generated_at": datetime(2026, 8, 1, 9, 30),
                "briefing": "Candidate-approved shortlist.",
            },
            "generated_at",
        ),
    ],
)
def test_provenance_timestamps_must_be_timezone_aware(
    model_type: type[BaseModel], payload: dict[str, object], field_name: str
) -> None:
    with pytest.raises(ValidationError, match=field_name):
        model_type.model_validate(payload)


def test_unknown_fields_are_rejected() -> None:
    with pytest.raises(ValidationError, match="unexpected_field"):
        type(make_candidate_profile()).model_validate(
            _replace(make_candidate_profile(), unexpected_field="not allowed")
        )


def test_enum_values_match_the_canonical_contract() -> None:
    assert {status.value for status in SupervisorLifecycleStatus} == {
        "prospective",
        "verified",
        "shortlisted",
        "rejected",
    }
    assert {status.value for status in AvailabilityStatus} == {
        "confirmed_accepting",
        "confirmed_not_accepting",
        "not_stated",
        "conflicting_evidence",
    }
    assert {action.value for action in CandidateReviewAction} == {
        "approve",
        "reject",
        "request_more",
    }
    assert {confidence.value for confidence in EvidenceConfidence} == {
        "low",
        "medium",
        "high",
    }
    assert EvidenceClaimType.IDENTITY.value == "identity"
