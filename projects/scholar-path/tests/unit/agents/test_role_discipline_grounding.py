"""Synthetic, offline regressions for complete academic role/discipline labels."""

from collections import Counter
from collections.abc import Sequence

import pytest
from pydantic import ValidationError

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
    SupervisorVerificationRecord,
    VerificationEvidenceStandard,
    VerificationStatus,
    evidence_claim_is_grounded_for_supervisor,
)
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import FakeEvidenceVerificationModel
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT, make_prospective_supervisor

NAME = "Professor Alex Morgan"
INSTITUTION = "Example University"
DEPARTMENT = "School of Computing"
PROFILE_URL = "https://example.edu/people/alex-morgan"
RESEARCH_EXCERPT = "Research interests: enterprise systems and responsible AI."


def _drafts(
    role: str = "Prof Computer Science", *, research_excerpt: str = RESEARCH_EXCERPT
) -> list[StructuredEvidenceClaimDraft]:
    affiliation = f"Current position: {role}, {DEPARTMENT}, {INSTITUTION}."
    return [
        StructuredEvidenceClaimDraft(
            claim_type=EvidenceClaimType.IDENTITY,
            claim=f"The official profile identifies {NAME}.",
            supporting_excerpt=NAME,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=NAME,
        ),
        StructuredEvidenceClaimDraft(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The profile states the Supervisor's current affiliation.",
            supporting_excerpt=affiliation,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=NAME,
            asserted_institution=INSTITUTION,
            asserted_department=DEPARTMENT,
        ),
        StructuredEvidenceClaimDraft(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states enterprise systems and responsible AI research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=NAME,
        ),
    ]


def _extract_both(
    drafts: Sequence[StructuredEvidenceClaimDraft],
    *,
    page: str | None = None,
    source_url: str = PROFILE_URL,
    source_kind: SourceKind = SourceKind.UNIVERSITY_PROFILE,
) -> tuple[tuple[EvidenceClaim, ...], SupervisorVerificationRecord, EvidenceGroundingDiagnostics]:
    supervisor = make_prospective_supervisor(
        1,
        full_name=NAME,
        institution=INSTITUTION,
        department=DEPARTMENT,
        profile_url=PROFILE_URL,
    )
    content = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": page or "\n".join(draft.supporting_excerpt for draft in drafts),
            "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
        }
    )
    diagnostics = EvidenceGroundingDiagnostics()
    outputs = []
    for collector in (None, diagnostics):
        model = FakeEvidenceVerificationModel(
            {source_url: StructuredEvidenceExtractionResult(claims=list(drafts))}
        )
        agent = EvidenceVerificationAgent(model)
        claims = agent.extract_claims(supervisor, content, source_kind, diagnostics=collector)
        record = agent.build_verification_record(supervisor, claims)
        assert model.call_count == 1
        assert record.verification_evidence_standard is VerificationEvidenceStandard.STRICT
        assert record.availability_status is AvailabilityStatus.NOT_STATED
        assert len({claim.evidence_id for claim in claims}) == len(claims)
        for claim in claims:
            draft = next(draft for draft in drafts if draft.claim_type is claim.claim_type)
            assert claim.supporting_excerpt == draft.supporting_excerpt
            assert claim.claim == draft.claim
            assert claim.asserted_name == draft.asserted_name
            assert claim.asserted_institution == draft.asserted_institution
            assert claim.asserted_department == draft.asserted_department
            assert claim.confidence is draft.confidence
            assert claim.supervisor_id == supervisor.supervisor_id
            assert str(claim.source_url) == source_url
            assert claim.source_kind is source_kind
            assert claim.retrieved_at == FIXED_EVIDENCE_RETRIEVED_AT
            assert claim.evidence_id
        outputs.append(
            (tuple(claim.model_dump_json() for claim in claims), record.model_dump_json())
        )
    # Includes exact evidence identifiers and subject-identity links, not just statuses.
    assert outputs[0] == outputs[1]
    retained = Counter(claim.claim_type.value for claim in claims)
    grounded = Counter(
        claim.claim_type.value
        for claim in claims
        if evidence_claim_is_grounded_for_supervisor(claim, supervisor, claims)
    )
    summary = diagnostics.summary()
    for kind in EvidenceClaimType:
        key = kind.value
        assert summary["retained_claim_counts"][key] == retained[key]
        assert summary["grounded_claim_counts"][key] == grounded[key]
        assert retained[key] == grounded[key] + sum(summary["rejection_counts"][key].values())
    return claims, record, diagnostics


@pytest.mark.parametrize(
    "role", ["Prof Computer Science", "Prof. Computer Science", "Professor Computer Science"]
)
def test_complete_role_label_with_supported_research_verifies_strictly(role: str) -> None:
    claims, record, diagnostics = _extract_both(_drafts(role))

    assert record.verification_status is VerificationStatus.VERIFIED, diagnostics.summary()
    assert record.verified_supervisor is not None
    assert all(claim.directly_supported for claim in claims)
    assert all(claim.subject_identity_evidence_id == claims[0].evidence_id for claim in claims[1:])
    assert not record.missing_required_evidence
    assert all(not reasons for reasons in diagnostics.summary()["rejection_counts"].values())


@pytest.mark.parametrize("role", ["Prof Computer Science", "Professor Computer Science"])
def test_role_does_not_hide_a_later_real_other_person(role: str) -> None:
    drafts = _drafts(role)
    drafts[1] = drafts[1].model_copy(
        update={
            "supporting_excerpt": drafts[1].supporting_excerpt
            + " Professor Alice Taylor is the current postholder."
        }
    )
    claims, record, diagnostics = _extract_both(drafts)

    assert not claims[1].directly_supported
    assert claims[1].subject_identity_evidence_id is None
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["current_affiliation"] == {
        GroundingFailureReason.CONTEXT_CONFLICTING_PERSON.value: 1
    }


def test_role_label_does_not_replace_missing_identity_evidence() -> None:
    drafts = _drafts()
    claims, record, diagnostics = _extract_both(
        drafts[1:], page="\n".join(draft.supporting_excerpt for draft in drafts)
    )

    assert all(not claim.directly_supported for claim in claims)
    assert record.verified_supervisor is None
    for kind in ("current_affiliation", "research_interest"):
        assert diagnostics.summary()["rejection_counts"][kind] == {
            GroundingFailureReason.GROUNDED_IDENTITY_MISSING.value: 1
        }


@pytest.mark.parametrize("field", ["asserted_name", "asserted_institution", "asserted_department"])
def test_role_label_does_not_supply_missing_typed_affiliation_fields(field: str) -> None:
    drafts = _drafts()
    drafts[1] = StructuredEvidenceClaimDraft.model_validate({**drafts[1].model_dump(), field: None})
    claims, record, diagnostics = _extract_both(drafts)

    assert all(claim.claim_type is not EvidenceClaimType.CURRENT_AFFILIATION for claim in claims)
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert diagnostics.summary()["retained_claim_counts"]["current_affiliation"] == 0


@pytest.mark.parametrize(
    ("source_kind", "source_url", "reason"),
    [
        (SourceKind.DEPARTMENT_PAGE, PROFILE_URL, GroundingFailureReason.PROFILE_SOURCE_INELIGIBLE),
        (
            SourceKind.UNIVERSITY_PROFILE,
            "https://example.edu/people",
            GroundingFailureReason.PROFILE_ROUTE_INELIGIBLE,
        ),
    ],
)
def test_role_label_does_not_relax_source_eligibility(
    source_kind: SourceKind, source_url: str, reason: GroundingFailureReason
) -> None:
    claims, record, diagnostics = _extract_both(
        _drafts(), source_kind=source_kind, source_url=source_url
    )

    assert not claims[1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["current_affiliation"] == {reason.value: 1}


@pytest.mark.parametrize("position", [1, 2], ids=["affiliation", "research"])
def test_role_label_does_not_promote_model_unsupported_claims(position: int) -> None:
    drafts = _drafts()
    drafts[position] = drafts[position].model_copy(update={"directly_supported": False})
    claims, record, diagnostics = _extract_both(drafts)

    assert not claims[position].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"][drafts[position].claim_type.value] == {
        GroundingFailureReason.MODEL_NOT_DIRECTLY_SUPPORTED.value: 1
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("source_url", "https://example.edu/people/alex-morgan/biography"),
        ("source_kind", SourceKind.INSTITUTIONAL_DIRECTORY),
    ],
)
def test_verified_role_label_still_requires_identity_from_the_same_source(
    field: str, value: str
) -> None:
    claims, original, _ = _extract_both(_drafts())
    identity = EvidenceClaim.model_validate({**claims[0].model_dump(), field: value})
    mismatched_evidence = (identity, *claims[1:])
    model = FakeEvidenceVerificationModel({})

    assert original.verified_supervisor is not None
    with pytest.raises(
        ValidationError, match="Directly supported verification-record claims must be grounded"
    ):
        EvidenceVerificationAgent(model).build_verification_record(
            original.prospective_supervisor, mismatched_evidence
        )
    assert model.call_count == 0


def test_affiliation_repair_does_not_relax_named_owner_is_research_grammar() -> None:
    drafts = _drafts(
        research_excerpt=f"{NAME} is researching enterprise systems and responsible AI."
    )
    claims, record, diagnostics = _extract_both(drafts)

    assert claims[1].directly_supported, diagnostics.summary()
    assert claims[1].subject_identity_evidence_id == claims[0].evidence_id
    assert not claims[2].directly_supported
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("research_interest_or_publication",)
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING.value: 1
    }
