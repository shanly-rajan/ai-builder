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
    evidence_claim_is_grounded_for_supervisor,
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


@pytest.mark.parametrize(
    ("supporting_excerpt", "availability_status"),
    (
        (
            "Professor Elias Hart is currently accepting new Master's research students.",
            AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
        (
            "Professor Elias Hart is accepting MPhil students.",
            AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
        (
            "Professor Elias Hart is accepting postgraduate research students.",
            AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
        (
            "Professor Elias Hart is not accepting new research-degree Candidates.",
            AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
        ),
    ),
)
def test_explicit_masters_and_other_research_degree_availability_is_grounded(
    supporting_excerpt: str,
    availability_status: AvailabilityStatus,
) -> None:
    prospective = make_prospective_supervisor(2)
    evidence = make_evidence_claims(2)
    availability = evidence[-1].model_copy(
        update={
            "supporting_excerpt": supporting_excerpt,
            "availability_status": availability_status,
        }
    )

    assert evidence_claim_is_grounded_for_supervisor(availability, prospective) is True
    assert (
        derive_availability_status((*evidence[:-1], availability), prospective.supervisor_id)
        is availability_status
    )


@pytest.mark.parametrize(
    "supporting_excerpt",
    (
        "Professor Elias Hart teaches students in the Master's programme.",
        "Professor Elias Hart welcomes students to taught postgraduate modules.",
        "Professor Elias Hart has supervised Master's students previously.",
    ),
)
def test_masters_teaching_or_supervision_history_is_not_current_availability(
    supporting_excerpt: str,
) -> None:
    prospective = make_prospective_supervisor(2)
    availability = make_evidence_claims(2)[-1].model_copy(
        update={"supporting_excerpt": supporting_excerpt}
    )

    assert evidence_claim_is_grounded_for_supervisor(availability, prospective) is False


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


@pytest.mark.parametrize("asserted_name", [None, "Dr Another Person"])
def test_identity_evidence_must_assert_the_same_supervisor_name(
    asserted_name: str | None,
) -> None:
    prospective = make_prospective_supervisor(1)
    evidence = make_evidence_claims(1)
    invalid_identity = evidence[0].model_copy(update={"asserted_name": asserted_name})
    invalid_evidence = (invalid_identity, *evidence[1:])

    assert missing_verification_evidence(invalid_evidence, prospective) == ("identity",)
    with pytest.raises(SupervisorVerificationError, match="identity"):
        verify_supervisor(prospective, invalid_evidence)


def test_direct_verified_construction_rejects_type_only_identity_evidence() -> None:
    verified = make_verified_supervisor(1)
    identity = verified.evidence[0].model_copy(update={"asserted_name": None})

    with pytest.raises(ValidationError, match="identity"):
        VerifiedSupervisor.model_validate(
            {
                **verified.model_dump(mode="python"),
                "evidence": (identity, *verified.evidence[1:]),
            }
        )


@pytest.mark.parametrize(
    "updates",
    [
        {"asserted_name": None},
        {"asserted_name": "Dr Another Person"},
        {"asserted_institution": None},
        {"asserted_department": None},
    ],
)
def test_affiliation_evidence_requires_the_same_name_institution_and_department(
    updates: dict[str, str | None],
) -> None:
    prospective = make_prospective_supervisor(1)
    evidence = make_evidence_claims(1)
    invalid_affiliation = evidence[1].model_copy(update=updates)
    invalid_evidence = (evidence[0], invalid_affiliation, *evidence[2:])

    assert missing_verification_evidence(invalid_evidence, prospective) == ("current_affiliation",)
    with pytest.raises(SupervisorVerificationError, match="current_affiliation"):
        verify_supervisor(prospective, invalid_evidence)


@pytest.mark.parametrize(
    ("field", "value"),
    [("asserted_institution", ""), ("asserted_department", " ")],
)
def test_affiliation_evidence_rejects_empty_typed_values(field: str, value: str) -> None:
    affiliation = make_evidence_claims(1)[1]

    with pytest.raises(ValidationError, match="at least 1 character"):
        affiliation.model_copy(update={field: value})


def test_direct_verified_construction_rejects_type_only_affiliation_evidence() -> None:
    verified = make_verified_supervisor(1)
    affiliation = verified.evidence[1].model_copy(
        update={
            "asserted_name": None,
            "asserted_institution": None,
            "asserted_department": None,
        }
    )

    with pytest.raises(ValidationError, match="current_affiliation"):
        VerifiedSupervisor.model_validate(
            {
                **verified.model_dump(mode="python"),
                "evidence": (verified.evidence[0], affiliation, *verified.evidence[2:]),
            }
        )


def test_every_direct_fixture_claim_is_subject_and_excerpt_grounded() -> None:
    prospective = make_prospective_supervisor(4)
    evidence = make_evidence_claims(4)

    assert all(evidence_claim_is_grounded_for_supervisor(claim, prospective) for claim in evidence)
    availability_source_urls = {
        str(claim.source_url)
        for claim in evidence
        if claim.claim_type is EvidenceClaimType.AVAILABILITY
    }
    assert len(availability_source_urls) == 2


@pytest.mark.parametrize(
    "updates",
    [
        {"supporting_excerpt": None},
        {"supporting_excerpt": "The profile names Dr Another Person."},
        {"supporting_excerpt": "The profile names Dr Amara Ndlovou."},
    ],
)
def test_identity_requires_the_exact_normalized_name_in_its_excerpt(
    updates: dict[str, str | None],
) -> None:
    prospective = make_prospective_supervisor(1)
    evidence = make_evidence_claims(1)
    identity = evidence[0].model_copy(update=updates)
    invalid_evidence = (identity, *evidence[1:])

    assert evidence_claim_is_grounded_for_supervisor(identity, prospective) is False
    assert missing_verification_evidence(invalid_evidence, prospective) == ("identity",)
    with pytest.raises(SupervisorVerificationError, match="identity"):
        verify_supervisor(prospective, invalid_evidence)


def test_identity_grounding_allows_only_a_leading_academic_title_variant() -> None:
    prospective = make_prospective_supervisor(1, full_name="Professor Amara Ndlovu")
    identity = make_evidence_claims(1)[0]

    assert identity.asserted_name == "Dr Amara Ndlovu"
    assert evidence_claim_is_grounded_for_supervisor(identity, prospective) is True


@pytest.mark.parametrize(
    "excerpt",
    [
        "Dr Amara Ndlovu is currently listed at Southern Cape Institute of Technology.",
        "Dr Amara Ndlovu is currently listed in the Department of Information Systems.",
    ],
)
def test_affiliation_requires_its_institution_and_department_in_the_excerpt(
    excerpt: str,
) -> None:
    prospective = make_prospective_supervisor(1)
    evidence = make_evidence_claims(1)
    affiliation = evidence[1].model_copy(update={"supporting_excerpt": excerpt})
    invalid_evidence = (evidence[0], affiliation, *evidence[2:])

    assert evidence_claim_is_grounded_for_supervisor(affiliation, prospective) is False
    assert missing_verification_evidence(invalid_evidence, prospective) == ("current_affiliation",)


@pytest.mark.parametrize(
    "updates",
    [
        {
            "asserted_name": "Dr Another Person",
            "supporting_excerpt": "Dr Another Person researches quantum biology.",
        },
        {
            "asserted_name": None,
            "supporting_excerpt": "The page discusses quantum biology.",
        },
        {
            "supporting_excerpt": (
                "Dr Amara Ndlovu hosts Dr Bongani Dube, whose research focuses on quantum biology."
            ),
        },
    ],
)
def test_wrong_person_or_generic_research_cannot_satisfy_verification(
    updates: dict[str, str | None],
) -> None:
    prospective = make_prospective_supervisor(1)
    evidence = make_evidence_claims(1)
    research = evidence[2].model_copy(update=updates)
    without_publication = tuple(
        claim
        for claim in (evidence[0], evidence[1], research, *evidence[3:])
        if claim.claim_type is not EvidenceClaimType.PUBLICATION
    )

    assert evidence_claim_is_grounded_for_supervisor(research, prospective) is False
    assert missing_verification_evidence(without_publication, prospective) == (
        "research_interest_or_publication",
    )
    with pytest.raises(SupervisorVerificationError, match="research_interest_or_publication"):
        verify_supervisor(prospective, without_publication)


@pytest.mark.parametrize(
    "updates",
    [
        {
            "asserted_name": "Dr Another Person",
            "supporting_excerpt": (
                "Dr Another Person is currently accepting new doctoral Candidates."
            ),
        },
        {"supporting_excerpt": ("Professor Elias Hart is not accepting new doctoral Candidates.")},
        {
            "supporting_excerpt": (
                "Professor Elias Hart has supervised doctoral Candidates previously."
            )
        },
        {
            "supporting_excerpt": (
                "Professor Elias Hart collaborates with Dr Bongani Dube, who is currently "
                "accepting new doctoral Candidates."
            )
        },
        {"supporting_excerpt": ("Professor Elias Hart isn't accepting new doctoral Candidates.")},
        {"supporting_excerpt": ("Professor Elias Hart isn’t accepting new doctoral Candidates.")},
    ],
)
def test_availability_requires_the_same_supervisor_and_matching_explicit_polarity(
    updates: dict[str, str],
) -> None:
    prospective = make_prospective_supervisor(2)
    evidence = make_evidence_claims(2)
    availability = evidence[-1].model_copy(update=updates)
    invalid_evidence = (*evidence[:-1], availability)

    assert evidence_claim_is_grounded_for_supervisor(availability, prospective) is False
    with pytest.raises(SupervisorVerificationError, match="inconsistent"):
        verify_supervisor(prospective, invalid_evidence)


def test_indirect_evidence_does_not_satisfy_verification() -> None:
    prospective = make_prospective_supervisor(1)
    evidence = make_evidence_claims(1)
    identity = evidence[0]
    indirect_identity = EvidenceClaim.model_validate(
        {**identity.model_dump(mode="python"), "directly_supported": False}
    )
    with_indirect_identity = (indirect_identity, *evidence[1:])

    assert missing_verification_evidence(with_indirect_identity, prospective) == ("identity",)
    with pytest.raises(SupervisorVerificationError, match="identity"):
        verify_supervisor(prospective, with_indirect_identity)


def test_evidence_for_another_supervisor_does_not_satisfy_verification() -> None:
    prospective = make_prospective_supervisor(1)
    evidence = tuple(
        EvidenceClaim.model_validate(
            {**claim.model_dump(mode="python"), "supervisor_id": "supervisor-999"}
        )
        for claim in make_evidence_claims(1)
    )

    assert missing_verification_evidence(evidence, prospective) == (
        "identity",
        "current_affiliation",
        "research_interest_or_publication",
    )
    with pytest.raises(SupervisorVerificationError, match="missing evidence"):
        verify_supervisor(prospective, evidence)


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
