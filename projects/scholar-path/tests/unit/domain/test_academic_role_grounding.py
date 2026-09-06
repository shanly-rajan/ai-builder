"""Academic roles must not impersonate a second person in exact evidence excerpts."""

import pytest

from scholarpath.domain import (
    EvidenceClaimType,
    GroundingFailureReason,
    evidence_claim_grounding_failure,
)
from tests.unit.domain.test_grounding_failure_reasons import _claim, _supervisor


@pytest.mark.parametrize(
    "role",
    [
        "Professor Of Computer Science",
        "Professor In Information Systems",
        "Prof. Of Computer Science",
        "Professor\nIn Information Systems",
    ],
)
@pytest.mark.parametrize("contextual", [True, False])
def test_academic_role_is_not_a_second_person(role: str, contextual: bool) -> None:
    identity = _claim()
    prefix = "Current position:" if contextual else "Dr Alex Morgan is"
    excerpt = f"{prefix} {role}, Department of Computing, Example University."
    affiliation = _claim(
        evidence_id="affiliation-role",
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        supporting_excerpt=excerpt,
        asserted_institution="Example University",
        asserted_department="Department of Computing",
        subject_identity_evidence_id=identity.evidence_id if contextual else None,
    )

    assert (
        evidence_claim_grounding_failure(affiliation, _supervisor(), (identity, affiliation))
        is None
    )


@pytest.mark.parametrize(
    "other_person", ["Professor Ines Smith", "Prof Ofelia Stone", "Dr Of Computer"]
)
def test_role_prepositions_do_not_suppress_other_person_names(other_person: str) -> None:
    identity = _claim()
    affiliation = _claim(
        evidence_id="affiliation-conflict",
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        supporting_excerpt=(
            "Current position: Professor Of Computer Science, Department of Computing, "
            f"Example University; collaborating with {other_person}."
        ),
        asserted_institution="Example University",
        asserted_department="Department of Computing",
        subject_identity_evidence_id=identity.evidence_id,
    )

    assert evidence_claim_grounding_failure(
        affiliation, _supervisor(), (identity, affiliation)
    ) is (GroundingFailureReason.CONTEXT_CONFLICTING_PERSON)
