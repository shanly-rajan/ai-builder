"""Exact named research specialisation stays bound to one synthetic official profile."""

import pytest

from scholarpath.domain import (
    EvidenceClaimType,
    GroundingFailureReason,
    SourceKind,
    VerificationStatus,
)
from tests.unit.agents.test_role_discipline_grounding import (
    NAME,
    PROFILE_URL,
    _drafts,
    _extract_both,
)


def _research_excerpt(owner: str = "Alex Morgan", spelling: str = "specialising") -> str:
    return (
        f"{owner} is an engineer and academic {spelling} in enterprise systems and responsible AI."
    )


@pytest.mark.parametrize(
    "owner",
    [
        "Alex Morgan",
        "Professor Alex Morgan",
        "Prof. Alex Morgan",
        "Dr Alex Morgan",
        "Assistant Professor Alex Morgan",
    ],
)
@pytest.mark.parametrize("spelling", ["specialising", "specializing"])
def test_exact_named_specialisation_verifies_with_original_provenance(
    owner: str, spelling: str
) -> None:
    # The shared helper compares full outputs with diagnostics off and on, including
    # evidence IDs, links, source URL/kind, timestamp, claim wording and exact excerpts.
    claims, record, diagnostics = _extract_both(
        _drafts(research_excerpt=_research_excerpt(owner, spelling))
    )

    assert record.verification_status is VerificationStatus.VERIFIED, diagnostics.summary()
    assert record.verified_supervisor is not None
    assert not record.missing_required_evidence
    assert all(claim.directly_supported for claim in claims)
    assert claims[2].subject_identity_evidence_id == claims[0].evidence_id
    assert all(not reasons for reasons in diagnostics.summary()["rejection_counts"].values())


@pytest.mark.parametrize("asserted_name", ["Alex Morgan", "Dr Alex Morgan", "Prof. Alex Morgan"])
def test_title_equivalent_asserted_name_does_not_rewrite_research_evidence(
    asserted_name: str,
) -> None:
    drafts = _drafts(research_excerpt=_research_excerpt("Professor Alex Morgan"))
    drafts[2] = drafts[2].model_copy(update={"asserted_name": asserted_name})
    claims, record, diagnostics = _extract_both(drafts)

    assert record.verification_status is VerificationStatus.VERIFIED, diagnostics.summary()
    assert claims[2].asserted_name == asserted_name
    assert claims[2].subject_identity_evidence_id == claims[0].evidence_id


@pytest.mark.parametrize("repeat", [False, True], ids=["wrong-heading", "repeated-excerpt"])
@pytest.mark.parametrize("other_heading", ["Alice Taylor", "Professor Alice Taylor"])
def test_named_specialisation_cannot_cross_another_person_heading(
    repeat: bool, other_heading: str
) -> None:
    excerpt = _research_excerpt()
    drafts = _drafts(research_excerpt=excerpt)
    own_occurrence = f"{excerpt}\n" if repeat else ""
    page = (
        f"# {NAME}\n{drafts[1].supporting_excerpt}\n{own_occurrence}## {other_heading}\n{excerpt}"
    )
    claims, record, diagnostics = _extract_both(drafts, page=page)

    assert claims[1].directly_supported
    assert not claims[2].directly_supported
    assert claims[2].subject_identity_evidence_id is None
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("research_interest_or_publication",)
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.PROFILE_SUBJECT_MISMATCH.value: 1
    }


def test_named_specialisation_must_be_present_in_retrieved_page() -> None:
    drafts = _drafts(research_excerpt=_research_excerpt())
    page = "\n".join(draft.supporting_excerpt for draft in drafts[:2])
    claims, record, diagnostics = _extract_both(drafts, page=page)

    assert all(claim.claim_type is not EvidenceClaimType.RESEARCH_INTEREST for claim in claims)
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("research_interest_or_publication",)
    assert diagnostics.summary()["retained_claim_counts"]["research_interest"] == 0


def test_named_specialisation_does_not_supply_missing_identity() -> None:
    drafts = _drafts(research_excerpt=_research_excerpt())
    claims, record, diagnostics = _extract_both(
        drafts[1:], page="\n".join(draft.supporting_excerpt for draft in drafts)
    )

    assert all(not claim.directly_supported for claim in claims)
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.GROUNDED_IDENTITY_MISSING.value: 1
    }


def test_named_specialisation_does_not_supply_missing_affiliation() -> None:
    drafts = _drafts(research_excerpt=_research_excerpt())
    claims, record, diagnostics = _extract_both([drafts[0], drafts[2]])

    assert all(claim.directly_supported for claim in claims), diagnostics.summary()
    assert claims[1].subject_identity_evidence_id == claims[0].evidence_id
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("current_affiliation",)


def test_named_specialisation_does_not_promote_model_unsupported_research() -> None:
    drafts = _drafts(research_excerpt=_research_excerpt())
    drafts[2] = drafts[2].model_copy(update={"directly_supported": False})
    claims, record, diagnostics = _extract_both(drafts)

    assert not claims[2].directly_supported
    assert claims[2].subject_identity_evidence_id is None
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.MODEL_NOT_DIRECTLY_SUPPORTED.value: 1
    }


@pytest.mark.parametrize(
    ("source_kind", "source_url", "reason"),
    [
        (SourceKind.DEPARTMENT_PAGE, PROFILE_URL, GroundingFailureReason.PROFILE_SOURCE_INELIGIBLE),
        (SourceKind.OTHER, PROFILE_URL, GroundingFailureReason.PROFILE_SOURCE_INELIGIBLE),
        (
            SourceKind.UNIVERSITY_PROFILE,
            "https://example.edu/people",
            GroundingFailureReason.PROFILE_ROUTE_INELIGIBLE,
        ),
    ],
)
def test_named_specialisation_keeps_official_single_person_source_requirement(
    source_kind: SourceKind, source_url: str, reason: GroundingFailureReason
) -> None:
    claims, record, diagnostics = _extract_both(
        _drafts(research_excerpt=_research_excerpt()),
        source_kind=source_kind,
        source_url=source_url,
    )

    assert not claims[2].directly_supported
    assert claims[2].subject_identity_evidence_id is None
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {reason.value: 1}


@pytest.mark.parametrize(
    "owner",
    [
        "Alice Taylor",
        "Professor Alice Taylor",
        "Alex Taylor",
        "Alex Morganstown",
        "Alex Morgan Jones",
        "Alex Morgan-Jones",
        "Alex",
        "Morgan",
    ],
)
def test_named_specialisation_rejects_different_or_incomplete_owners(owner: str) -> None:
    claims, record, diagnostics = _extract_both(_drafts(research_excerpt=_research_excerpt(owner)))

    assert claims[1].directly_supported
    assert not claims[2].directly_supported
    assert claims[2].subject_identity_evidence_id is None
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("research_interest_or_publication",)
    assert sum(diagnostics.summary()["rejection_counts"]["research_interest"].values()) == 1


@pytest.mark.parametrize(
    "statement",
    [
        "is researching enterprise systems and responsible AI.",
        "is an engineer and academic.",
        "is not an engineer and academic specialising in enterprise systems.",
        "may be an engineer and academic specialising in enterprise systems.",
        "was an engineer and academic specialising in enterprise systems.",
        "is an engineer and academic specialising in .",
    ],
)
def test_named_specialisation_does_not_become_a_generic_is_bypass(statement: str) -> None:
    claims, record, diagnostics = _extract_both(
        _drafts(research_excerpt=f"Alex Morgan {statement}")
    )

    assert not claims[2].directly_supported
    assert claims[2].subject_identity_evidence_id is None
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING.value: 1
    }
