"""Focused M6 domain tests for partial verification and evidence conflicts."""

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    EvidenceClaim,
    SourceKind,
    SupervisorLifecycleStatus,
    SupervisorVerificationRecord,
    VerificationStatus,
    VerifiedSupervisor,
    missing_verification_evidence,
)
from tests.fixtures.factories import (
    make_evidence_claims,
    make_prospective_supervisor,
    make_verified_supervisor,
)


def _partial_record(
    *,
    evidence: tuple[EvidenceClaim, ...] = (),
) -> SupervisorVerificationRecord:
    prospective = make_prospective_supervisor(1)
    return SupervisorVerificationRecord(
        prospective_supervisor=prospective,
        evidence=evidence,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        missing_required_evidence=missing_verification_evidence(evidence, prospective),
    )


def test_partial_verification_status_survives_a_json_round_trip() -> None:
    record = _partial_record(evidence=(make_evidence_claims(1)[0],))

    restored = SupervisorVerificationRecord.model_validate_json(record.model_dump_json())

    assert restored == record
    assert restored.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert restored.prospective_supervisor.status is SupervisorLifecycleStatus.PROSPECTIVE
    assert restored.verified_supervisor is None


def test_evidence_claim_rejects_a_self_referencing_conflict_identifier() -> None:
    claim = make_evidence_claims(1)[0]

    with pytest.raises(ValidationError, match="cannot conflict with itself"):
        claim.model_copy(update={"conflicting_evidence_ids": (claim.evidence_id,)})


def test_evidence_claim_rejects_duplicate_conflict_identifiers() -> None:
    claim = make_evidence_claims(1)[0]
    other_id = make_evidence_claims(1)[1].evidence_id

    with pytest.raises(ValidationError, match="must be unique"):
        claim.model_copy(update={"conflicting_evidence_ids": (other_id, other_id)})


def test_identity_claim_rejects_a_subject_identity_link() -> None:
    identity, affiliation = make_evidence_claims(1)[:2]

    with pytest.raises(ValidationError, match="Identity evidence cannot reference"):
        identity.model_copy(update={"subject_identity_evidence_id": affiliation.evidence_id})


def test_verification_record_rejects_an_unknown_subject_identity_link() -> None:
    singular_url = "https://profiles.example.edu/amara-ndlovu"
    identity = make_evidence_claims(1)[0].model_copy(
        update={
            "source_url": singular_url,
            "source_kind": SourceKind.UNIVERSITY_PROFILE,
        }
    )
    contextual = make_evidence_claims(1)[2].model_copy(
        update={
            "source_url": singular_url,
            "source_kind": SourceKind.UNIVERSITY_PROFILE,
            "retrieved_at": identity.retrieved_at,
            "subject_identity_evidence_id": "evidence-unknown",
        }
    )

    with pytest.raises(ValidationError, match="Subject identity evidence must exist"):
        _partial_record(evidence=(identity, contextual))


@pytest.mark.parametrize(
    "updates",
    [
        {
            "directly_supported": False,
            "source_kind": SourceKind.UNIVERSITY_PROFILE,
            "source_url": "https://profiles.example.edu/amara-ndlovu",
        },
        {
            "source_kind": SourceKind.DEPARTMENT_PAGE,
            "source_url": "https://profiles.example.edu/amara-ndlovu",
        },
        {
            "source_kind": SourceKind.UNIVERSITY_PROFILE,
            "source_url": "https://example.edu/people",
        },
    ],
)
def test_subject_identity_link_is_restricted_to_direct_official_profile_evidence(
    updates: dict[str, object],
) -> None:
    identity, _, research = make_evidence_claims(1)[:3]

    with pytest.raises(ValidationError, match="(?i)subject identity evidence|official person"):
        research.model_copy(
            update={
                **updates,
                "subject_identity_evidence_id": identity.evidence_id,
            }
        )


def test_verification_record_rejects_an_unknown_conflict_identifier() -> None:
    claim = make_evidence_claims(1)[0].model_copy(
        update={"conflicting_evidence_ids": ("evidence-unknown",)}
    )

    with pytest.raises(ValidationError, match="must exist in the record"):
        _partial_record(evidence=(claim,))


def test_verified_supervisor_rejects_an_unknown_conflict_identifier() -> None:
    verified = make_verified_supervisor(1)
    claim = verified.evidence[0].model_copy(
        update={"conflicting_evidence_ids": ("evidence-unknown",)}
    )

    with pytest.raises(ValidationError, match="must exist in the record"):
        VerifiedSupervisor.model_validate(
            {
                **verified.model_dump(mode="python"),
                "evidence": (claim, *verified.evidence[1:]),
            }
        )


def test_verification_record_accepts_a_conflict_reference_to_retained_evidence() -> None:
    first, second = make_evidence_claims(1)[:2]
    first_with_conflict = first.model_copy(
        update={"conflicting_evidence_ids": (second.evidence_id,)}
    )

    record = _partial_record(evidence=(first_with_conflict, second))

    assert record.evidence[0].conflicting_evidence_ids == (second.evidence_id,)


def test_partial_verification_cannot_contain_a_verified_supervisor() -> None:
    verified = make_verified_supervisor(1)

    with pytest.raises(ValidationError, match="cannot contain a Verified Supervisor"):
        SupervisorVerificationRecord(
            prospective_supervisor=make_prospective_supervisor(1),
            evidence=verified.evidence,
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
            availability_status=verified.availability_status,
            missing_required_evidence=("research_interest_or_publication",),
            verified_supervisor=verified,
        )


def test_partial_record_rejects_an_ungrounded_direct_claim() -> None:
    evidence = make_evidence_claims(1)
    wrong_person_research = evidence[2].model_copy(
        update={
            "asserted_name": "Dr Another Person",
            "supporting_excerpt": "Dr Another Person researches quantum biology.",
        }
    )

    with pytest.raises(ValidationError, match="must be grounded"):
        SupervisorVerificationRecord(
            prospective_supervisor=make_prospective_supervisor(1),
            evidence=(evidence[0], wrong_person_research),
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
            missing_required_evidence=(
                "current_affiliation",
                "research_interest_or_publication",
            ),
        )


def test_partial_record_requires_the_exact_deterministic_missing_evidence() -> None:
    identity = make_evidence_claims(1)[0]

    with pytest.raises(ValidationError, match="exact missing required evidence"):
        SupervisorVerificationRecord(
            prospective_supervisor=make_prospective_supervisor(1),
            evidence=(identity,),
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
            missing_required_evidence=("current_affiliation",),
        )
