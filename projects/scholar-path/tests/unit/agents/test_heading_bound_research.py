"""Named owner role sentences must not masquerade as different person headings."""

import pytest

from scholarpath.agents.evidence_verification import (
    EvidenceVerificationAgent,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    SourceKind,
    VerificationStatus,
    evidence_claim_is_grounded_for_supervisor,
)
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import FakeEvidenceVerificationModel
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT, make_prospective_supervisor

_NAME = "Dr Amara Ndlovu"
_URL = "https://example.edu/people/amara-ndlovu"
_ROLE = (
    "Dr Amara Ndlovu is Associate Professor in the Department of Information Systems at "
    "Southern Cape Institute of Technology."
)
_RESEARCH = "Research interests: enterprise architecture and responsible AI governance."


def _extract(
    page: str,
    *,
    directly_supported: bool = True,
    source_kind: SourceKind = SourceKind.UNIVERSITY_PROFILE,
    source_url: str = _URL,
    include_affiliation: bool = False,
    include_identity: bool = True,
) -> tuple[EvidenceVerificationAgent, tuple[EvidenceClaim, ...]]:
    supervisor = make_prospective_supervisor(1)
    drafts = [
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.IDENTITY,
            claim=f"The profile identifies {_NAME}.",
            supporting_excerpt=_NAME,
            asserted_name=_NAME,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
        ),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states enterprise architecture and responsible AI research.",
            supporting_excerpt=_RESEARCH,
            asserted_name=_NAME,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=directly_supported,
        ),
    ]
    if include_affiliation:
        drafts.append(
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim="The profile states the current institution and department.",
                supporting_excerpt=_ROLE,
                asserted_name=_NAME,
                asserted_institution=supervisor.institution,
                asserted_department=supervisor.department,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
            )
        )
    response = StructuredEvidenceExtractionResult.model_validate(
        {
            "claims": [
                draft
                for draft in drafts
                if include_identity or draft.claim_type is not EvidenceClaimType.IDENTITY
            ]
        }
    )
    response_before = response.model_dump_json()
    model = FakeEvidenceVerificationModel({source_url: response})
    agent = EvidenceVerificationAgent(model)
    content = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": page,
            "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
        }
    )

    claims = agent.extract_claims(supervisor, content, source_kind)

    assert model.call_count == 1
    assert model.inputs[0].page_content == page
    assert str(model.inputs[0].source_url) == source_url
    assert response.model_dump_json() == response_before
    return agent, claims


def _research_claim(claims: tuple[EvidenceClaim, ...]) -> EvidenceClaim:
    return next(item for item in claims if item.claim_type is EvidenceClaimType.RESEARCH_INTEREST)


def test_owner_affiliation_sentence_preserves_strict_verification_and_provenance() -> None:
    page = f"# {_NAME}\n\n{_ROLE}\n\n## Research interests\n{_RESEARCH}"

    agent, claims = _extract(page, include_affiliation=True)

    research = _research_claim(claims)
    identity = next(item for item in claims if item.claim_type is EvidenceClaimType.IDENTITY)
    supervisor = make_prospective_supervisor(1)
    assert research.directly_supported is True
    assert research.supporting_excerpt == _RESEARCH
    assert research.subject_identity_evidence_id == identity.evidence_id
    assert str(research.source_url) == str(identity.source_url) == _URL
    assert research.source_kind is SourceKind.UNIVERSITY_PROFILE
    assert research.retrieved_at == FIXED_EVIDENCE_RETRIEVED_AT
    assert research.supervisor_id == identity.supervisor_id == supervisor.supervisor_id
    assert evidence_claim_is_grounded_for_supervisor(research, supervisor, claims)
    record = agent.build_verification_record(supervisor, claims)
    assert record.verification_status is VerificationStatus.VERIFIED
    assert record.missing_required_evidence == ()
    assert record.availability_status is AvailabilityStatus.NOT_STATED
    assert record.verified_supervisor is not None
    assert record.verified_supervisor.evidence == claims
    _, replayed = _extract(page, include_affiliation=True)
    assert replayed == claims


@pytest.mark.parametrize(
    "role_sentence",
    [
        "Professor Amara Ndlovu is Professor in the Department of Information Systems.",
        "Dr Amara Ndlovu is a Professor of Information Systems.",
        "Dr Amara Ndlovu is an Assistant Professor at Southern Cape Institute of Technology.",
        "Dr Amara Ndlovu is an Adjunct Professor in Information Systems.",
    ],
)
def test_bounded_owner_role_variants_preserve_heading_binding(role_sentence: str) -> None:
    _, claims = _extract(f"# {_NAME}\n{role_sentence}\n## Research interests\n{_RESEARCH}")

    research = _research_claim(claims)
    identity = next(item for item in claims if item.claim_type is EvidenceClaimType.IDENTITY)
    assert research.directly_supported is True
    assert research.subject_identity_evidence_id == identity.evidence_id
    assert research.supporting_excerpt == _RESEARCH


@pytest.mark.parametrize(
    "intervening_lines",
    [
        f"## Professor Elias Hart\n{_ROLE}",
        "Professor Elias Hart is Professor in Information Systems.",
        f"{_ROLE}\nDr Elias Hart is an Assistant Professor at Northbridge University.",
        "Dr Amara Ndlovu works with external researchers.",
        f"{_ROLE.rstrip('.')}; Professor Alice Morgan studies software testing.",
        f"{_ROLE} Alice Morgan is Professor in Computer Science.",
        f"{_ROLE.rstrip('.')} and Professor Alice Morgan studies software testing.",
        f"{_ROLE.rstrip('.')} while Alice Morgan is Professor in Computer Science.",
        f"## {_ROLE}",
        "Dr Amara Ndlovus is Professor in Information Systems.",
        "Dr Amara Ndlovu Smith is Professor in Information Systems.",
    ],
)
def test_owner_role_sentence_does_not_remove_existing_person_boundaries(
    intervening_lines: str,
) -> None:
    _, claims = _extract(f"# {_NAME}\n{intervening_lines}\n{_RESEARCH}")

    research = _research_claim(claims)
    assert research.directly_supported is False
    assert research.subject_identity_evidence_id is None
    assert research.supporting_excerpt == _RESEARCH
    assert not evidence_claim_is_grounded_for_supervisor(
        research, make_prospective_supervisor(1), claims
    )


def test_repeated_excerpt_under_another_person_is_not_bound_to_owner() -> None:
    page = f"# {_NAME}\n{_ROLE}\n{_RESEARCH}\n## Professor Elias Hart\n{_ROLE}\n{_RESEARCH}"

    _, claims = _extract(page)

    assert _research_claim(claims).directly_supported is False
    assert _research_claim(claims).subject_identity_evidence_id is None


def test_excerpt_absent_from_page_is_not_retained_even_with_owner_role_sentence() -> None:
    _, claims = _extract(f"# {_NAME}\n{_ROLE}\nResearch interests: software testing.")

    assert all(item.claim_type is not EvidenceClaimType.RESEARCH_INTEREST for item in claims)


def test_model_unsupported_claim_is_not_promoted_by_owner_context() -> None:
    _, claims = _extract(f"# {_NAME}\n{_ROLE}\n{_RESEARCH}", directly_supported=False)

    research = _research_claim(claims)
    assert research.directly_supported is False
    assert research.subject_identity_evidence_id is None


def test_owner_heading_and_role_cannot_replace_missing_identity_evidence() -> None:
    _, claims = _extract(f"# {_NAME}\n{_ROLE}\n{_RESEARCH}", include_identity=False)

    assert all(item.claim_type is not EvidenceClaimType.IDENTITY for item in claims)
    research = _research_claim(claims)
    assert research.directly_supported is False
    assert research.subject_identity_evidence_id is None


@pytest.mark.parametrize(
    ("source_kind", "source_url"),
    [
        (SourceKind.DEPARTMENT_PAGE, _URL),
        (SourceKind.PUBLICATION, _URL),
        (SourceKind.INSTITUTIONAL_DIRECTORY, "https://example.edu/people"),
    ],
)
def test_owner_role_sentence_does_not_bypass_source_or_route_requirements(
    source_kind: SourceKind, source_url: str
) -> None:
    _, claims = _extract(
        f"# {_NAME}\n{_ROLE}\n{_RESEARCH}",
        source_kind=source_kind,
        source_url=source_url,
    )

    research = _research_claim(claims)
    assert research.directly_supported is False
    assert research.subject_identity_evidence_id is None
    assert str(research.source_url) == source_url
