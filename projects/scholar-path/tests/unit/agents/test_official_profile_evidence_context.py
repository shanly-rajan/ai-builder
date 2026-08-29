"""Offline tests for bounded subject context on official person profiles."""

from datetime import timedelta

import pytest
from pydantic import ValidationError

from scholarpath.agents.evidence_verification import (
    EvidenceVerificationAgent,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
)
from scholarpath.agents.independent_review import (
    IndependentReviewResult,
    reconcile_research_fit_assessment,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewDecision,
    IndependentReviewFailureKind,
    IndependentReviewStatus,
    ProspectiveSupervisor,
    ResearchFitAssessment,
    ResearchFitBreakdown,
    ResearchFitComponentAssessment,
    ResearchFitEvidenceError,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationStatus,
    VerifiedSupervisor,
    derive_availability_status,
    evidence_claim_is_grounded_for_supervisor,
    is_singular_person_profile_url,
    supervisor_names_are_title_equivalent,
    validate_research_fit_evidence,
)
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import FakeEvidenceVerificationModel
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT, make_prospective_supervisor

PROFILE_URL = "https://profiles.example.edu/dhaval-thakker"
PAGE_NAME = "Professor Dhavalkumar (Dhaval) Thakker"


def _supervisor() -> ProspectiveSupervisor:
    return make_prospective_supervisor(1).model_copy(
        update={
            "full_name": "Professor Dhaval Thakker",
            "institution": "University of Bradford",
            "department": "School of Management",
            "profile_url": PROFILE_URL,
        }
    )


def _identity_draft(*, asserted_name: str = PAGE_NAME) -> StructuredEvidenceClaim:
    return StructuredEvidenceClaim(
        claim_type=EvidenceClaimType.IDENTITY,
        claim=f"The profile identifies {asserted_name}.",
        supporting_excerpt=asserted_name,
        confidence=EvidenceConfidence.HIGH,
        directly_supported=True,
        asserted_name=asserted_name,
    )


def _extract(
    claims: list[StructuredEvidenceClaim],
    content: str,
    *,
    source_kind: SourceKind = SourceKind.UNIVERSITY_PROFILE,
    source_url: str = PROFILE_URL,
    supervisor: ProspectiveSupervisor | None = None,
) -> tuple[EvidenceVerificationAgent, tuple[EvidenceClaim, ...]]:
    response = StructuredEvidenceExtractionResult.model_validate(
        {"claims": [claim.model_dump(mode="python") for claim in claims]}
    )
    model = FakeEvidenceVerificationModel({source_url: response})
    agent = EvidenceVerificationAgent(model)
    extracted = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": content,
            "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
        }
    )
    return agent, agent.extract_claims(supervisor or _supervisor(), extracted, source_kind)


def _topic_assessment(supervisor_id: str, research_id: str) -> ResearchFitAssessment:
    missing_component = ResearchFitComponentAssessment(
        score=0,
        rationale="No suitable evidence was retrieved.",
        confidence=EvidenceConfidence.LOW,
        evidence_gap="Suitable evidence is missing.",
    )
    return ResearchFitAssessment(
        supervisor_id=supervisor_id,
        overall_score=10,
        breakdown=ResearchFitBreakdown(
            topic_alignment=ResearchFitComponentAssessment(
                score=10,
                rationale="The research-interest claim supports topic alignment.",
                supporting_evidence_ids=(research_id,),
                confidence=EvidenceConfidence.HIGH,
            ),
            methodological_alignment=missing_component,
            research_orientation_alignment=missing_component,
            recent_research_alignment=missing_component,
            practical_constraint_alignment=missing_component,
        ),
        rationale="Only the directly supported topic evidence contributes points.",
        supporting_evidence_ids=(research_id,),
        confidence=EvidenceConfidence.MEDIUM,
    )


def _verified_context_bundle() -> tuple[VerifiedSupervisor, ResearchFitAssessment]:
    affiliation_excerpt = (
        "Current position: Professor, School of Management, University of Bradford."
    )
    research_excerpt = "Research interests: enterprise systems and responsible AI."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The profile states a current affiliation.",
            supporting_excerpt=affiliation_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            asserted_institution="University of Bradford",
            asserted_department="School of Management",
        ),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states enterprise systems and responsible AI research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]
    agent, claims = _extract(
        drafts,
        f"{PAGE_NAME}\n{affiliation_excerpt}\n{research_excerpt}",
    )
    record = agent.build_verification_record(_supervisor(), claims)
    assert record.verified_supervisor is not None
    research = next(
        claim for claim in claims if claim.claim_type is EvidenceClaimType.RESEARCH_INTEREST
    )
    return record.verified_supervisor, _topic_assessment(
        record.verified_supervisor.supervisor_id,
        research.evidence_id,
    )


def _unchecked_verified_with_evidence(
    supervisor: VerifiedSupervisor,
    evidence: tuple[EvidenceClaim, ...],
) -> VerifiedSupervisor:
    data = {
        field_name: getattr(supervisor, field_name)
        for field_name in VerifiedSupervisor.model_fields
    }
    data["evidence"] = evidence
    return VerifiedSupervisor.model_construct(**data)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.edu/profile/jane-doe",
        "https://example.edu/profiles/12345",
        "https://example.edu/academic/jane-doe",
        "https://example.edu/academics/jane-doe",
        "https://example.edu/people/jane-doe",
        "https://example.edu/person/jane-doe",
        "https://example.edu/en/persons/jane-doe",
        "https://example.edu/directories/jane-doe",
        "https://example.edu/directory/jane-doe",
        "https://example.edu/staff-directory/jane-doe",
        "https://example.edu/department/staff/jane-doe",
        "https://example.edu/staff/12345/jane-doe",
        "https://example.edu/faculty/jane-doe",
        "https://example.edu/researcher/jane-doe",
        "https://example.edu/researchers/jane-doe",
        "https://example.edu/about/our-people/jane-doe",
        "https://example.edu/profile/alice-news",
        "https://profiles.example.edu/jane-doe",
        "https://people.example.edu/12345",
    ],
)
def test_singular_person_profile_url_accepts_only_bounded_person_routes(url: str) -> None:
    assert is_singular_person_profile_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://example.edu/staff",
        "https://example.edu/directory",
        "https://example.edu/people",
        "https://example.edu/profiles",
        "https://example.edu/people/events",
        "https://example.edu/faculty/about",
        "https://example.edu/profile/contact",
        "https://example.edu/profile/our-people",
        "https://example.edu/directory/events",
        "https://example.edu/directory/team",
        "https://example.edu/contact/people/jane-doe",
        "https://example.edu/search/people/jane-doe",
        "https://example.edu/projects/profile/jane-doe",
        "https://example.edu/groups/people/jane-doe",
        "https://example.edu/about/profile/jane-doe",
        "https://example.edu/about-us/people/jane-doe",
        "https://example.edu/en/news-and-events/people/jane-doe",
        "https://example.edu/en/news_and_events/people/jane-doe",
        "https://example.edu/en/articles-and-news/profiles/jane-doe",
        "https://example.edu/en/projects-and-events/faculty/jane-doe",
        "https://example.edu/en/search-results/person/jane-doe",
        "https://example.edu/en/newsAndEvents/people/jane-doe",
        "https://example.edu/en/newsandevents/people/jane-doe",
        "https://example.edu/en/searchResults/people/jane-doe",
        "https://example.edu/en/contactUs/people/jane-doe",
        "https://example.edu/en/researchProjects/people/jane-doe",
        "https://example.edu/news/profile/jane-doe",
        "https://example.edu/articles/people/jane-doe",
        "https://example.edu/publications/researchers/jane-doe",
        "https://example.edu/groups/faculty/jane-doe",
        "https://example.edu/people/jane-doe/publications",
        "https://profiles.example.edu/news",
        "https://people.example.edu/people",
        "https://profiles.example.edu/jane-doe/publications",
    ],
)
def test_singular_person_profile_url_rejects_collections_and_content_pages(url: str) -> None:
    assert not is_singular_person_profile_url(url)


@pytest.mark.parametrize(
    "source_kind",
    [SourceKind.UNIVERSITY_PROFILE, SourceKind.INSTITUTIONAL_DIRECTORY],
)
def test_official_profile_sections_and_first_person_prose_link_to_identity(
    source_kind: SourceKind,
) -> None:
    affiliation_excerpt = (
        "Current position: Professor, School of Management, University of Bradford."
    )
    research_excerpt = (
        "Research interests: enterprise systems, responsible AI, and digital innovation."
    )
    methodology_excerpt = "My work uses design science research and case-study evaluation."
    availability_excerpt = "I am currently accepting new doctoral Candidates."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The profile states a current role in the School of Management.",
            supporting_excerpt=affiliation_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            asserted_institution="University of Bradford",
            asserted_department="School of Management",
        ),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states research in enterprise systems and responsible AI.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.METHODOLOGY,
            claim="The profile states use of design science and case-study evaluation.",
            supporting_excerpt=methodology_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.AVAILABILITY,
            claim="The profile explicitly states current doctoral availability.",
            supporting_excerpt=availability_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
    ]
    content = "\n".join(
        (
            f"# {PAGE_NAME}",
            affiliation_excerpt,
            research_excerpt,
            methodology_excerpt,
            availability_excerpt,
        )
    )

    agent, claims = _extract(drafts, content, source_kind=source_kind)
    record = agent.build_verification_record(_supervisor(), claims)
    identity = next(claim for claim in claims if claim.claim_type is EvidenceClaimType.IDENTITY)
    contextual_claims = tuple(
        claim for claim in claims if claim.claim_type is not EvidenceClaimType.IDENTITY
    )

    assert supervisor_names_are_title_equivalent(PAGE_NAME, _supervisor().full_name)
    assert all(claim.directly_supported for claim in claims)
    assert all(
        claim.subject_identity_evidence_id == identity.evidence_id for claim in contextual_claims
    )
    assert all(
        evidence_claim_is_grounded_for_supervisor(claim, _supervisor(), claims) for claim in claims
    )
    assert record.verification_status is VerificationStatus.VERIFIED
    assert record.availability_status is AvailabilityStatus.CONFIRMED_ACCEPTING
    assert SupervisorVerificationRecord.model_validate_json(record.model_dump_json()) == record


def test_research_fit_accepts_a_grounded_official_profile_context_link() -> None:
    research_excerpt = "Research interests: enterprise systems and responsible AI."
    affiliation_excerpt = (
        "Current position: Professor, School of Management, University of Bradford."
    )
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The profile states a current affiliation.",
            supporting_excerpt=affiliation_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            asserted_institution="University of Bradford",
            asserted_department="School of Management",
        ),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states enterprise systems and responsible AI research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]
    agent, claims = _extract(
        drafts,
        f"{PAGE_NAME}\n{affiliation_excerpt}\n{research_excerpt}",
    )
    record = agent.build_verification_record(_supervisor(), claims)
    assert record.verified_supervisor is not None
    research = next(
        claim for claim in claims if claim.claim_type is EvidenceClaimType.RESEARCH_INTEREST
    )

    assessment = _topic_assessment(_supervisor().supervisor_id, research.evidence_id)

    validate_research_fit_evidence(record.verified_supervisor, assessment)


def test_research_fit_rejects_a_broken_context_identity_link() -> None:
    verified, assessment = _verified_context_bundle()
    research = next(
        claim
        for claim in verified.evidence
        if claim.claim_type is EvidenceClaimType.RESEARCH_INTEREST
    )
    broken = research.model_copy(
        update={"subject_identity_evidence_id": "evidence-missing-identity"}
    )
    invalid_verified = _unchecked_verified_with_evidence(
        verified,
        tuple(
            broken if claim.evidence_id == research.evidence_id else claim
            for claim in verified.evidence
        ),
    )

    with pytest.raises(ResearchFitEvidenceError, match="grounded evidence"):
        validate_research_fit_evidence(invalid_verified, assessment)


def test_independent_reviewer_rejects_broken_context_as_overlooked_evidence() -> None:
    verified, assessment = _verified_context_bundle()
    research = next(
        claim
        for claim in verified.evidence
        if claim.claim_type is EvidenceClaimType.RESEARCH_INTEREST
    )
    broken_overlooked = research.model_copy(
        update={
            "evidence_id": "evidence-broken-overlooked",
            "claim_type": EvidenceClaimType.METHODOLOGY,
            "claim": "The profile states use of design science research.",
            "supporting_excerpt": "Methodology: design science research.",
            "subject_identity_evidence_id": "evidence-missing-identity",
        }
    )
    invalid_verified = _unchecked_verified_with_evidence(
        verified,
        (*verified.evidence, broken_overlooked),
    )
    review = IndependentReviewResult(
        decision=IndependentReviewDecision.REVISE,
        recommended_score=assessment.overall_score,
        unsupported_claim_ids=[],
        overlooked_evidence_ids=[broken_overlooked.evidence_id],
        confidence=EvidenceConfidence.HIGH,
        critique="The proposed additional evidence reference requires validation.",
    )

    reconciled = reconcile_research_fit_assessment(
        invalid_verified,
        assessment,
        review,
    )

    assert reconciled.review_status is IndependentReviewStatus.UNAVAILABLE
    assert reconciled.failure_kind is IndependentReviewFailureKind.INVALID_EVIDENCE_REFERENCE


def test_parenthetical_alias_never_overrides_a_mismatched_surname() -> None:
    wrong_page_name = "Professor Dhavalkumar (Dhaval) Thacker"
    affiliation_excerpt = (
        "Current position: Professor, School of Management, University of Bradford."
    )
    drafts = [
        _identity_draft(asserted_name=wrong_page_name),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The profile states a current affiliation.",
            supporting_excerpt=affiliation_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=wrong_page_name,
            asserted_institution="University of Bradford",
            asserted_department="School of Management",
        ),
    ]

    _, claims = _extract(drafts, f"{wrong_page_name}\n{affiliation_excerpt}")

    assert not supervisor_names_are_title_equivalent(wrong_page_name, _supervisor().full_name)
    assert all(not claim.directly_supported for claim in claims)
    assert all(claim.subject_identity_evidence_id is None for claim in claims)


@pytest.mark.parametrize(
    "page_name",
    [
        "Professor Dhavalkumar (AI) Thakker",
        "Professor Dhavalkumar (University) Thakker",
        "Professor Dhavalkumar (Bob) Thakker",
        "Professor Dhavalkumar (Researcher) Thakker",
        "Professor Dhavalkumar Thakker (AI)",
        "Professor Dhavalkumar Thakker (University)",
    ],
)
def test_parenthetical_alias_rejects_non_morphological_tokens(page_name: str) -> None:
    assert not supervisor_names_are_title_equivalent(
        page_name,
        "Professor Dhavalkumar Thakker",
    )


def test_parenthetical_alias_accepts_only_a_morphological_given_name_form() -> None:
    assert supervisor_names_are_title_equivalent(
        "Professor Dhavalkumar (Dhaval) Thakker",
        "Professor Dhaval Thakker",
    )


def test_official_affiliation_bullets_bind_through_same_page_identity() -> None:
    sarah = _supervisor().model_copy(
        update={
            "full_name": "Professor Sarah McGeown",
            "institution": "University of Edinburgh",
            "department": "Moray House School of Education and Sport",
        }
    )
    affiliation_excerpt = "* Moray House School of Education and Sport\n* University of Edinburgh"
    drafts = [
        _identity_draft(asserted_name=sarah.full_name),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The official profile states the current school and university.",
            supporting_excerpt=affiliation_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=sarah.full_name,
            asserted_institution=sarah.institution,
            asserted_department=sarah.department,
        ),
    ]

    _, claims = _extract(
        drafts,
        f"# {sarah.full_name}\n{affiliation_excerpt}",
        supervisor=sarah,
    )
    identity, affiliation = claims

    assert affiliation.directly_supported is True
    assert affiliation.subject_identity_evidence_id == identity.evidence_id
    assert evidence_claim_is_grounded_for_supervisor(affiliation, sarah, claims)


@pytest.mark.parametrize(
    ("research_excerpt", "expected_direct"),
    [
        (
            "His research focuses on enterprise architectures and AI governance.",
            True,
        ),
        (
            "Professor Thakker’s research focuses on enterprise architectures and AI governance.",
            False,
        ),
        (
            "Professor Lovelace’s research focuses on enterprise architectures and AI governance.",
            False,
        ),
    ],
)
def test_official_profile_context_does_not_bind_a_surname_only_subject(
    research_excerpt: str,
    expected_direct: bool,
) -> None:
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states enterprise architecture and AI governance research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]

    _, claims = _extract(drafts, f"# {PAGE_NAME}\n{research_excerpt}")
    identity, research = claims

    assert research.directly_supported is expected_direct
    assert research.subject_identity_evidence_id == (
        identity.evidence_id if expected_direct else None
    )


@pytest.mark.parametrize("source_kind", [SourceKind.DEPARTMENT_PAGE, SourceKind.OTHER])
def test_group_and_general_pages_cannot_use_profile_section_context(
    source_kind: SourceKind,
) -> None:
    research_excerpt = "Research interests: enterprise systems and responsible AI."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The page lists enterprise systems research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]

    _, claims = _extract(
        drafts,
        f"{PAGE_NAME}\n{research_excerpt}",
        source_kind=source_kind,
    )
    research = claims[1]

    assert claims[0].directly_supported is True
    assert research.directly_supported is False
    assert research.subject_identity_evidence_id is None


@pytest.mark.parametrize(
    "source_url",
    [
        "https://example.edu/people",
        "https://example.edu/staff",
        "https://example.edu/directory",
        "https://example.edu/news/profile/dhaval-thakker",
        "https://example.edu/groups/people/dhaval-thakker",
        "https://example.edu/en/news-and-events/people/dhaval-thakker",
        "https://example.edu/en/news_and_events/people/dhaval-thakker",
        "https://example.edu/about-us/people/dhaval-thakker",
        "https://example.edu/en/newsAndEvents/people/dhaval-thakker",
        "https://example.edu/en/newsandevents/people/dhaval-thakker",
        "https://example.edu/en/searchResults/people/dhaval-thakker",
        "https://example.edu/en/contactUs/people/dhaval-thakker",
        "https://example.edu/en/researchProjects/people/dhaval-thakker",
    ],
)
def test_official_source_kind_cannot_context_link_a_collection_url(
    source_url: str,
) -> None:
    research_excerpt = "Research interests: enterprise systems and responsible AI."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The page lists enterprise systems research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]

    _, claims = _extract(
        drafts,
        f"{PAGE_NAME}\n{research_excerpt}",
        source_url=source_url,
    )

    assert claims[0].directly_supported is True
    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None


def test_contextual_affiliation_rejects_an_untitled_other_person() -> None:
    affiliation_excerpt = "Alice Smith — School of Management, University of Bradford."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The page states a current affiliation.",
            supporting_excerpt=affiliation_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            asserted_institution="University of Bradford",
            asserted_department="School of Management",
        ),
    ]

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{affiliation_excerpt}")

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None


def test_contextual_research_rejects_an_untitled_other_person() -> None:
    research_excerpt = "Research interests of Alice Smith: analytical engines."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The page states analytical-engine research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{research_excerpt}")

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None


def test_contextual_research_rejects_a_labelled_untitled_other_person() -> None:
    research_excerpt = "Research interests: Alice Smith studies analytical engines."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The page states analytical-engine research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{research_excerpt}")

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None


def test_contextual_affiliation_rejects_a_labelled_untitled_other_person() -> None:
    affiliation_excerpt = (
        "Current position: Alice Smith is Professor, School of Management, University of Bradford."
    )
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
            claim="The page states a current affiliation.",
            supporting_excerpt=affiliation_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            asserted_institution="University of Bradford",
            asserted_department="School of Management",
        ),
    ]

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{affiliation_excerpt}")

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None


def test_contextual_availability_rejects_first_person_text_beneath_another_person() -> None:
    availability_excerpt = "## Alice Smith\nI am currently accepting new doctoral Candidates."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.AVAILABILITY,
            claim="The page appears to state current doctoral availability.",
            supporting_excerpt=availability_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
    ]

    agent, claims = _extract(drafts, f"{PAGE_NAME}\n{availability_excerpt}")
    record = agent.build_verification_record(_supervisor(), claims)

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None
    assert record.availability_status is AvailabilityStatus.NOT_STATED


def test_contextual_availability_checks_the_heading_before_an_exact_excerpt() -> None:
    availability_excerpt = "I am currently accepting new doctoral Candidates."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.AVAILABILITY,
            claim="The page appears to state current doctoral availability.",
            supporting_excerpt=availability_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
    ]
    page_content = f"# {PAGE_NAME}\n## Alice Smith\n{availability_excerpt}"

    agent, claims = _extract(drafts, page_content)
    record = agent.build_verification_record(_supervisor(), claims)

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None
    assert record.availability_status is AvailabilityStatus.NOT_STATED


def test_contextual_availability_rejects_a_credentialed_other_person_heading() -> None:
    availability_excerpt = "I am currently accepting new doctoral Candidates."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.AVAILABILITY,
            claim="The page appears to state current doctoral availability.",
            supporting_excerpt=availability_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
    ]
    page_content = f"# {PAGE_NAME}\n## Alice Smith, PhD\n{availability_excerpt}"

    agent, claims = _extract(drafts, page_content)
    record = agent.build_verification_record(_supervisor(), claims)

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None
    assert record.availability_status is AvailabilityStatus.NOT_STATED


@pytest.mark.parametrize(
    "role_line",
    [
        "Professor of Artificial Intelligence",
        "Associate Professor in Information Systems",
    ],
)
def test_owner_profile_role_line_does_not_replace_the_page_subject(role_line: str) -> None:
    research_excerpt = "Research interests: enterprise systems and responsible AI."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The page states enterprise-systems research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]
    page_content = f"# {PAGE_NAME}\n{role_line}\n## Research interests\n{research_excerpt}"

    _, claims = _extract(drafts, page_content)

    assert claims[1].directly_supported is True
    assert claims[1].subject_identity_evidence_id == claims[0].evidence_id


def test_official_profile_context_rejects_an_excerpt_about_another_person() -> None:
    wrong_person_excerpt = "Professor Ada Lovelace studies analytical engines."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The page states research on analytical engines.",
            supporting_excerpt=wrong_person_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{wrong_person_excerpt}")

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None


def test_official_profile_context_rejects_a_mismatched_asserted_name() -> None:
    research_excerpt = "Research interests: enterprise systems and responsible AI."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The page states enterprise systems research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name="Professor Ada Lovelace",
        ),
    ]

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{research_excerpt}")

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None


def test_pronoun_led_official_profile_research_is_linked_to_page_identity() -> None:
    research_excerpt = "Her research focuses on enterprise systems and responsible AI."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states enterprise systems and responsible AI research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]

    _, claims = _extract(drafts, f"{PAGE_NAME}\n{research_excerpt}")

    assert claims[1].directly_supported is True
    assert claims[1].subject_identity_evidence_id == claims[0].evidence_id


def test_contextual_not_accepting_statement_preserves_explicit_polarity() -> None:
    availability_excerpt = "I am not currently accepting new doctoral Candidates."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.AVAILABILITY,
            claim="The profile explicitly states current doctoral availability.",
            supporting_excerpt=availability_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            availability_status=AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
        ),
    ]

    agent, claims = _extract(drafts, f"{PAGE_NAME}\n{availability_excerpt}")
    record = agent.build_verification_record(_supervisor(), claims)

    assert claims[1].directly_supported is True
    assert claims[1].subject_identity_evidence_id == claims[0].evidence_id
    assert record.availability_status is AvailabilityStatus.CONFIRMED_NOT_ACCEPTING


def test_availability_derivation_ignores_an_unresolved_context_identity_link() -> None:
    availability_excerpt = "I am currently accepting new doctoral Candidates."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.AVAILABILITY,
            claim="The profile explicitly states current doctoral availability.",
            supporting_excerpt=availability_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
    ]
    _, claims = _extract(drafts, f"{PAGE_NAME}\n{availability_excerpt}")
    identity, availability = claims
    unresolved = availability.model_copy(
        update={"subject_identity_evidence_id": "evidence-missing-identity"}
    )

    assert (
        derive_availability_status(
            (identity, availability),
            _supervisor().supervisor_id,
        )
        is AvailabilityStatus.CONFIRMED_ACCEPTING
    )
    assert (
        derive_availability_status(
            (identity, unresolved),
            _supervisor().supervisor_id,
        )
        is AvailabilityStatus.NOT_STATED
    )


@pytest.mark.parametrize(
    "availability_excerpt",
    [
        "Availability: Yes",
        "I welcome doctoral enquiries.",
        "I am open to doctoral enquiries.",
    ],
)
def test_official_profile_context_does_not_infer_availability(
    availability_excerpt: str,
) -> None:
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.AVAILABILITY,
            claim="The profile appears to discuss doctoral enquiries.",
            supporting_excerpt=availability_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
            availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
        ),
    ]

    agent, claims = _extract(drafts, f"{PAGE_NAME}\n{availability_excerpt}")
    record = agent.build_verification_record(_supervisor(), claims)

    assert claims[1].directly_supported is False
    assert claims[1].subject_identity_evidence_id is None
    assert record.availability_status is AvailabilityStatus.NOT_STATED


def test_context_link_must_resolve_to_identity_from_the_same_page_and_retrieval() -> None:
    research_excerpt = "Research interests: enterprise systems and responsible AI."
    drafts = [
        _identity_draft(),
        StructuredEvidenceClaim(
            claim_type=EvidenceClaimType.RESEARCH_INTEREST,
            claim="The profile states enterprise systems research.",
            supporting_excerpt=research_excerpt,
            confidence=EvidenceConfidence.HIGH,
            directly_supported=True,
            asserted_name=PAGE_NAME,
        ),
    ]
    _, claims = _extract(drafts, f"{PAGE_NAME}\n{research_excerpt}")
    identity, research = claims
    cross_source = research.model_copy(
        update={"source_url": "https://profiles.example.edu/a-different-page"}
    )
    later_retrieval = research.model_copy(
        update={"retrieved_at": research.retrieved_at + timedelta(seconds=1)}
    )

    assert not evidence_claim_is_grounded_for_supervisor(
        cross_source,
        _supervisor(),
        (identity, cross_source),
    )
    assert not evidence_claim_is_grounded_for_supervisor(
        later_retrieval,
        _supervisor(),
        (identity, later_retrieval),
    )
    with pytest.raises(ValidationError, match="must be grounded"):
        SupervisorVerificationRecord(
            prospective_supervisor=_supervisor(),
            evidence=(identity, cross_source),
            verification_status=VerificationStatus.PARTIALLY_VERIFIED,
            missing_required_evidence=(
                EvidenceClaimType.CURRENT_AFFILIATION.value,
                "research_interest_or_publication",
            ),
        )
