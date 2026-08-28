"""Unit tests for deterministic Supervisor lifecycle transitions."""

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    AvailabilityStatus,
    CandidateApprovalRequiredError,
    CandidateReviewAction,
    CandidateReviewDecision,
    CandidateReviewScopeError,
    EvidenceClaim,
    EvidenceClaimType,
    InvalidSupervisorTransitionError,
    SupervisorLifecycleStatus,
    SupervisorVerificationError,
    VerificationStatus,
    VerifiedSupervisor,
    apply_candidate_review,
    create_supervisor_shortlist,
    derive_availability_status,
    is_structural_transition_allowed,
    missing_verification_evidence,
    structurally_allowed_transitions,
    validate_structural_transition,
    verify_supervisor,
)
from tests.fixtures import (
    FIXED_RETRIEVED_AT,
    make_evidence_claims,
    make_prospective_supervisor,
    make_verified_supervisor,
)


def _decision(action: CandidateReviewAction, *supervisor_ids: str) -> CandidateReviewDecision:
    return CandidateReviewDecision(
        action=action,
        supervisor_ids=supervisor_ids,
        reason="Candidate reviewed the evidence and Research Fit assessment.",
    )


def test_structural_lifecycle_transitions_match_the_canonical_flow() -> None:
    expected = {
        SupervisorLifecycleStatus.PROSPECTIVE: {SupervisorLifecycleStatus.VERIFIED},
        SupervisorLifecycleStatus.VERIFIED: {
            SupervisorLifecycleStatus.SHORTLISTED,
            SupervisorLifecycleStatus.REJECTED,
        },
        SupervisorLifecycleStatus.SHORTLISTED: set(),
        SupervisorLifecycleStatus.REJECTED: set(),
    }

    for current_status in SupervisorLifecycleStatus:
        assert structurally_allowed_transitions(current_status) == frozenset(
            expected[current_status]
        )
        for target_status in SupervisorLifecycleStatus:
            assert is_structural_transition_allowed(current_status, target_status) is (
                target_status in expected[current_status]
            )


def test_valid_transition_passes_validation() -> None:
    validate_structural_transition(
        SupervisorLifecycleStatus.PROSPECTIVE,
        SupervisorLifecycleStatus.VERIFIED,
    )


@pytest.mark.parametrize(
    ("current_status", "target_status"),
    [
        (SupervisorLifecycleStatus.PROSPECTIVE, SupervisorLifecycleStatus.SHORTLISTED),
        (SupervisorLifecycleStatus.VERIFIED, SupervisorLifecycleStatus.PROSPECTIVE),
        (SupervisorLifecycleStatus.SHORTLISTED, SupervisorLifecycleStatus.REJECTED),
        (SupervisorLifecycleStatus.REJECTED, SupervisorLifecycleStatus.VERIFIED),
        (SupervisorLifecycleStatus.VERIFIED, SupervisorLifecycleStatus.VERIFIED),
    ],
)
def test_invalid_lifecycle_transitions_are_rejected(
    current_status: SupervisorLifecycleStatus,
    target_status: SupervisorLifecycleStatus,
) -> None:
    with pytest.raises(InvalidSupervisorTransitionError, match="Cannot move a Supervisor"):
        validate_structural_transition(current_status, target_status)


def test_verification_succeeds_with_required_direct_evidence() -> None:
    prospective = make_prospective_supervisor(1)

    verified = verify_supervisor(prospective, make_evidence_claims(1))

    assert verified.status is SupervisorLifecycleStatus.VERIFIED
    assert verified.verification_status is VerificationStatus.VERIFIED
    assert verified.supervisor_id == prospective.supervisor_id


def test_availability_not_stated_does_not_block_verification() -> None:
    verified = verify_supervisor(
        make_prospective_supervisor(1),
        make_evidence_claims(1),
        availability_status=AvailabilityStatus.NOT_STATED,
    )

    assert verified.availability_status is AvailabilityStatus.NOT_STATED


@pytest.mark.parametrize(
    ("index", "expected_status"),
    [
        (1, AvailabilityStatus.NOT_STATED),
        (2, AvailabilityStatus.CONFIRMED_ACCEPTING),
        (3, AvailabilityStatus.CONFIRMED_NOT_ACCEPTING),
        (4, AvailabilityStatus.CONFLICTING_EVIDENCE),
    ],
)
def test_availability_is_derived_without_blocking_verification(
    index: int, expected_status: AvailabilityStatus
) -> None:
    prospective = make_prospective_supervisor(index)
    evidence = make_evidence_claims(index)

    assert derive_availability_status(evidence, prospective.supervisor_id) is expected_status
    assert verify_supervisor(prospective, evidence).availability_status is expected_status


def test_verification_concerns_are_explicitly_classified() -> None:
    verified = verify_supervisor(
        make_prospective_supervisor(1),
        make_evidence_claims(1),
        verification_concerns=("The publication date needs a second source.",),
    )

    assert verified.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS
    assert verified.verification_concerns == ("The publication date needs a second source.",)


@pytest.mark.parametrize(
    ("excluded_claim_types", "expected_missing"),
    [
        ({EvidenceClaimType.IDENTITY}, "identity"),
        ({EvidenceClaimType.CURRENT_AFFILIATION}, "current_affiliation"),
        (
            {
                EvidenceClaimType.RESEARCH_INTEREST,
                EvidenceClaimType.PUBLICATION,
            },
            "research_interest_or_publication",
        ),
    ],
)
def test_verification_rejects_missing_required_evidence(
    excluded_claim_types: set[EvidenceClaimType], expected_missing: str
) -> None:
    evidence = tuple(
        claim for claim in make_evidence_claims(1) if claim.claim_type not in excluded_claim_types
    )

    with pytest.raises(SupervisorVerificationError, match=expected_missing):
        verify_supervisor(make_prospective_supervisor(1), evidence)


def test_direct_verified_construction_rejects_missing_identity_evidence() -> None:
    verified = make_verified_supervisor(1)
    evidence = tuple(
        claim for claim in verified.evidence if claim.claim_type is not EvidenceClaimType.IDENTITY
    )

    with pytest.raises(ValidationError, match="identity"):
        VerifiedSupervisor.model_validate(
            {**verified.model_dump(mode="python"), "evidence": evidence}
        )


def test_indirect_evidence_does_not_satisfy_verification() -> None:
    evidence = make_evidence_claims(1)
    identity = evidence[0]
    indirect_identity = EvidenceClaim.model_validate(
        {**identity.model_dump(mode="python"), "directly_supported": False}
    )
    with_indirect_identity = (indirect_identity, *evidence[1:])

    assert missing_verification_evidence(with_indirect_identity, "supervisor-001") == ("identity",)
    with pytest.raises(SupervisorVerificationError, match="identity"):
        verify_supervisor(make_prospective_supervisor(1), with_indirect_identity)


def test_evidence_for_another_supervisor_does_not_satisfy_verification() -> None:
    evidence = tuple(
        EvidenceClaim.model_validate(
            {**claim.model_dump(mode="python"), "supervisor_id": "supervisor-999"}
        )
        for claim in make_evidence_claims(1)
    )

    assert missing_verification_evidence(evidence, "supervisor-001") == (
        "identity",
        "current_affiliation",
        "research_interest_or_publication",
    )
    with pytest.raises(SupervisorVerificationError, match="missing evidence"):
        verify_supervisor(make_prospective_supervisor(1), evidence)


def test_verification_normalizes_duplicate_evidence_errors() -> None:
    evidence = make_evidence_claims(1)

    with pytest.raises(SupervisorVerificationError, match="evidence collection is inconsistent"):
        verify_supervisor(
            make_prospective_supervisor(1),
            (*evidence, evidence[0]),
        )


def test_verification_normalizes_foreign_evidence_errors() -> None:
    evidence = make_evidence_claims(1)
    foreign = EvidenceClaim.model_validate(
        {
            **evidence[0].model_dump(mode="python"),
            "evidence_id": "evidence-foreign-identity",
            "supervisor_id": "supervisor-999",
        }
    )

    with pytest.raises(SupervisorVerificationError, match="evidence collection is inconsistent"):
        verify_supervisor(make_prospective_supervisor(1), (*evidence, foreign))


def test_stated_availability_requires_matching_availability_evidence() -> None:
    with pytest.raises(SupervisorVerificationError, match="evidence collection is inconsistent"):
        verify_supervisor(
            make_prospective_supervisor(1),
            make_evidence_claims(1),
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        )


@pytest.mark.parametrize(
    ("action", "expected_status"),
    [
        (CandidateReviewAction.APPROVE, SupervisorLifecycleStatus.SHORTLISTED),
        (CandidateReviewAction.REJECT, SupervisorLifecycleStatus.REJECTED),
    ],
)
def test_candidate_review_applies_terminal_decision(
    action: CandidateReviewAction, expected_status: SupervisorLifecycleStatus
) -> None:
    verified = make_verified_supervisor(1)

    reviewed = apply_candidate_review(verified, _decision(action, verified.supervisor_id))

    assert reviewed.status is expected_status
    assert reviewed.evidence == verified.evidence
    assert reviewed.candidate_review_decision is not None
    assert reviewed.candidate_review_decision.action is action


def test_request_more_preserves_verified_state() -> None:
    verified = make_verified_supervisor(1)

    reviewed = apply_candidate_review(
        verified,
        _decision(CandidateReviewAction.REQUEST_MORE, verified.supervisor_id),
    )

    assert reviewed.status is SupervisorLifecycleStatus.VERIFIED
    assert reviewed.candidate_review_decision is not None
    assert reviewed.candidate_review_decision.action is CandidateReviewAction.REQUEST_MORE


def test_candidate_review_must_address_the_supervisor() -> None:
    with pytest.raises(CandidateReviewScopeError, match="does not address"):
        apply_candidate_review(
            make_verified_supervisor(1),
            _decision(CandidateReviewAction.APPROVE, "supervisor-002"),
        )


def test_candidate_review_cannot_reapply_to_terminal_state() -> None:
    verified = make_verified_supervisor(1)
    shortlisted = apply_candidate_review(
        verified,
        _decision(CandidateReviewAction.APPROVE, verified.supervisor_id),
    )

    with pytest.raises(InvalidSupervisorTransitionError, match="only be applied"):
        apply_candidate_review(
            shortlisted,
            _decision(CandidateReviewAction.REQUEST_MORE, shortlisted.supervisor_id),
        )


def test_shortlist_creation_requires_candidate_approval() -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(CandidateApprovalRequiredError, match="approval is required"):
        create_supervisor_shortlist(
            "candidate-001",
            (verified,),
            _decision(CandidateReviewAction.REJECT, verified.supervisor_id),
            generated_at=FIXED_RETRIEVED_AT,
            briefing="Evidence-backed briefing.",
        )


def test_shortlist_creation_rejects_unknown_decision_scope() -> None:
    with pytest.raises(CandidateReviewScopeError, match="unknown Supervisor identifiers"):
        create_supervisor_shortlist(
            "candidate-001",
            (make_verified_supervisor(1),),
            _decision(CandidateReviewAction.APPROVE, "supervisor-999"),
            generated_at=FIXED_RETRIEVED_AT,
            briefing="Evidence-backed briefing.",
        )


def test_shortlist_creation_rejects_duplicate_input_identifiers() -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(CandidateReviewScopeError, match="input identifiers must be unique"):
        create_supervisor_shortlist(
            "candidate-001",
            (verified, verified),
            _decision(CandidateReviewAction.APPROVE, verified.supervisor_id),
            generated_at=FIXED_RETRIEVED_AT,
            briefing="Evidence-backed briefing.",
        )


def test_shortlist_creation_preserves_candidate_approved_order() -> None:
    supervisors = (make_verified_supervisor(1), make_verified_supervisor(2))
    decision = _decision(
        CandidateReviewAction.APPROVE,
        "supervisor-002",
        "supervisor-001",
    )

    shortlist = create_supervisor_shortlist(
        "candidate-001",
        supervisors,
        decision,
        generated_at=FIXED_RETRIEVED_AT,
        briefing="Two approved, evidence-backed Supervisors.",
    )

    assert tuple(supervisor.supervisor_id for supervisor in shortlist.shortlisted_supervisors) == (
        "supervisor-002",
        "supervisor-001",
    )
    assert all(
        supervisor.status is SupervisorLifecycleStatus.SHORTLISTED
        for supervisor in shortlist.shortlisted_supervisors
    )
