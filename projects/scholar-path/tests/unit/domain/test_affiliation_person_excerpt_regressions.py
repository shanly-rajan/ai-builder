"""Fixed official-profile excerpts distinguish complete owners from other people."""

import pytest

from scholarpath.domain import (
    EvidenceClaim,
    EvidenceClaimType,
    GroundingFailureReason,
    ProspectiveSupervisor,
    evidence_claim_grounding_failure,
    evidence_claim_is_grounded_for_supervisor,
)
from tests.unit.domain.test_grounding_failure_reasons import _claim, _supervisor

_AFFILIATION = "Department of Computing, Example University."


def _affiliation_case(
    owner_name: str, excerpt: str
) -> tuple[ProspectiveSupervisor, EvidenceClaim, tuple[EvidenceClaim, ...]]:
    """Keep the fixture's singular source URL and fixed retrieval provenance."""
    supervisor = _supervisor().model_copy(update={"full_name": owner_name})
    identity = _claim(asserted_name=owner_name, supporting_excerpt=owner_name)
    affiliation = _claim(
        evidence_id="affiliation-person-excerpt",
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        asserted_name=owner_name,
        supporting_excerpt=excerpt,
        asserted_institution="Example University",
        asserted_department="Department of Computing",
        subject_identity_evidence_id=identity.evidence_id,
    )
    assert evidence_claim_is_grounded_for_supervisor(identity, supervisor) is True
    return supervisor, affiliation, (identity, affiliation)


@pytest.mark.parametrize(
    "owner_name",
    [
        pytest.param("Dr Alex Morgan", id="two-name-dr-control"),
        pytest.param("Professor Alex Morgan", id="two-name-professor-control"),
        pytest.param("Dr Alex James Morgan", id="three-name-dr"),
        pytest.param("Professor Alex James Morgan", id="three-name-professor"),
        pytest.param("Prof. Alex James Morgan", id="three-name-abbreviated-title"),
        pytest.param("Professor Alex James Thomas Morgan", id="four-name-professor"),
        pytest.param("Dr Alex James van Morgan", id="middle-name-surname-particle"),
        pytest.param("Dr Anne-Marie Jane O’Connor", id="hyphen-and-apostrophe"),
    ],
)
def test_complete_profile_owner_is_not_an_affiliation_person_conflict(owner_name: str) -> None:
    supervisor, affiliation, evidence = _affiliation_case(
        owner_name,
        f"Current position: {owner_name} is in the {_AFFILIATION}",
    )

    assert evidence_claim_grounding_failure(affiliation, supervisor, evidence) is None
    assert evidence_claim_is_grounded_for_supervisor(affiliation, supervisor, evidence) is True


@pytest.mark.parametrize(
    "separator", [pytest.param("\t", id="tab"), pytest.param("\u00a0", id="nbsp")]
)
def test_horizontal_name_whitespace_keeps_complete_owner_grounded(separator: str) -> None:
    owner_name = "Professor Alex James Morgan"
    displayed_name = separator.join(owner_name.split())
    supervisor, affiliation, evidence = _affiliation_case(
        owner_name,
        f"Current position: {displayed_name} is in the {_AFFILIATION}",
    )

    assert evidence_claim_grounding_failure(affiliation, supervisor, evidence) is None
    assert evidence_claim_is_grounded_for_supervisor(affiliation, supervisor, evidence) is True


def test_complete_owner_name_does_not_consume_the_next_section_heading() -> None:
    owner_name = "Professor Alex James Morgan"
    supervisor, affiliation, evidence = _affiliation_case(
        owner_name,
        f"{owner_name}\nCurrent Position: {_AFFILIATION}",
    )

    assert evidence_claim_grounding_failure(affiliation, supervisor, evidence) is None
    assert evidence_claim_is_grounded_for_supervisor(affiliation, supervisor, evidence) is True


def test_complete_long_owner_also_grounds_a_direct_affiliation_subject() -> None:
    owner_name = "Professor Alex James Morgan"
    supervisor, affiliation, _ = _affiliation_case(
        owner_name,
        f"{owner_name} is in the {_AFFILIATION}",
    )
    direct = affiliation.model_copy(update={"subject_identity_evidence_id": None})

    assert evidence_claim_grounding_failure(direct, supervisor) is None
    assert evidence_claim_is_grounded_for_supervisor(direct, supervisor) is True


def test_complete_owner_name_does_not_match_a_supervisor_with_a_missing_middle_name() -> None:
    owner_name = "Professor Alex James Morgan"
    supervisor, affiliation, evidence = _affiliation_case(
        owner_name,
        f"Current position: {owner_name} is in the {_AFFILIATION}",
    )
    other_supervisor = supervisor.model_copy(update={"full_name": "Professor Alex Morgan"})

    assert evidence_claim_grounding_failure(affiliation, other_supervisor, evidence) is (
        GroundingFailureReason.SUPERVISOR_NAME_MISMATCH
    )
    assert (
        evidence_claim_is_grounded_for_supervisor(affiliation, other_supervisor, evidence) is False
    )


@pytest.mark.parametrize(
    ("owner_name", "person_statement"),
    [
        pytest.param(
            "Professor Alex James Morgan",
            "Current position: Professor Alex James Taylor is in the",
            id="titled-other-shares-given-names",
        ),
        pytest.param(
            "Professor Alex James Morgan",
            "Current position: Professor Alex James is in the",
            id="truncated-owner-is-a-different-complete-name",
        ),
        pytest.param(
            "Professor Alex Morgan",
            "Current position: Professor Alex Morgan Smith is in the",
            id="other-person-extends-complete-owner-name",
        ),
        pytest.param(
            "Dr Alex Morgan",
            "Current position: Dr Jane Smith is in the",
            id="titled-unrelated-person",
        ),
        pytest.param(
            "Dr Alex Morgan",
            "Current position: Dr Jane\nSmith is in the",
            id="titled-unrelated-person-wrapped-name",
        ),
        pytest.param(
            "Dr Alex James Morgan",
            "Current position: Alex James Taylor is in the",
            id="untitled-other-shares-given-names",
        ),
        pytest.param(
            "Dr Alex James Morgan",
            "Alex James Taylor —",
            id="untitled-other-heading",
        ),
        pytest.param(
            "Professor Alex James Morgan",
            "Current position: Professor Alex James Morgan works with Dr Jane Smith in the",
            id="complete-owner-followed-by-titled-other",
        ),
        pytest.param(
            "Professor Alex James Morgan",
            "Dr Jane Smith works with Professor Alex James Morgan in the",
            id="titled-other-followed-by-complete-owner",
        ),
        pytest.param(
            "Professor Alex James Morgan",
            "Professor Alex James Morgan\nCurrent position: Alex James Taylor is in the",
            id="complete-owner-followed-by-untitled-other",
        ),
    ],
)
def test_other_people_still_reject_contextual_affiliation(
    owner_name: str, person_statement: str
) -> None:
    supervisor, affiliation, evidence = _affiliation_case(
        owner_name,
        f"{person_statement} {_AFFILIATION}",
    )

    assert evidence_claim_grounding_failure(affiliation, supervisor, evidence) is (
        GroundingFailureReason.CONTEXT_CONFLICTING_PERSON
    )
    assert evidence_claim_is_grounded_for_supervisor(affiliation, supervisor, evidence) is False
