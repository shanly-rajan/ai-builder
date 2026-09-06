"""Offline subject-binding regressions, not reproductions of an unseen live page."""

from collections.abc import Sequence

import pytest

from scholarpath.agents.evidence_verification import (
    EvidenceGroundingDiagnostics,
    StructuredEvidenceClaimDraft,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    GroundingFailureReason,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationStatus,
)
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT
from tests.unit.agents.test_grounding_diagnostics import _assert_accounting, _extract
from tests.unit.agents.test_official_profile_evidence_context import (
    AFFILIATION_EXCERPT,
    PAGE_NAME,
    PROFILE_URL,
    _affiliation_draft,
    _identity_draft,
    _supervisor,
)

RESEARCH_EXCERPT = "Research interests: enterprise systems and responsible AI."
PUBLICATION_EXCERPT = "Selected publications: Responsible Enterprise Systems (2025)."


def _research_draft() -> StructuredEvidenceClaimDraft:
    return StructuredEvidenceClaimDraft(
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        claim="The profile states enterprise systems and responsible AI research.",
        supporting_excerpt=RESEARCH_EXCERPT,
        asserted_name=PAGE_NAME,
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
    )


def _assert_diagnostic_equivalence(
    drafts: Sequence[StructuredEvidenceClaimDraft],
    page: str,
    *,
    source_kind: SourceKind = SourceKind.UNIVERSITY_PROFILE,
    source_url: str = PROFILE_URL,
) -> tuple[tuple[EvidenceClaim, ...], SupervisorVerificationRecord, EvidenceGroundingDiagnostics]:
    """Both runs make exactly one fake model call and preserve source-owned values."""
    diagnostics = EvidenceGroundingDiagnostics()
    plain_agent, plain = _extract(drafts, page, source_kind=source_kind, source_url=source_url)
    agent, observed = _extract(
        drafts, page, diagnostics=diagnostics, source_kind=source_kind, source_url=source_url
    )
    assert observed == plain
    assert [claim.model_dump_json() for claim in observed] == [
        claim.model_dump_json() for claim in plain
    ]
    record = agent.build_verification_record(_supervisor(), observed)
    assert record == plain_agent.build_verification_record(_supervisor(), plain)
    assert record.availability_status is AvailabilityStatus.NOT_STATED
    for claim in observed:
        original = next(draft for draft in drafts if draft.claim_type is claim.claim_type)
        assert claim.claim == original.claim
        assert claim.supporting_excerpt == original.supporting_excerpt
        assert claim.confidence is original.confidence
        assert claim.asserted_name == original.asserted_name
        assert claim.asserted_institution == original.asserted_institution
        assert claim.asserted_department == original.asserted_department
        assert str(claim.source_url) == source_url
        assert claim.source_kind is source_kind
        assert claim.retrieved_at == FIXED_EVIDENCE_RETRIEVED_AT
        assert claim.supervisor_id == _supervisor().supervisor_id
    _assert_accounting(diagnostics, observed)
    return observed, record, diagnostics


@pytest.mark.parametrize(
    ("heading", "claim_type", "excerpt"),
    [
        ("Academic Background", EvidenceClaimType.CURRENT_AFFILIATION, AFFILIATION_EXCERPT),
        ("Research Overview", EvidenceClaimType.RESEARCH_INTEREST, RESEARCH_EXCERPT),
        ("Research Publications", EvidenceClaimType.PUBLICATION, PUBLICATION_EXCERPT),
    ],
)
def test_exact_non_person_sections_do_not_override_grounded_profile_identity(
    heading: str, claim_type: EvidenceClaimType, excerpt: str
) -> None:
    target = (
        _affiliation_draft()
        if claim_type is EvidenceClaimType.CURRENT_AFFILIATION
        else _research_draft().model_copy(
            update={
                "claim_type": claim_type,
                "claim": "The profile states research evidence.",
                "supporting_excerpt": excerpt,
            }
        )
    )
    companion = (
        _research_draft()
        if claim_type is EvidenceClaimType.CURRENT_AFFILIATION
        else _affiliation_draft()
    )
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), companion, target],
        f"# {PAGE_NAME}\n{companion.supporting_excerpt}\n## {heading}\n{excerpt}",
    )
    assert record.verified_supervisor is not None, diagnostics.summary()
    assert all(claim.directly_supported for claim in claims)
    assert claims[-1].subject_identity_evidence_id == claims[0].evidence_id
    assert diagnostics.summary()["rejection_counts"][claim_type.value] == {}


@pytest.mark.parametrize(
    "role", ["Professor Of Computer Science", "Professor In Information Systems"]
)
def test_title_cased_academic_role_is_not_a_different_person(role: str) -> None:
    excerpt = f"Current position: {role}, School of Management, University of Bradford."
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(supporting_excerpt=excerpt), _research_draft()],
        f"# {PAGE_NAME}\n{excerpt}\n{RESEARCH_EXCERPT}",
    )
    assert record.verified_supervisor is not None, diagnostics.summary()
    assert claims[1].directly_supported
    assert claims[1].subject_identity_evidence_id == claims[0].evidence_id
    assert diagnostics.summary()["rejection_counts"]["current_affiliation"] == {}


@pytest.mark.parametrize(
    "heading", ["Professor Alice Example", "Alice Example", "Alice Example, PhD"]
)
def test_actual_other_person_heading_remains_a_context_barrier(heading: str) -> None:
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), _research_draft()],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n## {heading}"
        f"\n### Research Overview\n{RESEARCH_EXCERPT}",
    )
    assert not claims[-1].directly_supported
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.PROFILE_SUBJECT_MISMATCH.value: 1
    }


@pytest.mark.parametrize(
    "role", ["Professor Of Computer Science", "Professor In Information Systems"]
)
def test_role_before_real_named_person_does_not_hide_the_person(role: str) -> None:
    excerpt = (
        f"Current position: {role}, School of Management, University of Bradford; "
        "Professor Alice Example is the current postholder."
    )
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(supporting_excerpt=excerpt), _research_draft()],
        f"# {PAGE_NAME}\n{excerpt}\n{RESEARCH_EXCERPT}",
    )
    assert not claims[1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["current_affiliation"] == {
        GroundingFailureReason.CONTEXT_CONFLICTING_PERSON.value: 1
    }


@pytest.mark.parametrize(
    "repeated", [RESEARCH_EXCERPT, "research\tinterests: Enterprise  systems and responsible AI."]
)
def test_all_equivalent_excerpt_occurrences_must_belong_to_same_person(repeated: str) -> None:
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), _research_draft()],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{RESEARCH_EXCERPT}\n## Alice Example\n{repeated}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.PROFILE_SUBJECT_MISMATCH.value: 1
    }


@pytest.mark.parametrize("heading", ["Research Overview Jones", "Academic Background Smith"])
def test_unknown_title_cased_labels_are_not_broadly_whitelisted(heading: str) -> None:
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), _research_draft()],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n## {heading}\n{RESEARCH_EXCERPT}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.PROFILE_SUBJECT_MISMATCH.value: 1
    }


@pytest.mark.parametrize(
    ("source_kind", "source_url", "expected"),
    [
        (SourceKind.DEPARTMENT_PAGE, PROFILE_URL, GroundingFailureReason.PROFILE_SOURCE_INELIGIBLE),
        (
            SourceKind.UNIVERSITY_PROFILE,
            "https://example.edu/people",
            GroundingFailureReason.PROFILE_ROUTE_INELIGIBLE,
        ),
    ],
)
def test_section_labels_do_not_make_an_ineligible_source_eligible(
    source_kind: SourceKind, source_url: str, expected: GroundingFailureReason
) -> None:
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), _research_draft()],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n## Research Overview\n{RESEARCH_EXCERPT}",
        source_kind=source_kind,
        source_url=source_url,
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {expected.value: 1}


def test_model_unsupported_research_stays_unsupported_under_a_known_section() -> None:
    draft = _research_draft().model_copy(update={"directly_supported": False})
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n## Research Overview\n{RESEARCH_EXCERPT}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.MODEL_NOT_DIRECTLY_SUPPORTED.value: 1
    }


@pytest.mark.parametrize("field", ["asserted_institution", "asserted_department"])
def test_known_section_does_not_supply_missing_required_affiliation_fields(field: str) -> None:
    affiliation = StructuredEvidenceClaimDraft.model_validate(
        {**_affiliation_draft().model_dump(), field: None}
    )
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), affiliation, _research_draft()],
        f"# {PAGE_NAME}\n## Academic Background\n{AFFILIATION_EXCERPT}\n{RESEARCH_EXCERPT}",
    )
    assert all(claim.claim_type is not EvidenceClaimType.CURRENT_AFFILIATION for claim in claims)
    assert record.verified_supervisor is None
    assert diagnostics.summary()["retained_claim_counts"]["current_affiliation"] == 0
