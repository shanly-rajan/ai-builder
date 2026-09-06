"""Context diagnostics refine labels without changing offline extraction decisions."""

import json
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

PRIVATE = "context-secret-token private-context@example.test https://private.example/context"
CONFLICTING_EXCERPT = (
    "Research interests: enterprise systems; Professor Alice Example researches governance."
)
UNBOUND_EXCERPT = "enterprise systems and responsible AI are studied."


def _context_draft(
    excerpt: str,
    *,
    claim_type: EvidenceClaimType = EvidenceClaimType.RESEARCH_INTEREST,
    directly_supported: bool = True,
    availability_status: AvailabilityStatus | None = None,
) -> StructuredEvidenceClaimDraft:
    return StructuredEvidenceClaimDraft(
        claim_type=claim_type,
        claim=f"The profile states the extracted fact. {PRIVATE}",
        supporting_excerpt=excerpt,
        confidence=EvidenceConfidence.HIGH,
        directly_supported=directly_supported,
        asserted_name=PAGE_NAME,
        availability_status=availability_status,
    )


def _assert_equivalent_extraction(
    drafts: Sequence[StructuredEvidenceClaimDraft],
) -> tuple[tuple[EvidenceClaim, ...], SupervisorVerificationRecord, EvidenceGroundingDiagnostics]:
    """Each run makes one fake call; diagnostics preserve exact source-owned fields."""
    page = "\n".join((f"# {PAGE_NAME}", *(draft.supporting_excerpt for draft in drafts), PRIVATE))
    diagnostics = EvidenceGroundingDiagnostics()
    plain_agent, plain = _extract(drafts, page)
    observed_agent, observed = _extract(drafts, page, diagnostics=diagnostics)

    assert observed == plain
    assert [claim.model_dump_json() for claim in observed] == [
        claim.model_dump_json() for claim in plain
    ]
    record = observed_agent.build_verification_record(_supervisor(), observed)
    assert record == plain_agent.build_verification_record(_supervisor(), plain)
    for draft, claim in zip(drafts, observed, strict=True):
        for field in StructuredEvidenceClaimDraft.model_fields:
            if field != "directly_supported":
                assert getattr(claim, field) == getattr(draft, field)
        assert claim.supervisor_id == _supervisor().supervisor_id
        assert str(claim.source_url) == PROFILE_URL
        assert claim.source_kind is SourceKind.UNIVERSITY_PROFILE
        assert claim.retrieved_at == FIXED_EVIDENCE_RETRIEVED_AT

    summary = diagnostics.summary()
    assert set(summary) == {"retained_claim_counts", "grounded_claim_counts", "rejection_counts"}
    _assert_accounting(diagnostics, observed)
    serialized = json.dumps(summary) + repr(vars(diagnostics))
    for private_value in (PRIVATE, PAGE_NAME, PROFILE_URL, _supervisor().supervisor_id, page):
        assert private_value not in serialized
    for claim in observed:
        assert claim.evidence_id not in serialized
        assert claim.claim not in serialized
        assert claim.supporting_excerpt is not None
        assert claim.supporting_excerpt not in serialized
    assert GroundingFailureReason.PROFILE_IDENTITY_CONTEXT_INVALID.value not in serialized
    return observed, record, diagnostics


@pytest.mark.parametrize(
    ("claim_type", "excerpt"),
    [
        (EvidenceClaimType.RESEARCH_INTEREST, "Research interests: responsible AI governance."),
        (EvidenceClaimType.RESEARCH_INTEREST, "I study responsible AI governance."),
        (EvidenceClaimType.METHODOLOGY, "My work uses design science research."),
        (EvidenceClaimType.PUBLICATION, "Selected publications: Responsible AI Systems (2025)."),
        (EvidenceClaimType.PROJECT, "Current projects: responsible enterprise systems."),
    ],
)
def test_supported_context_patterns_keep_exact_evidence_and_zero_rejections(
    claim_type: EvidenceClaimType, excerpt: str
) -> None:
    drafts = [
        _identity_draft(),
        _affiliation_draft(),
        _context_draft(excerpt, claim_type=claim_type),
    ]

    claims, _, diagnostics = _assert_equivalent_extraction(drafts)

    assert all(claim.directly_supported for claim in claims)
    assert claims[-1].subject_identity_evidence_id == claims[0].evidence_id
    assert all(not reasons for reasons in diagnostics.summary()["rejection_counts"].values())


@pytest.mark.parametrize(
    ("excerpt", "reason"),
    [
        (CONFLICTING_EXCERPT, GroundingFailureReason.CONTEXT_CONFLICTING_PERSON),
        (UNBOUND_EXCERPT, GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING),
    ],
)
def test_rejected_context_has_one_precise_final_reason_and_unchanged_verification(
    excerpt: str, reason: GroundingFailureReason
) -> None:
    claims, record, diagnostics = _assert_equivalent_extraction(
        [_identity_draft(), _affiliation_draft(), _context_draft(excerpt)]
    )

    assert not claims[-1].directly_supported
    assert claims[-1].subject_identity_evidence_id is None
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("research_interest_or_publication",)
    assert record.availability_status is AvailabilityStatus.NOT_STATED
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {reason.value: 1}


@pytest.mark.parametrize("excerpt", [CONFLICTING_EXCERPT, UNBOUND_EXCERPT])
def test_original_unsupported_flag_precedes_context_rejection(excerpt: str) -> None:
    claims, record, diagnostics = _assert_equivalent_extraction(
        [
            _identity_draft(),
            _affiliation_draft(),
            _context_draft(excerpt, directly_supported=False),
        ]
    )

    assert not claims[-1].directly_supported
    assert claims[-1].subject_identity_evidence_id is None
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.MODEL_NOT_DIRECTLY_SUPPORTED.value: 1
    }


@pytest.mark.parametrize("conflicting_person", [False, True])
def test_affiliation_bypasses_subject_prefix_but_still_rejects_conflicting_person(
    conflicting_person: bool,
) -> None:
    excerpt = "Based at University of Bradford in the School of Management."
    if conflicting_person:
        excerpt += " Professor Alice Example is the current postholder."
    claims, record, diagnostics = _assert_equivalent_extraction(
        [
            _identity_draft(),
            _affiliation_draft(supporting_excerpt=excerpt),
            _context_draft("Research interests: responsible AI governance."),
        ]
    )

    affiliation = claims[1]
    assert affiliation.directly_supported is not conflicting_person
    assert affiliation.subject_identity_evidence_id == (
        None if conflicting_person else claims[0].evidence_id
    )
    assert (record.verified_supervisor is None) is conflicting_person
    assert diagnostics.summary()["rejection_counts"]["current_affiliation"] == (
        {GroundingFailureReason.CONTEXT_CONFLICTING_PERSON.value: 1} if conflicting_person else {}
    )


@pytest.mark.parametrize(
    ("excerpt", "expected"),
    [
        ("I am not accepting new doctoral Candidates.", None),
        (
            "I am currently accepting new doctoral Candidates.",
            GroundingFailureReason.AVAILABILITY_POLARITY_NOT_SUPPORTED,
        ),
    ],
)
def test_availability_polarity_is_separate_from_valid_context_subject(
    excerpt: str, expected: GroundingFailureReason | None
) -> None:
    claims, record, diagnostics = _assert_equivalent_extraction(
        [
            _identity_draft(),
            _affiliation_draft(supporting_excerpt=AFFILIATION_EXCERPT),
            _context_draft("Research interests: responsible AI governance."),
            _context_draft(
                excerpt,
                claim_type=EvidenceClaimType.AVAILABILITY,
                availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
            ),
        ]
    )

    assert claims[-1].directly_supported is (expected is None)
    assert record.verified_supervisor is not None
    assert record.availability_status is (
        AvailabilityStatus.CONFIRMED_NOT_ACCEPTING
        if expected is None
        else AvailabilityStatus.NOT_STATED
    )
    assert diagnostics.summary()["rejection_counts"]["availability"] == (
        {} if expected is None else {expected.value: 1}
    )
