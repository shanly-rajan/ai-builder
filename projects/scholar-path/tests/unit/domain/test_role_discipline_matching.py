"""Synthetic role labels must not hide real people or establish missing evidence."""

import pytest

from scholarpath.domain import (
    EvidenceClaimType,
    GroundingFailureReason,
    evidence_claim_grounding_failure,
)
from scholarpath.evaluation.grounding_replay import (
    RejectedExcerptCapture,
    replay_details,
    replay_snapshot,
)
from tests.unit.domain.test_grounding_failure_reasons import _claim, _supervisor

ROLE = "Professor Computer Science"
AFFILIATION = "Department of Computing, Example University."


@pytest.mark.parametrize(
    "role",
    [ROLE, "Prof. Computer Science", "Prof Computer Science", "Professor\tComputer\u00a0Science"],
)
@pytest.mark.parametrize("contextual", [True, False])
def test_complete_discipline_role_label_is_not_a_conflicting_person(
    role: str, contextual: bool
) -> None:
    identity = _claim()
    prefix = "Current position:" if contextual else "Dr Alex Morgan is"
    excerpt = f"{prefix} {role}, {AFFILIATION}"
    affiliation = _claim(
        evidence_id="role-affiliation",
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        supporting_excerpt=excerpt,
        asserted_institution="Example University",
        asserted_department="Department of Computing",
        subject_identity_evidence_id=identity.evidence_id if contextual else None,
    )
    assert evidence_claim_grounding_failure(affiliation, _supervisor(), (identity,)) is None
    assert affiliation.supporting_excerpt == excerpt


@pytest.mark.parametrize(
    "other_person",
    [
        "Professor Computer Science Morgan",
        "Professor Computer Sciences",
        "Dr Computer Science",
        "Professor Jane Computer Science",
        "Professor Alice Example",
        "Dr Alex Morgan Smith",
        pytest.param("Professor Computer Science\nMorgan", id="lf-name-extension"),
        pytest.param("Professor Computer Science\r\nMorgan", id="crlf-name-extension"),
        pytest.param("Professor Computer Science van\nMorgan", id="lf-particle-extension"),
        pytest.param("Professor Computer Science van \r\nMorgan", id="crlf-particle-extension"),
        pytest.param("Professor\nComputer Science", id="wrapped-title"),
        pytest.param("Professor Computer\nScience", id="wrapped-name"),
    ],
)
@pytest.mark.parametrize("contextual", [True, False])
@pytest.mark.parametrize("other_first", [True, False])
def test_exact_role_exception_does_not_hide_other_or_extended_names(
    other_person: str, contextual: bool, other_first: bool
) -> None:
    identity = _claim()
    prefix = "Current position:" if contextual else "Dr Alex Morgan is"
    body = (
        f"working with {other_person}; {ROLE}"
        if other_first
        else f"{ROLE}; working with {other_person}"
    )
    affiliation = _claim(
        evidence_id="role-conflict",
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        supporting_excerpt=f"{prefix} {body}, {AFFILIATION}",
        asserted_institution="Example University",
        asserted_department="Department of Computing",
        subject_identity_evidence_id=identity.evidence_id if contextual else None,
    )
    expected = (
        GroundingFailureReason.CONTEXT_CONFLICTING_PERSON
        if contextual
        else GroundingFailureReason.SUBJECT_NOT_ESTABLISHED
    )
    assert evidence_claim_grounding_failure(affiliation, _supervisor(), (identity,)) is expected


@pytest.mark.parametrize("field", ["asserted_institution", "asserted_department"])
def test_accepted_role_does_not_replace_required_affiliation_fields(field: str) -> None:
    identity = _claim()
    updates = {
        "evidence_id": "role-missing-field",
        "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
        "supporting_excerpt": f"Current position: {ROLE}, {AFFILIATION}",
        "asserted_institution": "Example University",
        "asserted_department": "Department of Computing",
        "subject_identity_evidence_id": identity.evidence_id,
        field: None,
    }
    affiliation = _claim(**updates)
    assert evidence_claim_grounding_failure(affiliation, _supervisor(), (identity,)) is (
        GroundingFailureReason.AFFILIATION_FIELDS_MISSING
    )


@pytest.mark.parametrize("other_person", [None, "Dr Alice Example"])
def test_private_replay_details_share_the_role_filter(other_person: str | None) -> None:
    excerpt = f"Current position: {ROLE}, {AFFILIATION}"
    if other_person:
        excerpt += f" Working with {other_person}."
    capture = RejectedExcerptCapture()
    capture.observe(
        expected_name=_supervisor().full_name,
        claim=_claim(
            evidence_id="historical-role-affiliation",
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            supporting_excerpt=excerpt,
        ),
        failure=GroundingFailureReason.CONTEXT_CONFLICTING_PERSON,
    )
    snapshot = capture.snapshot()
    assert len(snapshot.samples) == 1
    detail = replay_details(snapshot)[0]
    summary = replay_snapshot(snapshot)
    if other_person:
        assert detail.current_reason is GroundingFailureReason.CONTEXT_CONFLICTING_PERSON
        assert detail.matcher_family == "titled_person"
        assert detail.matched_text == other_person
        assert summary.matched_count == 1
    else:
        assert detail.current_reason is None
        assert detail.matcher_family is None
        assert detail.matched_text is None
        assert summary.changed_count == 1
    assert snapshot.samples[0].supporting_excerpt == excerpt
