"""Pure routing and alternate-source tests for M6 evidence verification."""

from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    SearchResult,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationStatus,
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
    assert selected.source_kind is SourceKind.DEPARTMENT_PAGE
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
            SourceKind.DEPARTMENT_PAGE,
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
            SourceKind.DEPARTMENT_PAGE,
        ),
        (
            "https://www.southerncape.edu/academics/amara-ndlovu",
            "Dr Amara Ndlovu",
            SourceKind.OTHER,
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
