"""Offline unit tests for grounded Supervisor evidence verification."""

import pytest
from pydantic import ValidationError

from scholarpath.agents.evidence_verification import (
    EvidenceModelOutputError,
    EvidenceVerificationAgent,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
    deterministic_evidence_id,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationStatus,
)
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    make_complete_evidence_response,
)
from tests.fixtures import (
    ACCEPTING_PROFILE_URL,
    ALTERNATE_OFFICIAL_PROFILE_URL,
    COMPLETE_PROFILE_URL,
    CONFLICTING_AFFILIATION_URL,
    FIXED_EVIDENCE_RETRIEVED_AT,
    MISSING_AFFILIATION_URL,
    MISSING_RESEARCH_URL,
    NOT_ACCEPTING_PROFILE_URL,
    make_prospective_supervisor,
)


def _extract_claims(
    source_url: str,
    *,
    source_kind: SourceKind = SourceKind.UNIVERSITY_PROFILE,
    content_extraction: FakeContentExtraction | None = None,
    model: FakeEvidenceVerificationModel | None = None,
) -> tuple[
    EvidenceVerificationAgent,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    tuple[EvidenceClaim, ...],
]:
    resolved_content_extraction = content_extraction or FakeContentExtraction()
    resolved_model = model or FakeEvidenceVerificationModel()
    agent = EvidenceVerificationAgent(resolved_model)
    content = resolved_content_extraction.extract(source_url)
    claims = agent.extract_claims(
        make_prospective_supervisor(1),
        content,
        source_kind,
    )
    return agent, resolved_content_extraction, resolved_model, claims


def test_complete_official_profile_produces_a_verified_supervisor() -> None:
    agent, content_extraction, model, claims = _extract_claims(COMPLETE_PROFILE_URL)

    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert content_extraction.calls == [COMPLETE_PROFILE_URL]
    assert model.call_count == 1
    assert {claim.claim_type for claim in claims} == {
        EvidenceClaimType.IDENTITY,
        EvidenceClaimType.CURRENT_AFFILIATION,
        EvidenceClaimType.RESEARCH_INTEREST,
        EvidenceClaimType.PUBLICATION,
        EvidenceClaimType.PROJECT,
    }
    assert record.verification_status is VerificationStatus.VERIFIED
    assert record.verified_supervisor is not None
    assert record.missing_required_evidence == ()
    assert record.availability_status is AvailabilityStatus.NOT_STATED


def test_missing_affiliation_remains_partial_without_using_discovery_data_as_evidence() -> None:
    agent, _, _, claims = _extract_claims(MISSING_AFFILIATION_URL)

    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert all(claim.claim_type is not EvidenceClaimType.CURRENT_AFFILIATION for claim in claims)
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == (EvidenceClaimType.CURRENT_AFFILIATION.value,)
    assert record.prospective_supervisor.institution == "Southern Cape Institute of Technology"


def test_missing_research_evidence_remains_partial() -> None:
    agent, _, _, claims = _extract_claims(
        MISSING_RESEARCH_URL, source_kind=SourceKind.DEPARTMENT_PAGE
    )

    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert {claim.claim_type for claim in claims} == {
        EvidenceClaimType.IDENTITY,
        EvidenceClaimType.CURRENT_AFFILIATION,
    }
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("research_interest_or_publication",)
    assert SupervisorVerificationRecord.model_validate_json(record.model_dump_json()) == record


def test_unstated_availability_remains_not_stated_and_does_not_block_verification() -> None:
    agent, _, _, claims = _extract_claims(COMPLETE_PROFILE_URL)

    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert all(claim.claim_type is not EvidenceClaimType.AVAILABILITY for claim in claims)
    assert record.availability_status is AvailabilityStatus.NOT_STATED
    assert record.verified_supervisor is not None


@pytest.mark.parametrize(
    ("source_url", "expected_status"),
    [
        (ACCEPTING_PROFILE_URL, AvailabilityStatus.CONFIRMED_ACCEPTING),
        (NOT_ACCEPTING_PROFILE_URL, AvailabilityStatus.CONFIRMED_NOT_ACCEPTING),
    ],
)
def test_explicit_availability_is_preserved_only_when_directly_stated(
    source_url: str,
    expected_status: AvailabilityStatus,
) -> None:
    agent, _, _, claims = _extract_claims(source_url)

    record = agent.build_verification_record(make_prospective_supervisor(1), claims)
    availability_claims = tuple(
        claim for claim in claims if claim.claim_type is EvidenceClaimType.AVAILABILITY
    )

    assert len(availability_claims) == 1
    assert availability_claims[0].directly_supported is True
    assert availability_claims[0].availability_status is expected_status
    assert record.availability_status is expected_status
    assert record.verified_supervisor is not None


def test_conflicting_affiliations_are_retained_linked_and_surfaced() -> None:
    agent, _, model, primary_claims = _extract_claims(COMPLETE_PROFILE_URL)
    alternate_content = FakeContentExtraction().extract(CONFLICTING_AFFILIATION_URL)
    alternate_claims = agent.extract_claims(
        make_prospective_supervisor(1),
        alternate_content,
        SourceKind.INSTITUTIONAL_DIRECTORY,
    )

    record = agent.build_verification_record(
        make_prospective_supervisor(1),
        (*primary_claims, *alternate_claims),
    )
    affiliation_claims = tuple(
        claim
        for claim in record.evidence
        if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
    )

    assert model.call_count == 2
    assert len(affiliation_claims) == 2
    assert {claim.asserted_institution for claim in affiliation_claims} == {
        "Southern Cape Institute of Technology",
        "Northbridge University",
    }
    assert {str(claim.source_url) for claim in affiliation_claims} == {
        COMPLETE_PROFILE_URL,
        CONFLICTING_AFFILIATION_URL,
    }
    first, second = affiliation_claims
    assert first.conflicting_evidence_ids == (second.evidence_id,)
    assert second.conflicting_evidence_ids == (first.evidence_id,)
    assert record.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS
    assert record.verified_supervisor is not None
    assert record.verified_supervisor.institution == "Southern Cape Institute of Technology"
    assert any("conflict" in concern.casefold() for concern in record.verification_concerns)


def test_same_claim_prose_with_different_affiliations_is_retained_and_cross_linked() -> None:
    source_url = "https://profiles.example.edu/amara-ndlovu"
    supervisor = make_prospective_supervisor(1)
    first_excerpt = (
        "Dr Amara Ndlovu is Professor in the Department of Information Systems at "
        "Southern Cape Institute of Technology."
    )
    second_excerpt = (
        "Dr Amara Ndlovu is Visiting Professor in the School of Computing and Strategy at "
        "Northbridge University."
    )
    shared_prose = "The official page states the Supervisor's current affiliation."
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.IDENTITY,
                claim="The official page identifies Dr Amara Ndlovu.",
                supporting_excerpt="Dr Amara Ndlovu",
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim=shared_prose,
                supporting_excerpt=first_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
                asserted_institution="Southern Cape Institute of Technology",
                asserted_department="Department of Information Systems",
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim=shared_prose,
                supporting_excerpt=second_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
                asserted_institution="Northbridge University",
                asserted_department="School of Computing and Strategy",
            ),
        ]
    )
    content = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": f"Dr Amara Ndlovu\n{first_excerpt}\n{second_excerpt}",
            "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
        }
    )
    agent = EvidenceVerificationAgent(FakeEvidenceVerificationModel({source_url: response}))

    claims = agent.extract_claims(supervisor, content, SourceKind.UNIVERSITY_PROFILE)
    record = agent.build_verification_record(supervisor, claims)
    affiliations = tuple(
        claim
        for claim in record.evidence
        if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
    )

    assert len(affiliations) == 2
    assert len({claim.evidence_id for claim in affiliations}) == 2
    first, second = affiliations
    assert first.claim == second.claim == shared_prose
    assert first.conflicting_evidence_ids == (second.evidence_id,)
    assert second.conflicting_evidence_ids == (first.evidence_id,)


def test_merge_rejects_same_identifier_for_semantically_distinct_claims() -> None:
    _, _, _, claims = _extract_claims(COMPLETE_PROFILE_URL)
    affiliation = next(
        claim for claim in claims if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
    )
    colliding = affiliation.model_copy(
        update={
            "asserted_institution": "Northbridge University",
            "asserted_department": "School of Computing and Strategy",
        }
    )

    with pytest.raises(EvidenceModelOutputError, match="Distinct evidence claims"):
        EvidenceVerificationAgent(FakeEvidenceVerificationModel()).build_verification_record(
            make_prospective_supervisor(1),
            (*claims, colliding),
        )


def test_evidence_identifier_changes_with_grounded_source_and_classification() -> None:
    draft = StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
        claim="The official page states the Supervisor's current affiliation.",
        supporting_excerpt=(
            "Dr Amara Ndlovu is Professor at Southern Cape Institute of Technology."
        ),
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name="Dr Amara Ndlovu",
        asserted_institution="Southern Cape Institute of Technology",
        asserted_department="Department of Information Systems",
    )

    def evidence_id(
        value: StructuredEvidenceClaim = draft,
        *,
        source_url: str = COMPLETE_PROFILE_URL,
        source_kind: SourceKind = SourceKind.UNIVERSITY_PROFILE,
        directly_supported: bool = True,
    ) -> str:
        return deterministic_evidence_id(
            "supervisor-001",
            source_url,
            source_kind,
            value,
            directly_supported=directly_supported,
        )

    identifiers = {
        evidence_id(),
        evidence_id(source_url=CONFLICTING_AFFILIATION_URL),
        evidence_id(source_kind=SourceKind.INSTITUTIONAL_DIRECTORY),
        evidence_id(directly_supported=False),
        evidence_id(draft.model_copy(update={"confidence": EvidenceConfidence.MEDIUM})),
        evidence_id(
            draft.model_copy(
                update={
                    "supporting_excerpt": "Dr Amara Ndlovu is Professor at Northbridge University.",
                    "asserted_institution": "Northbridge University",
                }
            )
        ),
    }

    assert len(identifiers) == 6


def test_evidence_identifier_includes_typed_availability_status() -> None:
    accepting = StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.AVAILABILITY,
        claim="The page states the current doctoral supervision availability.",
        supporting_excerpt="Dr Amara Ndlovu is currently accepting doctoral Candidates.",
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        asserted_name="Dr Amara Ndlovu",
    )
    not_accepting = accepting.model_copy(
        update={"availability_status": AvailabilityStatus.CONFIRMED_NOT_ACCEPTING}
    )

    accepting_id = deterministic_evidence_id(
        "supervisor-001",
        COMPLETE_PROFILE_URL,
        SourceKind.UNIVERSITY_PROFILE,
        accepting,
        directly_supported=True,
    )
    not_accepting_id = deterministic_evidence_id(
        "supervisor-001",
        COMPLETE_PROFILE_URL,
        SourceKind.UNIVERSITY_PROFILE,
        not_accepting,
        directly_supported=True,
    )

    assert accepting_id != not_accepting_id


def test_claim_without_an_exact_page_grounding_excerpt_is_rejected() -> None:
    ungrounded_response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.RESEARCH_INTEREST,
                claim="The page allegedly states a research interest that is not present.",
                supporting_excerpt="This sentence does not occur in the retrieved page.",
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
            )
        ]
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: ungrounded_response})
    content = FakeContentExtraction().extract(COMPLETE_PROFILE_URL)

    with pytest.raises(EvidenceModelOutputError, match="not grounded"):
        EvidenceVerificationAgent(model).extract_claims(
            make_prospective_supervisor(1),
            content,
            SourceKind.UNIVERSITY_PROFILE,
        )


def test_model_cannot_make_a_mismatched_identity_directly_supported() -> None:
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.IDENTITY,
                claim="The page names Dr Amara Ndlovu.",
                supporting_excerpt="Dr Amara Ndlovu",
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Another Person",
            )
        ]
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    content = FakeContentExtraction().extract(COMPLETE_PROFILE_URL)
    agent = EvidenceVerificationAgent(model)

    claims = agent.extract_claims(
        make_prospective_supervisor(1),
        content,
        SourceKind.UNIVERSITY_PROFILE,
    )
    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert claims[0].directly_supported is False
    assert EvidenceClaimType.IDENTITY.value in record.missing_required_evidence
    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED


def test_page_without_matching_identity_cannot_contribute_research_evidence() -> None:
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.IDENTITY,
                claim="The model attaches the page to a different person.",
                supporting_excerpt="Dr Amara Ndlovu",
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Professor Bongani Ndlovu",
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.RESEARCH_INTEREST,
                claim="The page states enterprise architecture research interests.",
                supporting_excerpt=(
                    "Dr Amara Ndlovu's stated research interests are enterprise architecture, "
                    "responsible AI governance, and resilient digital transformation."
                ),
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
            ),
        ]
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    content = FakeContentExtraction().extract(COMPLETE_PROFILE_URL)
    agent = EvidenceVerificationAgent(model)

    claims = agent.extract_claims(
        make_prospective_supervisor(1),
        content,
        SourceKind.UNIVERSITY_PROFILE,
    )
    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert all(claim.directly_supported is False for claim in claims)
    assert record.missing_required_evidence == (
        "identity",
        "current_affiliation",
        "research_interest_or_publication",
    )


def test_matching_page_identity_cannot_bind_another_persons_research_or_availability() -> None:
    wrong_research = (
        "Dr Other Person researches enterprise architecture and responsible AI governance."
    )
    wrong_availability = (
        "Dr Other Person is currently accepting doctoral Candidates for the 2027 intake."
    )
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.IDENTITY,
                claim="The page identifies Dr Amara Ndlovu.",
                supporting_excerpt="Dr Amara Ndlovu",
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.RESEARCH_INTEREST,
                claim="The page states enterprise architecture research interests.",
                supporting_excerpt=wrong_research,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Other Person",
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.AVAILABILITY,
                claim="The page states that a person is accepting doctoral Candidates.",
                supporting_excerpt=wrong_availability,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
                asserted_name="Dr Other Person",
            ),
        ]
    )
    content = (
        FakeContentExtraction()
        .extract(COMPLETE_PROFILE_URL)
        .model_copy(update={"content": f"Dr Amara Ndlovu\n{wrong_research}\n{wrong_availability}"})
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    agent = EvidenceVerificationAgent(model)

    claims = agent.extract_claims(
        make_prospective_supervisor(1),
        content,
        SourceKind.UNIVERSITY_PROFILE,
    )
    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert claims[0].directly_supported is True
    assert all(claim.directly_supported is False for claim in claims[1:])
    assert record.availability_status is AvailabilityStatus.NOT_STATED
    assert "research_interest_or_publication" in record.missing_required_evidence


def test_model_cannot_invert_explicit_availability_polarity() -> None:
    availability_excerpt = (
        "Dr Amara Ndlovu is not accepting new doctoral Candidates for the 2027 intake."
    )
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.IDENTITY,
                claim="The page identifies Dr Amara Ndlovu.",
                supporting_excerpt="Dr Amara Ndlovu",
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.AVAILABILITY,
                claim="The model incorrectly labels a negative statement as accepting.",
                supporting_excerpt=availability_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
                asserted_name="Dr Amara Ndlovu",
            ),
        ]
    )
    content = (
        FakeContentExtraction()
        .extract(COMPLETE_PROFILE_URL)
        .model_copy(update={"content": f"Dr Amara Ndlovu\n{availability_excerpt}"})
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    agent = EvidenceVerificationAgent(model)

    claims = agent.extract_claims(
        make_prospective_supervisor(1),
        content,
        SourceKind.UNIVERSITY_PROFILE,
    )
    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    availability = next(
        claim for claim in claims if claim.claim_type is EvidenceClaimType.AVAILABILITY
    )
    assert availability.directly_supported is False
    assert record.availability_status is AvailabilityStatus.NOT_STATED


def test_typed_affiliation_values_must_be_grounded_in_the_exact_excerpt() -> None:
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim="The model asserts an institution absent from the excerpt.",
                supporting_excerpt=(
                    "Dr Amara Ndlovu is Associate Professor in the Department of "
                    "Information Systems at Southern Cape Institute of Technology."
                ),
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Amara Ndlovu",
                asserted_institution="Invented University",
                asserted_department="Department of Information Systems",
            )
        ]
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    content = FakeContentExtraction().extract(COMPLETE_PROFILE_URL)
    agent = EvidenceVerificationAgent(model)

    claims = agent.extract_claims(
        make_prospective_supervisor(1),
        content,
        SourceKind.UNIVERSITY_PROFILE,
    )
    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert claims[0].directly_supported is False
    assert EvidenceClaimType.CURRENT_AFFILIATION.value in record.missing_required_evidence


def test_affiliation_about_a_different_person_cannot_verify_the_supervisor() -> None:
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim="The model attaches the page affiliation to a different person.",
                supporting_excerpt=(
                    "Dr Amara Ndlovu is Associate Professor in the Department of "
                    "Information Systems at Southern Cape Institute of Technology."
                ),
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name="Dr Another Person",
                asserted_institution="Southern Cape Institute of Technology",
                asserted_department="Department of Information Systems",
            )
        ]
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    content = FakeContentExtraction().extract(COMPLETE_PROFILE_URL)
    agent = EvidenceVerificationAgent(model)

    claims = agent.extract_claims(
        make_prospective_supervisor(1),
        content,
        SourceKind.UNIVERSITY_PROFILE,
    )
    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert claims[0].directly_supported is False
    assert EvidenceClaimType.CURRENT_AFFILIATION.value in record.missing_required_evidence


def test_different_affiliation_is_retained_and_surfaced_without_silent_overwrite() -> None:
    agent, _, _, claims = _extract_claims(
        CONFLICTING_AFFILIATION_URL,
        source_kind=SourceKind.INSTITUTIONAL_DIRECTORY,
    )

    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert record.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS
    assert record.missing_required_evidence == ()
    assert record.prospective_supervisor.institution == "Southern Cape Institute of Technology"
    assert record.evidence[1].asserted_institution == "Northbridge University"
    assert record.verified_supervisor is not None
    assert record.verified_supervisor.institution == "Southern Cape Institute of Technology"
    assert any("differs" in concern.casefold() for concern in record.verification_concerns)


def test_one_page_cannot_create_conflicting_availability_evidence() -> None:
    with pytest.raises(ValidationError, match="distinct source pages"):
        StructuredEvidenceExtractionResult(
            claims=[
                StructuredEvidenceClaim(
                    claim_type=EvidenceClaimType.AVAILABILITY,
                    claim="The page states accepting.",
                    supporting_excerpt=(
                        "Dr Amara Ndlovu is currently accepting doctoral Candidates"
                    ),
                    confidence=EvidenceConfidence.HIGH,
                    directly_supported=True,
                    availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
                    asserted_name="Dr Amara Ndlovu",
                ),
                StructuredEvidenceClaim(
                    claim_type=EvidenceClaimType.AVAILABILITY,
                    claim="The page states not accepting.",
                    supporting_excerpt="Dr Amara Ndlovu is not accepting doctoral Candidates",
                    confidence=EvidenceConfidence.HIGH,
                    directly_supported=True,
                    availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
                    asserted_name="Dr Amara Ndlovu",
                ),
            ]
        )


def test_conflicting_availability_claims_from_distinct_pages_are_cross_linked() -> None:
    content_extraction = FakeContentExtraction()
    model = FakeEvidenceVerificationModel()
    agent = EvidenceVerificationAgent(model)
    supervisor = make_prospective_supervisor(1)
    accepting = agent.extract_claims(
        supervisor,
        content_extraction.extract(ACCEPTING_PROFILE_URL),
        SourceKind.UNIVERSITY_PROFILE,
    )
    not_accepting = agent.extract_claims(
        supervisor,
        content_extraction.extract(NOT_ACCEPTING_PROFILE_URL),
        SourceKind.DEPARTMENT_PAGE,
    )

    record = agent.build_verification_record(supervisor, (*accepting, *not_accepting))
    availability_claims = tuple(
        claim for claim in record.evidence if claim.claim_type is EvidenceClaimType.AVAILABILITY
    )

    assert record.availability_status is AvailabilityStatus.CONFLICTING_EVIDENCE
    assert len(availability_claims) == 2
    first, second = availability_claims
    assert first.conflicting_evidence_ids == (second.evidence_id,)
    assert second.conflicting_evidence_ids == (first.evidence_id,)


def test_agent_owns_stable_evidence_ids_and_exact_source_provenance() -> None:
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: make_complete_evidence_response()})
    content_extraction = FakeContentExtraction()
    _, _, _, first_claims = _extract_claims(
        COMPLETE_PROFILE_URL,
        content_extraction=content_extraction,
        model=model,
    )
    _, _, _, second_claims = _extract_claims(
        COMPLETE_PROFILE_URL,
        content_extraction=content_extraction,
        model=model,
    )

    assert first_claims == second_claims
    assert len({claim.evidence_id for claim in first_claims}) == len(first_claims)
    assert all(str(claim.source_url) == COMPLETE_PROFILE_URL for claim in first_claims)
    assert all(claim.source_kind is SourceKind.UNIVERSITY_PROFILE for claim in first_claims)
    assert all(claim.retrieved_at == FIXED_EVIDENCE_RETRIEVED_AT for claim in first_claims)
    assert all(claim.supporting_excerpt for claim in first_claims)
    assert str(model.inputs[0].source_url) == COMPLETE_PROFILE_URL
    assert model.inputs[0].expected_name == make_prospective_supervisor(1).full_name
    assert (
        model.inputs[0].page_content
        == content_extraction.extract(COMPLETE_PROFILE_URL).content.strip()
    )


def test_alternate_official_profile_can_verify_without_fabricating_a_publication() -> None:
    agent, _, _, claims = _extract_claims(
        ALTERNATE_OFFICIAL_PROFILE_URL,
        source_kind=SourceKind.DEPARTMENT_PAGE,
    )

    record = agent.build_verification_record(make_prospective_supervisor(1), claims)

    assert record.verified_supervisor is not None
    assert record.verification_status is VerificationStatus.VERIFIED
    assert EvidenceClaimType.PUBLICATION not in {claim.claim_type for claim in claims}
    assert {claim.claim_type for claim in claims} >= {
        EvidenceClaimType.IDENTITY,
        EvidenceClaimType.CURRENT_AFFILIATION,
        EvidenceClaimType.RESEARCH_INTEREST,
        EvidenceClaimType.PROJECT,
    }
