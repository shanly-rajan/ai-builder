"""Fixed draft-dataset inputs exercise the real strict verifier with a fake model."""

from collections import Counter
from dataclasses import dataclass

import pytest

from scholarpath.agents.evidence_verification import (
    EvidenceGroundingDiagnostics,
    EvidenceVerificationAgent,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    ProspectiveSupervisor,
    SourceKind,
    VerificationEvidenceStandard,
    VerificationStatus,
    evidence_claim_is_grounded_for_supervisor,
)
from scholarpath.evaluation.draft_evidence import DRAFT_EVIDENCE_CASES, apply_draft_evidence_case
from scholarpath.evaluation.fakes import ScriptedEvidenceModel, make_evaluation_evidence_outcomes
from scholarpath.graph import build_walking_skeleton_fixtures
from scholarpath.tools import ExtractedContent

_BASE_TYPES = ("identity", "current_affiliation", "research_interest", "methodology", "publication")


@dataclass(frozen=True)
class _Expected:
    case: str
    retained: tuple[str, ...] = _BASE_TYPES
    grounded: tuple[str, ...] = _BASE_TYPES
    missing: tuple[str, ...] = ()
    status: VerificationStatus = VerificationStatus.VERIFIED
    availability: AvailabilityStatus = AvailabilityStatus.NOT_STATED


# Contract checks for the synthetic variations. The explicitly identified heading
# false-negative below is an observed defect, not the dataset's intended label.
_EXPECTED = (
    _Expected(
        "confirmed_accepting",
        retained=(*_BASE_TYPES, "availability"),
        grounded=(*_BASE_TYPES, "availability"),
        availability=AvailabilityStatus.CONFIRMED_ACCEPTING,
    ),
    _Expected(
        "confirmed_not_accepting",
        retained=(*_BASE_TYPES, "availability"),
        grounded=(*_BASE_TYPES, "availability"),
        availability=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
        status=VerificationStatus.VERIFIED_WITH_CONCERNS,
    ),
    _Expected("markdown_identity"),
    _Expected("honorific_identity"),
    _Expected("line_wrapped_affiliation"),
    _Expected(
        "publication_only",
        retained=("identity", "current_affiliation", "publication"),
        grounded=("identity", "current_affiliation", "publication"),
    ),
    _Expected(
        "heading_bound_research",
        grounded=("identity", "current_affiliation", "methodology", "publication"),
    ),
    _Expected(
        "missing_identity",
        retained=("current_affiliation", "research_interest", "methodology", "publication"),
        grounded=(),
        missing=("identity", "current_affiliation", "research_interest_or_publication"),
        status=VerificationStatus.PARTIALLY_VERIFIED,
    ),
    _Expected(
        "missing_affiliation",
        retained=("identity", "research_interest", "methodology", "publication"),
        grounded=("identity", "research_interest", "methodology", "publication"),
        missing=("current_affiliation",),
        status=VerificationStatus.PARTIALLY_VERIFIED,
    ),
    _Expected(
        "missing_research",
        retained=("identity", "current_affiliation", "methodology"),
        grounded=("identity", "current_affiliation", "methodology"),
        missing=("research_interest_or_publication",),
        status=VerificationStatus.PARTIALLY_VERIFIED,
    ),
    _Expected("publication_year_not_stated"),
    _Expected("availability_without_statement", retained=(*_BASE_TYPES, "availability")),
    _Expected(
        "off_page_excerpt",
        retained=("identity", "current_affiliation", "methodology"),
        grounded=("identity", "current_affiliation", "methodology"),
        missing=("research_interest_or_publication",),
        status=VerificationStatus.PARTIALLY_VERIFIED,
    ),
)


def _baseline(
    index: int = 1,
) -> tuple[ProspectiveSupervisor, ExtractedContent, StructuredEvidenceExtractionResult]:
    fixtures = build_walking_skeleton_fixtures()
    supervisor = fixtures.raw_search_results[index - 1].to_prospective_supervisor()
    pages, responses = make_evaluation_evidence_outcomes(fixtures)
    url = str(supervisor.profile_url)
    return supervisor, pages[url], responses[url]


@pytest.mark.parametrize("index", [1, 2, 3, 4, 5, 6, 7, 8])
@pytest.mark.parametrize("expected", _EXPECTED, ids=lambda expected: expected.case)
def test_draft_evidence_cases_have_predeclared_strict_outcomes(
    expected: _Expected, index: int
) -> None:
    supervisor, page, response = _baseline(index)
    original = (supervisor.model_dump_json(), page.model_dump_json(), response.model_dump_json())
    varied_page, varied_response = apply_draft_evidence_case(
        supervisor, page, response, expected.case
    )
    model = ScriptedEvidenceModel({str(varied_page.source_url): varied_response})
    agent = EvidenceVerificationAgent(model)
    diagnostics = EvidenceGroundingDiagnostics()
    claims = agent.extract_claims(
        supervisor, varied_page, SourceKind.UNIVERSITY_PROFILE, diagnostics=diagnostics
    )
    record = agent.build_verification_record(supervisor, claims)

    assert record.verification_evidence_standard is VerificationEvidenceStandard.STRICT
    assert record.verification_status is expected.status, diagnostics.summary()
    assert record.availability_status is expected.availability
    assert record.missing_required_evidence == expected.missing
    assert (record.verified_supervisor is not None) == (not expected.missing)
    assert Counter(claim.claim_type.value for claim in claims) == Counter(expected.retained)
    assert Counter(
        claim.claim_type.value
        for claim in claims
        if evidence_claim_is_grounded_for_supervisor(claim, supervisor, claims)
    ) == Counter(expected.grounded)
    assert len(model.inputs) == 1
    # The production input schema strips only outer whitespace; source content is retained.
    assert model.inputs[0].page_content == varied_page.content.strip()
    assert varied_page.source_url == page.source_url
    assert varied_page.retrieved_at == page.retrieved_at
    for claim in claims:
        assert claim.supervisor_id == supervisor.supervisor_id
        assert claim.source_url == page.source_url
        assert claim.source_kind is SourceKind.UNIVERSITY_PROFILE
        assert claim.retrieved_at == page.retrieved_at
        assert claim.evidence_id
    assert len({claim.evidence_id for claim in claims}) == len(claims)
    assert original == (
        supervisor.model_dump_json(),
        page.model_dump_json(),
        response.model_dump_json(),
    )


def test_draft_variations_are_distinct_reproducible_and_exhaustively_tested() -> None:
    supervisor, page, response = _baseline()
    assert tuple(item.case for item in _EXPECTED) == DRAFT_EVIDENCE_CASES
    serialized = []
    for case in DRAFT_EVIDENCE_CASES:
        varied = apply_draft_evidence_case(supervisor, page, response, case)
        repeated = apply_draft_evidence_case(supervisor, page, response, case)
        payload = tuple(item.model_dump_json() for item in varied)
        assert payload == tuple(item.model_dump_json() for item in repeated)
        serialized.append(payload)
    assert len(set(serialized)) == 13


@pytest.mark.parametrize("case", ["availability_without_statement", "off_page_excerpt"])
def test_adversarial_variations_are_valid_model_contracts_with_false_factual_support(
    case: str,
) -> None:
    supervisor, page, response = _baseline()
    varied_page, varied_response = apply_draft_evidence_case(supervisor, page, response, case)
    assert varied_page == page
    for claim in varied_response.claims:
        StructuredEvidenceClaim.model_validate(claim.model_dump(mode="python"))
        assert claim.directly_supported
        assert claim.asserted_name == supervisor.full_name
    if case == "off_page_excerpt":
        for claim in varied_response.claims:
            if claim.claim_type in {
                EvidenceClaimType.RESEARCH_INTEREST,
                EvidenceClaimType.PUBLICATION,
            }:
                assert claim.supporting_excerpt not in varied_page.content
    else:
        availability = varied_response.claims[-1]
        assert availability.claim_type is EvidenceClaimType.AVAILABILITY
        assert availability.supporting_excerpt in varied_page.content
        assert "accepting" not in varied_page.content


def test_undated_publication_does_not_invent_an_activity_year() -> None:
    supervisor, page, response = _baseline()
    varied_page, varied_response = apply_draft_evidence_case(
        supervisor, page, response, "publication_year_not_stated"
    )
    model = ScriptedEvidenceModel({str(page.source_url): varied_response})
    claims = EvidenceVerificationAgent(model).extract_claims(
        supervisor, varied_page, SourceKind.UNIVERSITY_PROFILE
    )
    publication = next(
        claim for claim in claims if claim.claim_type is EvidenceClaimType.PUBLICATION
    )
    assert publication.directly_supported
    assert publication.activity_year is None
    assert "2025" not in varied_page.content


def test_heading_bound_research_preserves_the_observed_false_negative() -> None:
    supervisor, page, response = _baseline()
    varied_page, varied_response = apply_draft_evidence_case(
        supervisor, page, response, "heading_bound_research"
    )
    model = ScriptedEvidenceModel({str(page.source_url): varied_response})
    diagnostics = EvidenceGroundingDiagnostics()
    claims = EvidenceVerificationAgent(model).extract_claims(
        supervisor, varied_page, SourceKind.UNIVERSITY_PROFILE, diagnostics=diagnostics
    )
    identity = next(claim for claim in claims if claim.claim_type is EvidenceClaimType.IDENTITY)
    research = next(
        claim for claim in claims if claim.claim_type is EvidenceClaimType.RESEARCH_INTEREST
    )
    # The named affiliation sentence is mistaken for another person heading. Do
    # not rearrange this legitimate fixture to get green: its draft dataset label
    # still requires grounded research and should fail expected_behavior today.
    assert identity.directly_supported
    assert varied_page.content.startswith(f"# {supervisor.full_name}\n")
    assert not research.directly_supported
    assert research.subject_identity_evidence_id is None
    assert research.supporting_excerpt is not None
    assert supervisor.full_name not in research.supporting_excerpt
    assert research.supporting_excerpt in varied_page.content
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        "profile_subject_mismatch": 1
    }


@pytest.mark.parametrize("case", ["", "not_a_case", "confirmed_accepting "])
def test_unknown_draft_case_is_rejected_without_changing_inputs(case: str) -> None:
    supervisor, page, response = _baseline()
    with pytest.raises(ValueError, match="Unknown draft evidence case"):
        apply_draft_evidence_case(supervisor, page, response, case)


def test_draft_variations_refuse_real_source_urls() -> None:
    supervisor, page, response = _baseline()
    other_page = ExtractedContent.model_validate(
        {**page.model_dump(mode="python"), "source_url": "https://university.edu/people/alex"}
    )
    with pytest.raises(ValueError, match="matching synthetic profile URL"):
        apply_draft_evidence_case(supervisor, other_page, response, "markdown_identity")


def test_draft_variations_refuse_another_supervisor() -> None:
    supervisor, page, response = _baseline()
    other = supervisor.model_copy(update={"full_name": "Professor Alex Morgan"})
    with pytest.raises(ValueError, match="matching synthetic Supervisor"):
        apply_draft_evidence_case(other, page, response, "markdown_identity")
