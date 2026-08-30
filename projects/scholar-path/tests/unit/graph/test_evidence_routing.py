"""Pure routing and alternate-source tests for M6 evidence verification."""

from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    SearchResult,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationEvidenceStandard,
    VerificationStatus,
    is_singular_person_profile_url,
)
from scholarpath.graph.verification import (
    EvidenceExtractionAttempt,
    EvidenceVerificationRoute,
    VerificationPolicy,
    alternate_official_source_query,
    classify_evidence_source_kind,
    route_after_evidence_sufficiency,
    select_alternate_official_source,
)
from scholarpath.tools.content_extraction import ContentExtractionErrorCategory
from tests.fixtures.factories import make_prospective_supervisor, make_verified_supervisor


def _partial_record(index: int = 1) -> SupervisorVerificationRecord:
    return SupervisorVerificationRecord(
        prospective_supervisor=make_prospective_supervisor(index),
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        missing_required_evidence=(
            "identity",
            "current_affiliation",
            "research_interest_or_publication",
        ),
    )


def _verified_record(index: int) -> SupervisorVerificationRecord:
    prospective = make_prospective_supervisor(index)
    verified = make_verified_supervisor(index)
    return SupervisorVerificationRecord(
        prospective_supervisor=prospective,
        evidence=verified.evidence,
        verification_status=verified.verification_status,
        availability_status=verified.availability_status,
        verification_concerns=verified.verification_concerns,
        verified_supervisor=verified,
    )


@pytest.mark.parametrize(
    "values",
    [
        {"minimum_verified_supervisors": 0},
        {"maximum_alternate_source_retries": -1},
        {"maximum_alternate_source_retries": 2},
        {"unknown_policy_option": True},
    ],
)
def test_verification_policy_rejects_invalid_or_unknown_options(
    values: Mapping[str, object],
) -> None:
    with pytest.raises(ValidationError):
        VerificationPolicy.model_validate(values)


def test_partial_record_has_retry_priority_even_when_cohort_minimum_is_already_met() -> None:
    records = tuple(_verified_record(index) for index in range(1, 6)) + (_partial_record(6),)

    route = route_after_evidence_sufficiency(
        VerificationPolicy(minimum_verified_supervisors=5),
        records,
        alternate_retry_count=0,
    )

    assert route is EvidenceVerificationRoute.RETRY_ALTERNATE


def test_policy_allows_exactly_one_alternate_source_retry() -> None:
    records = (_verified_record(1), _partial_record(2))
    policy = VerificationPolicy(
        minimum_verified_supervisors=1,
        maximum_alternate_source_retries=1,
    )

    assert (
        route_after_evidence_sufficiency(policy, records, alternate_retry_count=0)
        is EvidenceVerificationRoute.RETRY_ALTERNATE
    )
    assert (
        route_after_evidence_sufficiency(policy, records, alternate_retry_count=1)
        is EvidenceVerificationRoute.EVALUATE_RESEARCH_FIT
    )


def test_policy_continues_with_minimum_verified_cohort_after_retry_exhaustion() -> None:
    records = tuple(_verified_record(index) for index in range(1, 6)) + (_partial_record(6),)

    route = route_after_evidence_sufficiency(
        VerificationPolicy(minimum_verified_supervisors=5),
        records,
        alternate_retry_count=1,
    )

    assert route is EvidenceVerificationRoute.EVALUATE_RESEARCH_FIT


def test_policy_stops_with_partial_results_when_retry_exhausted_below_minimum() -> None:
    records = tuple(_verified_record(index) for index in range(1, 5)) + (_partial_record(5),)

    route = route_after_evidence_sufficiency(
        VerificationPolicy(minimum_verified_supervisors=5),
        records,
        alternate_retry_count=1,
    )

    assert route is EvidenceVerificationRoute.STOP_PARTIAL


def test_identity_only_mvp_uses_three_as_its_implicit_verified_cohort_minimum() -> None:
    policy = VerificationPolicy(
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )

    assert policy.minimum_verified_supervisors == 3
    assert VerificationPolicy().minimum_verified_supervisors == 5


def test_identity_only_mvp_preserves_an_explicit_verified_cohort_override() -> None:
    policy = VerificationPolicy(
        minimum_verified_supervisors=4,
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )
    records = tuple(_verified_record(index) for index in range(1, 4)) + (_partial_record(4),)

    assert policy.minimum_verified_supervisors == 4
    assert (
        route_after_evidence_sufficiency(policy, records, alternate_retry_count=0)
        is EvidenceVerificationRoute.RETRY_ALTERNATE
    )


def test_identity_only_mvp_continues_immediately_with_three_verified_supervisors() -> None:
    records = tuple(_verified_record(index) for index in range(1, 4)) + (_partial_record(4),)
    policy = VerificationPolicy(
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )

    route = route_after_evidence_sufficiency(
        policy,
        records,
        alternate_retry_count=0,
    )

    assert route is EvidenceVerificationRoute.EVALUATE_RESEARCH_FIT


def test_identity_only_mvp_retries_once_then_stops_with_only_two_verified_supervisors() -> None:
    records = tuple(_verified_record(index) for index in range(1, 3)) + (_partial_record(3),)
    policy = VerificationPolicy(
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )

    assert (
        route_after_evidence_sufficiency(policy, records, alternate_retry_count=0)
        is EvidenceVerificationRoute.RETRY_ALTERNATE
    )
    assert (
        route_after_evidence_sufficiency(policy, records, alternate_retry_count=1)
        is EvidenceVerificationRoute.STOP_PARTIAL
    )


def test_strict_standard_keeps_five_minimum_and_retry_priority() -> None:
    five_verified_with_one_partial = tuple(_verified_record(index) for index in range(1, 6)) + (
        _partial_record(6),
    )
    four_verified_with_one_partial = tuple(_verified_record(index) for index in range(1, 5)) + (
        _partial_record(5),
    )
    policy = VerificationPolicy()

    assert (
        route_after_evidence_sufficiency(
            policy,
            five_verified_with_one_partial,
            alternate_retry_count=0,
        )
        is EvidenceVerificationRoute.RETRY_ALTERNATE
    )
    assert (
        route_after_evidence_sufficiency(
            policy,
            five_verified_with_one_partial,
            alternate_retry_count=1,
        )
        is EvidenceVerificationRoute.EVALUATE_RESEARCH_FIT
    )
    assert (
        route_after_evidence_sufficiency(
            policy,
            four_verified_with_one_partial,
            alternate_retry_count=1,
        )
        is EvidenceVerificationRoute.STOP_PARTIAL
    )


def test_policy_rejects_a_negative_runtime_retry_count() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        route_after_evidence_sufficiency(
            VerificationPolicy(),
            (_partial_record(),),
            alternate_retry_count=-1,
        )


def _search_result(
    *,
    url: str,
    title: str,
    description: str,
    query: str,
) -> SearchResult:
    return SearchResult.model_validate(
        {
            "url": url,
            "title": title,
            "description": description,
            "originating_query": query,
        }
    )


@pytest.mark.parametrize(
    ("full_name", "expected_name"),
    [
        ("Dr Amara Ndlovu", "Amara Ndlovu"),
        ("Prof. Amara Ndlovu", "Amara Ndlovu"),
        ("Associate Professor Amara Ndlovu", "Amara Ndlovu"),
        ("Professor Emerita Amara Ndlovu", "Amara Ndlovu"),
        ("Professor Maximilian Förster", "Maximilian Förster"),
    ],
)
def test_alternate_source_query_uses_the_title_free_substantive_person_name(
    full_name: str,
    expected_name: str,
) -> None:
    supervisor = make_prospective_supervisor(1, full_name=full_name)

    query = alternate_official_source_query(supervisor)

    assert query.startswith(f'"{expected_name}" ')
    assert "Dr " not in query
    assert "Prof " not in query
    assert "Professor " not in query


def test_alternate_source_selects_the_first_plausible_official_page() -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    official = _search_result(
        url="https://www.southerncape.ac.za/department/staff/amara-ndlovu",
        title=(
            "Dr Amara Ndlovu | Department of Information Systems | "
            "Southern Cape Institute of Technology"
        ),
        description="Official institutional staff profile.",
        query=query,
    )

    selected = select_alternate_official_source(supervisor, (official,), query=query)

    assert selected is not None
    assert selected.supervisor_id == supervisor.supervisor_id
    assert str(selected.source_url) == str(official.url)
    assert selected.source_kind is SourceKind.INSTITUTIONAL_DIRECTORY
    assert selected.originating_query == query


@pytest.mark.parametrize(
    "url",
    [
        "https://faculty.southerncape.edu/people/amara-ndlovu",
        "https://faculty.southerncape.edu.au/people/amara-ndlovu",
        "https://faculty.southerncape.ac.za/people/amara-ndlovu",
    ],
)
def test_alternate_source_accepts_label_aware_academic_domains(url: str) -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | Southern Cape Institute of Technology",
        description="Official institutional profile.",
        query=query,
    )

    assert select_alternate_official_source(supervisor, (result,), query=query) is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.southerncape.ac.za/profile/amara-ndlovu",
        "https://www.southerncape.ac.za/profile/48217",
        "https://www.southerncape.ac.za/profiles/amara-ndlovu",
        "https://www.southerncape.ac.za/academic/amara-ndlovu",
        "https://www.southerncape.ac.za/academics/amara-ndlovu",
        "https://www.southerncape.ac.za/people/amara-ndlovu",
        "https://www.southerncape.ac.za/person/amara-ndlovu",
        "https://www.southerncape.ac.za/persons/amara-ndlovu",
        "https://www.southerncape.ac.za/directories/amara-ndlovu",
        "https://www.southerncape.ac.za/directory/amara-ndlovu",
        "https://www.southerncape.ac.za/department/staff/amara-ndlovu",
        "https://www.southerncape.ac.za/staff/48217/amara-ndlovu",
        "https://www.southerncape.ac.za/staff-directory/amara-ndlovu",
        "https://www.southerncape.ac.za/researcher/amara-ndlovu",
        "https://www.southerncape.ac.za/researchers/amara-ndlovu",
        "https://www.southerncape.ac.za/about/our-people/amara-ndlovu",
    ],
)
def test_matching_academic_host_accepts_only_a_singular_person_profile_path(
    url: str,
) -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | Southern Cape Institute of Technology",
        description="Official institutional person profile.",
        query=query,
    )

    assert is_singular_person_profile_url(url)
    assert select_alternate_official_source(supervisor, (result,), query=query) is not None


def test_person_slug_may_contain_a_denylisted_word_without_becoming_content() -> None:
    supervisor = make_prospective_supervisor(1, full_name="Dr Alice News")
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url="https://www.southerncape.ac.za/profile/alice-news",
        title="Dr Alice News | Southern Cape Institute of Technology",
        description="Official institutional person profile.",
        query=query,
    )

    assert is_singular_person_profile_url(str(result.url))
    assert select_alternate_official_source(supervisor, (result,), query=query) is not None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.southerncape.ac.za/people",
        "https://www.southerncape.ac.za/staff",
        "https://www.southerncape.ac.za/directory",
        "https://www.southerncape.ac.za/persons",
        "https://www.southerncape.ac.za/profile",
        "https://www.southerncape.ac.za/profiles",
        "https://www.southerncape.ac.za/researcher",
        "https://www.southerncape.ac.za/researchers",
        "https://www.southerncape.ac.za/staff-directory",
        "https://www.southerncape.ac.za/directory/faculty",
        "https://www.southerncape.ac.za/people/all",
        "https://www.southerncape.ac.za/profile/our-people",
        "https://www.southerncape.ac.za/staff/directory",
        "https://www.southerncape.ac.za/news/amara-ndlovu",
        "https://www.southerncape.ac.za/articles/amara-ndlovu",
        "https://www.southerncape.ac.za/publications/amara-ndlovu",
        "https://www.southerncape.ac.za/projects/amara-ndlovu",
        "https://www.southerncape.ac.za/contact/people/amara-ndlovu",
        "https://www.southerncape.ac.za/search/people/amara-ndlovu",
        "https://www.southerncape.ac.za/projects/profile/amara-ndlovu",
        "https://www.southerncape.ac.za/groups/people/amara-ndlovu",
        "https://www.southerncape.ac.za/about/profile/amara-ndlovu",
        "https://www.southerncape.ac.za/about-us/people/amara-ndlovu",
        "https://www.southerncape.ac.za/en/news-and-events/people/amara-ndlovu",
        "https://www.southerncape.ac.za/en/news_and_events/people/amara-ndlovu",
        "https://www.southerncape.ac.za/en/articles-and-news/profiles/amara-ndlovu",
        "https://www.southerncape.ac.za/en/projects-and-events/faculty/amara-ndlovu",
        "https://www.southerncape.ac.za/en/search-results/person/amara-ndlovu",
        "https://www.southerncape.ac.za/en/newsAndEvents/people/amara-ndlovu",
        "https://www.southerncape.ac.za/en/newsandevents/people/amara-ndlovu",
        "https://www.southerncape.ac.za/en/searchResults/people/amara-ndlovu",
        "https://www.southerncape.ac.za/en/contactUs/people/amara-ndlovu",
        "https://www.southerncape.ac.za/en/researchProjects/people/amara-ndlovu",
    ],
)
def test_matching_academic_host_rejects_collection_and_general_content_paths(
    url: str,
) -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | Southern Cape Institute of Technology",
        description="The exact person and institution appear in this result.",
        query=query,
    )

    assert not is_singular_person_profile_url(url)
    assert select_alternate_official_source(supervisor, (result,), query=query) is None


def test_bradford_compound_news_route_cannot_be_selected_as_an_alternate_profile() -> None:
    supervisor = make_prospective_supervisor(
        1,
        full_name="Professor Dhaval Thakker",
        institution="University of Bradford",
    )
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url="https://www.bradford.ac.uk/en/news-and-events/people/dhaval-thakker",
        title="Professor Dhaval Thakker | University of Bradford",
        description="The exact person and institution appear in this result.",
        query=query,
    )

    assert not is_singular_person_profile_url(str(result.url))
    assert select_alternate_official_source(supervisor, (result,), query=query) is None


@pytest.mark.parametrize("compound_prefix", ["newsAndEvents", "newsandevents"])
def test_bradford_camel_or_concatenated_news_route_cannot_be_selected(
    compound_prefix: str,
) -> None:
    supervisor = make_prospective_supervisor(
        1,
        full_name="Professor Dhaval Thakker",
        institution="University of Bradford",
    )
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=(f"https://www.bradford.ac.uk/en/{compound_prefix}/people/dhaval-thakker"),
        title="Professor Dhaval Thakker | University of Bradford",
        description="The exact person and institution appear in this result.",
        query=query,
    )

    assert not is_singular_person_profile_url(str(result.url))
    assert select_alternate_official_source(supervisor, (result,), query=query) is None


@pytest.mark.parametrize(
    ("url", "expected_kind"),
    [
        (
            "https://www.uwe.ac.uk/about/our-people/amara-ndlovu",
            SourceKind.UNIVERSITY_PROFILE,
        ),
        (
            "https://www.uwe.ac.uk/persons/amara-ndlovu",
            SourceKind.UNIVERSITY_PROFILE,
        ),
        (
            "https://www.uwe.ac.uk/researcher/amara-ndlovu",
            SourceKind.UNIVERSITY_PROFILE,
        ),
        (
            "https://www.uwe.ac.uk/researchers/amara-ndlovu",
            SourceKind.UNIVERSITY_PROFILE,
        ),
        (
            "https://www.uwe.ac.uk/directory/amara-ndlovu",
            SourceKind.INSTITUTIONAL_DIRECTORY,
        ),
        (
            "https://profiles.uwe.ac.uk/profile/48217",
            SourceKind.UNIVERSITY_PROFILE,
        ),
    ],
)
def test_alternate_source_accepts_an_abbreviated_academic_host_for_one_person_profile(
    url: str,
    expected_kind: SourceKind,
) -> None:
    supervisor = make_prospective_supervisor(
        1,
        institution="University of the West of England",
    )
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | University of the West of England",
        description="Official academic profile.",
        query=query,
    )

    selected = select_alternate_official_source(supervisor, (result,), query=query)

    assert is_singular_person_profile_url(url)
    assert selected is not None
    assert selected.source_kind is expected_kind


@pytest.mark.parametrize(
    "url",
    [
        "https://www.uwe.ac.uk/",
        "https://www.uwe.ac.uk/people",
        "https://www.uwe.ac.uk/persons",
        "https://www.uwe.ac.uk/researcher",
        "https://www.uwe.ac.uk/researchers",
        "https://www.uwe.ac.uk/directory",
        "https://www.uwe.ac.uk/news/amara-ndlovu",
        "https://www.uwe.ac.uk/news/persons/amara-ndlovu",
        "https://www.uwe.ac.uk/articles/researchers/amara-ndlovu",
        "https://www.uwe.ac.uk/publications/amara-ndlovu",
        "https://www.uwe.ac.uk/publications/directory/amara-ndlovu",
        "https://www.uwe.ac.uk/projects/amara-ndlovu",
        "https://www.uwe.ac.uk/search/amara-ndlovu",
        "https://www.unrelated.edu/people/amara-ndlovu",
        "https://www.uwe.example/people/amara-ndlovu",
        "http://www.uwe.ac.uk/people/amara-ndlovu",
    ],
)
def test_abbreviated_host_exception_rejects_general_content_and_unrelated_hosts(
    url: str,
) -> None:
    supervisor = make_prospective_supervisor(
        1,
        institution="University of the West of England",
    )
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | University of the West of England",
        description="Official university page.",
        query=query,
    )

    assert select_alternate_official_source(supervisor, (result,), query=query) is None


def test_abbreviated_host_exception_still_requires_exact_person_and_institution_text() -> None:
    supervisor = make_prospective_supervisor(
        1,
        institution="University of the West of England",
    )
    query = alternate_official_source_query(supervisor)
    wrong_person = _search_result(
        url="https://www.uwe.ac.uk/persons/nomsa-ndlovu",
        title="Dr Nomsa Ndlovu | University of the West of England",
        description="Official academic profile.",
        query=query,
    )
    wrong_institution = _search_result(
        url="https://www.uwe.ac.uk/directory/amara-ndlovu",
        title="Dr Amara Ndlovu | University of Bristol",
        description="Official academic profile.",
        query=query,
    )

    assert select_alternate_official_source(supervisor, (wrong_person,), query=query) is None
    assert select_alternate_official_source(supervisor, (wrong_institution,), query=query) is None


def test_short_academic_host_label_can_match_one_unambiguous_institution_name() -> None:
    supervisor = make_prospective_supervisor(1, institution="Oxford University")
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url="https://www.ox.ac.uk/people/amara-ndlovu",
        title="Dr Amara Ndlovu | Oxford University",
        description="Official academic profile.",
        query=query,
    )

    selected = select_alternate_official_source(supervisor, (result,), query=query)

    assert selected is not None
    assert selected.source_kind is SourceKind.UNIVERSITY_PROFILE


@pytest.mark.parametrize(
    ("institution", "url"),
    [
        (
            "University of Southern California",
            "https://viterbi.usc.edu/directory/faculty/amara-ndlovu",
        ),
        (
            "University of the West of England",
            "https://profiles.uwe.ac.uk/profile/48217",
        ),
        (
            "Southern Cape Institute of Technology",
            "https://www.southerncape.ac.za/people/amara-ndlovu",
        ),
    ],
)
def test_correlated_academic_host_recovers_a_sparse_official_person_profile(
    institution: str,
    url: str,
) -> None:
    supervisor = make_prospective_supervisor(1, institution=institution)
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | Faculty profile",
        description="Official academic profile.",
        query=query,
    )

    selected = select_alternate_official_source(supervisor, (result,), query=query)

    assert selected is not None
    assert selected.supervisor_id == supervisor.supervisor_id
    assert str(selected.source_url) == url


def test_correlated_academic_host_does_not_override_a_named_institution_conflict() -> None:
    supervisor = make_prospective_supervisor(
        1,
        institution="University of the West of England",
    )
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url="https://www.uwe.ac.uk/persons/amara-ndlovu",
        title="Dr Amara Ndlovu | University of Bristol",
        description="Official academic profile.",
        query=query,
    )

    assert select_alternate_official_source(supervisor, (result,), query=query) is None


def test_sparse_metadata_recovery_rejects_a_host_prefix_without_exact_correlation() -> None:
    supervisor = make_prospective_supervisor(1, institution="Oxford University")
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url="https://www.ox.ac.uk/people/amara-ndlovu",
        title="Dr Amara Ndlovu | Faculty profile",
        description="Official academic profile.",
        query=query,
    )

    assert select_alternate_official_source(supervisor, (result,), query=query) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.usc.edu/people",
        "https://www.usc.edu/staff",
        "https://www.usc.edu/news/amara-ndlovu",
        "https://www.unrelated.edu/people/amara-ndlovu",
    ],
)
def test_sparse_metadata_recovery_still_rejects_lists_content_and_unrelated_hosts(
    url: str,
) -> None:
    supervisor = make_prospective_supervisor(
        1,
        institution="University of Southern California",
    )
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | Faculty profile",
        description="Official academic profile.",
        query=query,
    )

    assert select_alternate_official_source(supervisor, (result,), query=query) is None


@pytest.mark.parametrize(
    "url",
    [
        "https://www.southerncape.ac.za/news/amara-ndlovu",
        "https://www.southerncape.ac.za/publications/amara-ndlovu",
        "https://www.southerncape.ac.za/projects/amara-ndlovu",
        "https://www.southerncape.ac.za/amara-ndlovu",
    ],
)
def test_matching_academic_host_still_requires_an_official_profile_source_kind(
    url: str,
) -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url=url,
        title="Dr Amara Ndlovu | Southern Cape Institute of Technology",
        description="Official university content.",
        query=query,
    )

    assert select_alternate_official_source(supervisor, (result,), query=query) is None


@pytest.mark.parametrize(
    ("url", "title", "description"),
    [
        (
            "http://www.southerncape.ac.za/staff/amara-ndlovu",
            "Dr Amara Ndlovu | Southern Cape Institute of Technology",
            "An unencrypted page.",
        ),
        (
            "https://profiles.scholarpath.example/supervisor-001#biography",
            "Dr Amara Ndlovu | Southern Cape Institute of Technology",
            "The original profile under another fragment.",
        ),
        (
            "https://profiles.example.com/amara-ndlovu",
            "Dr Amara Ndlovu | Southern Cape Institute of Technology",
            "A commercial profile that merely repeats the institution name.",
        ),
        (
            "https://southerncape.evil.com/amara-ndlovu",
            "Dr Amara Ndlovu | Southern Cape Institute of Technology",
            "A commercial host containing the institution name.",
        ),
        (
            "https://profiles.southerncape.edu.evil.com/amara-ndlovu",
            "Dr Amara Ndlovu | Southern Cape Institute of Technology",
            "A commercial host with an embedded education label.",
        ),
        (
            "https://unrelated.edu/faculty/amara-ndlovu",
            "Dr Amara Ndlovu | Southern Cape Institute of Technology",
            "An unrelated academic host repeating the institution name.",
        ),
        (
            "https://southerncape.ac.za.attacker.edu/faculty/amara-ndlovu",
            "Dr Amara Ndlovu | Southern Cape Institute of Technology",
            "A controlled academic suffix with a deceptive institution subdomain.",
        ),
        (
            "https://www.southerncape.ac.za/department/staff/jordan-lee",
            "Dr Jordan Lee | Southern Cape Institute of Technology",
            "An official page for another person.",
        ),
        (
            "https://www.southerncape.ac.za/department/staff/nomsa-ndlovu",
            "Dr Nomsa Ndlovu | Southern Cape Institute of Technology",
            "An official page for a different person with the same surname.",
        ),
        (
            "https://www.northbridge.edu/staff/amara-ndlovu",
            "Dr Amara Ndlovu | Northbridge University",
            "The right person at an institution unrelated to the discovered profile.",
        ),
    ],
)
def test_alternate_source_rejects_non_official_original_or_wrong_person_pages(
    url: str,
    title: str,
    description: str,
) -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    result = _search_result(url=url, title=title, description=description, query=query)

    assert select_alternate_official_source(supervisor, (result,), query=query) is None


def test_alternate_source_rejects_result_from_another_originating_query() -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    result = _search_result(
        url="https://www.southerncape.ac.za/staff/amara-ndlovu",
        title="Dr Amara Ndlovu | Southern Cape Institute of Technology",
        description="Official institutional profile.",
        query="a different search query",
    )

    assert select_alternate_official_source(supervisor, (result,), query=query) is None


def test_search_snippet_is_used_for_selection_but_never_persisted_as_evidence() -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    snippet = (
        "Southern Cape Institute of Technology says Dr Amara Ndlovu is accepting "
        "doctoral Candidates; this search snippet is not page evidence."
    )
    result = _search_result(
        url="https://www.southerncape.ac.za/staff/amara-ndlovu",
        title="Dr Amara Ndlovu | Southern Cape Institute of Technology",
        description=snippet,
        query=query,
    )

    selected = select_alternate_official_source(supervisor, (result,), query=query)

    assert selected is not None
    serialized_reference = selected.model_dump_json()
    assert snippet not in serialized_reference
    assert "accepting doctoral Candidates" not in serialized_reference
    assert "description" not in selected.model_fields_set


@pytest.mark.parametrize(
    ("source_url", "title", "expected"),
    [
        (
            "https://profiles.southerncape.edu/amara-ndlovu",
            "",
            SourceKind.UNIVERSITY_PROFILE,
        ),
        (
            "https://www.southerncape.edu/department/staff/amara-ndlovu",
            "",
            SourceKind.INSTITUTIONAL_DIRECTORY,
        ),
        (
            "https://www.southerncape.edu/staff/amara-ndlovu",
            "",
            SourceKind.INSTITUTIONAL_DIRECTORY,
        ),
        (
            "https://www.southerncape.edu/repository/item-42",
            "",
            SourceKind.RESEARCH_REPOSITORY,
        ),
        (
            "https://www.southerncape.edu/research-portal/item-42",
            "",
            SourceKind.RESEARCH_REPOSITORY,
        ),
        (
            "https://www.southerncape.edu/projects/responsible-ai",
            "",
            SourceKind.PROJECT_PAGE,
        ),
        (
            "https://www.southerncape.edu/publications/item-42",
            "",
            SourceKind.PUBLICATION,
        ),
        (
            "https://www.southerncape.edu/academics/amara-ndlovu",
            "Department of Information Systems",
            SourceKind.UNIVERSITY_PROFILE,
        ),
        (
            "https://www.southerncape.edu/academics/amara-ndlovu",
            "Dr Amara Ndlovu",
            SourceKind.UNIVERSITY_PROFILE,
        ),
        (
            "https://profiles.untrusted.example/people/amara-ndlovu",
            "University profile",
            SourceKind.OTHER,
        ),
    ],
)
def test_source_kind_classifier_uses_only_known_url_and_title_signals(
    source_url: str,
    title: str,
    expected: SourceKind,
) -> None:
    assert classify_evidence_source_kind(source_url, title=title) is expected


def test_evidence_extraction_attempt_accepts_unambiguous_success_and_failure() -> None:
    success = EvidenceExtractionAttempt.model_validate(
        {
            "supervisor_id": "supervisor-001",
            "source_url": "https://example.edu/profile",
            "source_kind": SourceKind.UNIVERSITY_PROFILE,
            "attempt_number": 1,
            "discovery_round": 1,
            "alternate_source": False,
            "successful": True,
        }
    )
    failure = EvidenceExtractionAttempt.model_validate(
        {
            "supervisor_id": "supervisor-001",
            "source_url": "https://example.edu/department/profile",
            "source_kind": SourceKind.DEPARTMENT_PAGE,
            "attempt_number": 2,
            "discovery_round": 1,
            "alternate_source": True,
            "successful": False,
            "error_category": ContentExtractionErrorCategory.EXTRACTION_FAILED,
        }
    )

    assert success.error_category is None
    assert failure.error_category is ContentExtractionErrorCategory.EXTRACTION_FAILED


@pytest.mark.parametrize(
    "values",
    [
        {"successful": True, "error_category": ContentExtractionErrorCategory.PROVIDER},
        {"successful": False, "error_category": None},
        {"attempt_number": 0},
        {"attempt_number": 3},
        {"discovery_round": 0},
        {"successful": "yes"},
        {"alternate_source": 1},
    ],
)
def test_evidence_extraction_attempt_rejects_ambiguous_or_invalid_values(
    values: Mapping[str, object],
) -> None:
    data: dict[str, object] = {
        "supervisor_id": "supervisor-001",
        "source_url": "https://example.edu/profile",
        "source_kind": SourceKind.UNIVERSITY_PROFILE,
        "attempt_number": 1,
        "discovery_round": 1,
        "alternate_source": False,
        "successful": True,
        **values,
    }

    with pytest.raises(ValidationError):
        EvidenceExtractionAttempt.model_validate(data)
