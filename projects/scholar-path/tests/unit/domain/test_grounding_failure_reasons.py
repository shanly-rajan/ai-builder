"""Fixed examples for first-failure grounding reasons without new evidence rules."""

from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    GroundingFailureReason,
    ProspectiveSupervisor,
    SourceKind,
    evidence_claim_grounding_failure,
    evidence_claim_is_grounded_for_supervisor,
)
from scholarpath.domain import models as domain_models
from tests.fixtures import make_evidence_claims, make_prospective_supervisor

_PROFILE_URL = "https://example.edu/people/alex-morgan"
_NAME = "Dr Alex Morgan"


def _supervisor() -> ProspectiveSupervisor:
    return make_prospective_supervisor(
        1,
        full_name=_NAME,
        institution="Example University",
        department="Department of Computing",
        profile_url=_PROFILE_URL,
    )


def _claim(**updates: object) -> EvidenceClaim:
    """Build valid defaults, then deliberately bypass validation for negative cases."""
    base = EvidenceClaim(
        evidence_id="evidence-identity",
        supervisor_id=_supervisor().supervisor_id,
        claim_type=EvidenceClaimType.IDENTITY,
        claim="The official profile identifies the Supervisor.",
        source_url=HttpUrl(_PROFILE_URL),
        source_kind=SourceKind.UNIVERSITY_PROFILE,
        retrieved_at=datetime(2026, 8, 1, tzinfo=UTC),
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=_NAME,
        supporting_excerpt=_NAME,
    )
    return EvidenceClaim.model_construct(**{**base.model_dump(mode="python"), **updates})


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"directly_supported": False}, GroundingFailureReason.NOT_DIRECTLY_SUPPORTED),
        ({"supervisor_id": "another-supervisor"}, GroundingFailureReason.SUPERVISOR_ID_MISMATCH),
        ({"asserted_name": None}, GroundingFailureReason.ASSERTED_NAME_MISSING),
        ({"supporting_excerpt": None}, GroundingFailureReason.SUPPORTING_EXCERPT_MISSING),
        ({"asserted_name": "Dr Different Person"}, GroundingFailureReason.SUPERVISOR_NAME_MISMATCH),
        (
            {"supporting_excerpt": "This is a generic university profile."},
            GroundingFailureReason.IDENTITY_NAME_NOT_IN_EXCERPT,
        ),
        (
            {
                "claim_type": EvidenceClaimType.RESEARCH_INTEREST,
                "supporting_excerpt": f"{_NAME} researches secure systems.",
                "subject_identity_evidence_id": "missing-identity",
            },
            GroundingFailureReason.CONTEXT_IDENTITY_NOT_FOUND,
        ),
        (
            {
                "claim_type": EvidenceClaimType.RESEARCH_INTEREST,
                "supporting_excerpt": f"Research at this university includes {_NAME}.",
            },
            GroundingFailureReason.SUBJECT_NOT_ESTABLISHED,
        ),
        (
            {
                "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
                "supporting_excerpt": f"{_NAME} is at Example University.",
            },
            GroundingFailureReason.AFFILIATION_FIELDS_MISSING,
        ),
        (
            {
                "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
                "supporting_excerpt": f"{_NAME} is in the Department of Computing.",
                "asserted_institution": "Example University",
                "asserted_department": "Department of Computing",
            },
            GroundingFailureReason.INSTITUTION_NOT_IN_EXCERPT,
        ),
        (
            {
                "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
                "supporting_excerpt": f"{_NAME} is at Example University.",
                "asserted_institution": "Example University",
                "asserted_department": "Department of Computing",
            },
            GroundingFailureReason.DEPARTMENT_NOT_IN_EXCERPT,
        ),
        (
            {
                "claim_type": EvidenceClaimType.AVAILABILITY,
                "supporting_excerpt": (
                    f"{_NAME} is not accepting new postgraduate research students."
                ),
                "availability_status": AvailabilityStatus.CONFIRMED_ACCEPTING,
            },
            GroundingFailureReason.AVAILABILITY_POLARITY_NOT_SUPPORTED,
        ),
    ],
)
def test_each_existing_grounding_failure_has_a_fixed_reason(
    updates: dict[str, object], reason: GroundingFailureReason
) -> None:
    claim = _claim(**updates)

    assert evidence_claim_grounding_failure(claim, _supervisor()) is reason
    assert evidence_claim_is_grounded_for_supervisor(claim, _supervisor()) is False


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        (
            {
                "directly_supported": False,
                "supervisor_id": "another-supervisor",
                "asserted_name": None,
                "supporting_excerpt": None,
            },
            GroundingFailureReason.NOT_DIRECTLY_SUPPORTED,
        ),
        (
            {"supervisor_id": "another-supervisor", "asserted_name": None},
            GroundingFailureReason.SUPERVISOR_ID_MISMATCH,
        ),
        (
            {"asserted_name": None, "supporting_excerpt": None},
            GroundingFailureReason.ASSERTED_NAME_MISSING,
        ),
        (
            {"asserted_name": "Dr Different Person", "supporting_excerpt": None},
            GroundingFailureReason.SUPPORTING_EXCERPT_MISSING,
        ),
        (
            {
                "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
                "asserted_name": "Dr Different Person",
                "supporting_excerpt": "No relevant statement.",
            },
            GroundingFailureReason.SUPERVISOR_NAME_MISMATCH,
        ),
        (
            {
                "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
                "supporting_excerpt": "No named subject or typed affiliation fields.",
            },
            GroundingFailureReason.SUBJECT_NOT_ESTABLISHED,
        ),
        (
            {
                "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
                "supporting_excerpt": f"{_NAME} is a researcher.",
                "asserted_institution": "Example University",
                "asserted_department": "Department of Computing",
            },
            GroundingFailureReason.INSTITUTION_NOT_IN_EXCERPT,
        ),
    ],
)
def test_multiple_failures_report_only_the_first_existing_check(
    updates: dict[str, object], reason: GroundingFailureReason
) -> None:
    assert evidence_claim_grounding_failure(_claim(**updates), _supervisor()) is reason


@pytest.mark.parametrize("index", range(1, 7))
def test_preexisting_fixture_claims_keep_their_grounding_outcome(index: int) -> None:
    supervisor = make_prospective_supervisor(index)
    evidence = make_evidence_claims(index)

    for claim in evidence:
        expected = (
            None if claim.directly_supported else GroundingFailureReason.NOT_DIRECTLY_SUPPORTED
        )
        assert evidence_claim_grounding_failure(claim, supervisor, evidence) is expected
        assert evidence_claim_is_grounded_for_supervisor(claim, supervisor, evidence) is (
            claim.directly_supported
        )


@pytest.mark.parametrize(
    "updates",
    [
        {
            "claim_type": EvidenceClaimType.RESEARCH_INTEREST,
            "supporting_excerpt": "Research interests: secure systems.",
        },
        {
            "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
            "supporting_excerpt": (
                "Current position: Professor, Department of Computing, Example University."
            ),
            "asserted_institution": "Example University",
            "asserted_department": "Department of Computing",
        },
        {
            "claim_type": EvidenceClaimType.AVAILABILITY,
            "supporting_excerpt": "I am accepting new postgraduate research students.",
            "availability_status": AvailabilityStatus.CONFIRMED_ACCEPTING,
        },
    ],
)
def test_valid_official_profile_context_keeps_the_claim_grounded(
    updates: dict[str, object],
) -> None:
    identity = _claim()
    contextual = _claim(
        **updates,
        evidence_id="contextual-evidence",
        subject_identity_evidence_id=identity.evidence_id,
    )
    evidence = (identity, contextual)

    assert evidence_claim_grounding_failure(contextual, _supervisor(), evidence) is None
    assert evidence_claim_is_grounded_for_supervisor(contextual, _supervisor(), evidence) is True


@pytest.mark.parametrize(
    ("identity_updates", "reason"),
    [
        (
            {"directly_supported": False},
            GroundingFailureReason.CONTEXT_IDENTITY_NOT_DIRECTLY_SUPPORTED,
        ),
        (
            {"supervisor_id": "another-supervisor"},
            GroundingFailureReason.CONTEXT_SUPERVISOR_ID_MISMATCH,
        ),
        (
            {"asserted_name": "Dr Different Person"},
            GroundingFailureReason.CONTEXT_IDENTITY_NAME_NOT_IN_EXCERPT,
        ),
        (
            {"supporting_excerpt": "A profile with no name."},
            GroundingFailureReason.CONTEXT_IDENTITY_NAME_NOT_IN_EXCERPT,
        ),
        ({"source_kind": SourceKind.OTHER}, GroundingFailureReason.CONTEXT_SOURCE_KIND_MISMATCH),
    ],
)
def test_invalid_profile_context_is_not_hidden_by_a_direct_subject(
    identity_updates: dict[str, object],
    reason: GroundingFailureReason,
) -> None:
    identity = _claim(**identity_updates)
    contextual = _claim(
        evidence_id="contextual-research",
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        supporting_excerpt=f"{_NAME} researches secure systems.",
        subject_identity_evidence_id=identity.evidence_id,
    )
    evidence = (identity, contextual)

    assert evidence_claim_grounding_failure(contextual, _supervisor(), evidence) is reason
    assert evidence_claim_is_grounded_for_supervisor(contextual, _supervisor(), evidence) is False


def test_contextual_availability_still_requires_matching_explicit_polarity() -> None:
    identity = _claim()
    contextual = _claim(
        evidence_id="contextual-availability",
        claim_type=EvidenceClaimType.AVAILABILITY,
        supporting_excerpt="I am not accepting new postgraduate research students.",
        availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        subject_identity_evidence_id=identity.evidence_id,
    )

    assert evidence_claim_grounding_failure(contextual, _supervisor(), (identity,)) is (
        GroundingFailureReason.AVAILABILITY_POLARITY_NOT_SUPPORTED
    )


@pytest.mark.parametrize("reason", [None, GroundingFailureReason.SUPERVISOR_NAME_MISMATCH])
def test_boolean_api_delegates_to_the_shared_reason_predicate(
    monkeypatch: pytest.MonkeyPatch, reason: GroundingFailureReason | None
) -> None:
    calls: list[tuple[EvidenceClaim, ProspectiveSupervisor, tuple[EvidenceClaim, ...]]] = []

    def fake_grounding_failure(
        claim: EvidenceClaim,
        supervisor: ProspectiveSupervisor,
        evidence: tuple[EvidenceClaim, ...] = (),
    ) -> GroundingFailureReason | None:
        calls.append((claim, supervisor, evidence))
        return reason

    monkeypatch.setattr(domain_models, "evidence_claim_grounding_failure", fake_grounding_failure)
    claim = _claim()
    supervisor = _supervisor()
    evidence = (claim,)

    assert evidence_claim_is_grounded_for_supervisor(claim, supervisor, evidence) is (
        reason is None
    )
    assert calls == [(claim, supervisor, evidence)]
