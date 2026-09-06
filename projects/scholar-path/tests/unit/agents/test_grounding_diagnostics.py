"""Offline final-grounding counters must not alter evidence or disclose its content."""

import json
from collections import Counter
from collections.abc import Sequence
from typing import cast

import pytest

from scholarpath.agents.evidence_verification import (
    EvidenceGroundingDiagnostics,
    EvidenceVerificationAgent,
    StructuredEvidenceClaimDraft,
    StructuredEvidenceExtractionResult,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    GroundingFailureReason,
    SourceKind,
    evidence_claim_is_grounded_for_supervisor,
)
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import FakeEvidenceVerificationModel
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT
from tests.unit.agents.test_official_profile_evidence_context import (
    AFFILIATION_EXCERPT,
    PAGE_NAME,
    PROFILE_URL,
    _affiliation_draft,
    _identity_draft,
    _supervisor,
)

PRIVATE = "secret-token private-person@example.test https://private.example/research"
RESEARCH_EXCERPT = "Research interests: enterprise systems and responsible AI."


def _research_draft(*, directly_supported: bool = True) -> StructuredEvidenceClaimDraft:
    return StructuredEvidenceClaimDraft(
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        claim=f"The source describes research interests. {PRIVATE}",
        supporting_excerpt=RESEARCH_EXCERPT,
        confidence=EvidenceConfidence.HIGH,
        directly_supported=directly_supported,
        asserted_name=PAGE_NAME,
    )


def _extract(
    drafts: Sequence[StructuredEvidenceClaimDraft],
    page: str,
    *,
    diagnostics: EvidenceGroundingDiagnostics | None = None,
    source_kind: SourceKind = SourceKind.UNIVERSITY_PROFILE,
    source_url: str = PROFILE_URL,
) -> tuple[EvidenceVerificationAgent, tuple[EvidenceClaim, ...]]:
    response = StructuredEvidenceExtractionResult(claims=list(drafts))
    model = FakeEvidenceVerificationModel({source_url: response})
    agent = EvidenceVerificationAgent(model)
    content = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": page,
            "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
        }
    )
    claims = agent.extract_claims(_supervisor(), content, source_kind, diagnostics=diagnostics)
    assert model.call_count == 1
    return agent, claims


def _assert_accounting(
    diagnostics: EvidenceGroundingDiagnostics, claims: tuple[EvidenceClaim, ...]
) -> None:
    summary = diagnostics.summary()
    retained = Counter(claim.claim_type.value for claim in claims)
    grounded = Counter(
        claim.claim_type.value
        for claim in claims
        if evidence_claim_is_grounded_for_supervisor(claim, _supervisor(), claims)
    )
    keys = {kind.value for kind in EvidenceClaimType}
    assert set(summary["retained_claim_counts"]) == keys
    assert set(summary["grounded_claim_counts"]) == keys
    assert set(summary["rejection_counts"]) == keys
    allowed_reasons = {reason.value for reason in GroundingFailureReason}
    for kind in EvidenceClaimType:
        key = kind.value
        assert summary["retained_claim_counts"][key] == retained[key]
        assert summary["grounded_claim_counts"][key] == grounded[key]
        reasons = summary["rejection_counts"][key]
        assert set(reasons) <= allowed_reasons
        assert all(type(count) is int and count > 0 for count in reasons.values())
        assert retained[key] == grounded[key] + sum(reasons.values())


def test_successful_context_rescue_counts_final_success_and_preserves_every_claim() -> None:
    drafts = [_identity_draft(), _affiliation_draft(), _research_draft()]
    page = f"{PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{RESEARCH_EXCERPT}"
    diagnostics = EvidenceGroundingDiagnostics()

    plain_agent, plain = _extract(drafts, page)
    observed_agent, observed = _extract(drafts, page, diagnostics=diagnostics)

    assert observed == plain
    assert [claim.model_dump_json() for claim in observed] == [
        claim.model_dump_json() for claim in plain
    ]
    plain_record = plain_agent.build_verification_record(_supervisor(), plain)
    observed_record = observed_agent.build_verification_record(_supervisor(), observed)
    assert observed_record == plain_record
    assert observed_record.verified_supervisor is not None
    assert observed_record.availability_status is AvailabilityStatus.NOT_STATED
    assert all(claim.subject_identity_evidence_id for claim in observed[1:])
    assert all(not failures for failures in diagnostics.summary()["rejection_counts"].values())
    _assert_accounting(diagnostics, observed)


@pytest.mark.parametrize(
    ("identity_present", "model_supported", "expected"),
    [
        (True, False, GroundingFailureReason.MODEL_NOT_DIRECTLY_SUPPORTED),
        (False, True, GroundingFailureReason.GROUNDED_IDENTITY_MISSING),
        (False, False, GroundingFailureReason.MODEL_NOT_DIRECTLY_SUPPORTED),
    ],
)
def test_original_model_support_is_distinguished_from_missing_identity(
    identity_present: bool, model_supported: bool, expected: GroundingFailureReason
) -> None:
    drafts: list[StructuredEvidenceClaimDraft] = [_identity_draft()] if identity_present else []
    drafts.append(_research_draft(directly_supported=model_supported))
    page = f"{PAGE_NAME}\n{RESEARCH_EXCERPT}"
    diagnostics = EvidenceGroundingDiagnostics()

    _, plain = _extract(drafts, page)
    _, observed = _extract(drafts, page, diagnostics=diagnostics)

    assert observed == plain
    assert not observed[-1].directly_supported
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {expected.value: 1}
    _assert_accounting(diagnostics, observed)


@pytest.mark.parametrize(
    ("source_kind", "source_url", "heading", "institution", "department", "expected"),
    [
        (
            SourceKind.DEPARTMENT_PAGE,
            PROFILE_URL,
            PAGE_NAME,
            "University of Bradford",
            "School of Management",
            GroundingFailureReason.PROFILE_SOURCE_INELIGIBLE,
        ),
        (
            SourceKind.UNIVERSITY_PROFILE,
            "https://example.edu/people",
            PAGE_NAME,
            "University of Bradford",
            "School of Management",
            GroundingFailureReason.PROFILE_ROUTE_INELIGIBLE,
        ),
        (
            SourceKind.UNIVERSITY_PROFILE,
            PROFILE_URL,
            "Professor Alice Example",
            "University of Bradford",
            "School of Management",
            GroundingFailureReason.PROFILE_SUBJECT_MISMATCH,
        ),
        (
            SourceKind.UNIVERSITY_PROFILE,
            PROFILE_URL,
            PAGE_NAME,
            "Unstated University",
            "School of Management",
            GroundingFailureReason.INSTITUTION_NOT_IN_EXCERPT,
        ),
        (
            SourceKind.UNIVERSITY_PROFILE,
            PROFILE_URL,
            PAGE_NAME,
            "University of Bradford",
            "Unstated Department",
            GroundingFailureReason.DEPARTMENT_NOT_IN_EXCERPT,
        ),
    ],
)
def test_failed_context_rescue_records_one_final_reason_without_changing_claims(
    source_kind: SourceKind,
    source_url: str,
    heading: str,
    institution: str,
    department: str,
    expected: GroundingFailureReason,
) -> None:
    drafts = [
        _identity_draft(),
        _affiliation_draft(asserted_institution=institution, asserted_department=department),
    ]
    page = f"{PAGE_NAME}\n{heading}\n{AFFILIATION_EXCERPT}"
    diagnostics = EvidenceGroundingDiagnostics()

    _, plain = _extract(drafts, page, source_kind=source_kind, source_url=source_url)
    _, observed = _extract(
        drafts, page, diagnostics=diagnostics, source_kind=source_kind, source_url=source_url
    )

    assert observed == plain
    assert diagnostics.summary()["rejection_counts"]["current_affiliation"] == {expected.value: 1}
    assert not observed[-1].directly_supported
    _assert_accounting(diagnostics, observed)


def test_duplicate_and_unadmitted_drafts_are_not_counted_as_retained_failures() -> None:
    identity = _identity_draft()
    # A typed provider draft may be admitted structurally yet fail the stricter
    # affiliation contract. Missing fields are not a retained claim failure.
    invalid_affiliation = StructuredEvidenceClaimDraft(
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        claim="The affiliation fields are absent.",
        supporting_excerpt=AFFILIATION_EXCERPT,
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=PAGE_NAME,
    )
    absent_excerpt = _research_draft().model_copy(update={"supporting_excerpt": "Not on page."})
    drafts = [identity, identity, invalid_affiliation, absent_excerpt]
    diagnostics = EvidenceGroundingDiagnostics()

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{AFFILIATION_EXCERPT}", diagnostics=diagnostics)

    assert len(claims) == 1
    assert diagnostics.summary()["grounded_claim_counts"]["identity"] == 1
    _assert_accounting(diagnostics, claims)


def test_empty_response_has_zero_counts_and_detached_summaries() -> None:
    diagnostics = EvidenceGroundingDiagnostics()
    _, claims = _extract([], "No matching evidence.", diagnostics=diagnostics)
    _assert_accounting(diagnostics, claims)
    summary = diagnostics.summary()
    summary["retained_claim_counts"]["identity"] = 999
    summary["rejection_counts"]["identity"][PRIVATE] = 999

    assert sum(diagnostics.summary()["retained_claim_counts"].values()) == 0
    assert PRIVATE not in json.dumps(diagnostics.summary())
    assert EvidenceGroundingDiagnostics().summary() == diagnostics.summary()


def test_collector_retains_only_fixed_labels_and_counts_never_evidence_payloads() -> None:
    diagnostics = EvidenceGroundingDiagnostics()
    _, claims = _extract(
        [_identity_draft(), _research_draft(directly_supported=False)],
        f"{PAGE_NAME}\n{RESEARCH_EXCERPT}\n{PRIVATE}",
        diagnostics=diagnostics,
    )
    serialized = json.dumps(diagnostics.summary()) + repr(vars(diagnostics))

    for sensitive in (
        PRIVATE,
        PAGE_NAME,
        PROFILE_URL,
        RESEARCH_EXCERPT,
        _supervisor().supervisor_id,
    ):
        assert sensitive not in serialized
    for claim in claims:
        assert claim.evidence_id not in serialized
        assert claim.claim not in serialized
    _assert_accounting(diagnostics, claims)


@pytest.mark.parametrize("invalid_kind", [True, False])
def test_collector_rejects_raw_labels_without_echoing_them(invalid_kind: bool) -> None:
    diagnostics = EvidenceGroundingDiagnostics()
    kind = cast(EvidenceClaimType, PRIVATE) if invalid_kind else EvidenceClaimType.IDENTITY
    reason = None if invalid_kind else cast(GroundingFailureReason, PRIVATE)

    with pytest.raises(ValueError) as error:
        diagnostics.record(kind, reason)

    assert PRIVATE not in str(error.value)
    assert sum(diagnostics.summary()["retained_claim_counts"].values()) == 0


def test_collectors_do_not_share_counts_between_extractions() -> None:
    first, second = EvidenceGroundingDiagnostics(), EvidenceGroundingDiagnostics()
    _extract([_identity_draft()], PAGE_NAME, diagnostics=first)
    _extract([], "No matching evidence.", diagnostics=second)

    assert first.summary()["grounded_claim_counts"]["identity"] == 1
    assert sum(second.summary()["retained_claim_counts"].values()) == 0
