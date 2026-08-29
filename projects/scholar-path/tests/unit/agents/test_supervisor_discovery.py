"""Unit tests for deterministic Prospective Supervisor discovery."""

import json

import pytest
from pydantic import ValidationError

from scholarpath.agents import (
    SupervisorDiscoveryAgent,
    SupervisorDiscoveryResult,
    canonical_profile_url,
    deduplicate_prospective_supervisors,
    deterministic_supervisor_id,
)
from scholarpath.domain import (
    PlannedSearchQuery,
    SearchPlan,
    SearchResult,
    SearchSourceType,
    SupervisorLifecycleStatus,
)
from tests.fixtures import make_prospective_supervisors

QUERY_ONE = "responsible AI university profiles"
QUERY_TWO = "enterprise architecture research groups"
QUERY_THREE = "digital transformation recent publications"
QUERY_FOUR = "doctoral supervision information systems"


def _search_plan() -> SearchPlan:
    return SearchPlan(
        search_queries=(
            PlannedSearchQuery(
                query=QUERY_ONE,
                purpose="Find official profiles.",
                target_source_types=(SearchSourceType.OFFICIAL_UNIVERSITY_PROFILE,),
            ),
            PlannedSearchQuery(
                query=QUERY_TWO,
                purpose="Find research groups.",
                target_source_types=(SearchSourceType.DEPARTMENT_OR_RESEARCH_GROUP,),
            ),
            PlannedSearchQuery(
                query=QUERY_THREE,
                purpose="Find publication evidence.",
                target_source_types=(SearchSourceType.RECENT_PUBLICATION,),
            ),
            PlannedSearchQuery(
                query=QUERY_FOUR,
                purpose="Find explicit doctoral supervision information.",
                target_source_types=(SearchSourceType.DOCTORAL_SUPERVISION_INFORMATION,),
            ),
        ),
        expanded_research_concepts=("AI assurance", "enterprise design"),
        target_regions=("South Africa",),
        rationale="Cover profile, group, publication, and supervision sources.",
    )


def _result(
    *,
    url: str = "https://example.edu/people/jane-doe",
    title: str = "Dr Jane Doe | Department of Information Systems | Example University",
    description: str = "Dr Jane Doe is an academic researcher at Example University.",
    query: str = QUERY_ONE,
) -> SearchResult:
    return SearchResult.model_validate(
        {
            "url": url,
            "title": title,
            "description": description,
            "originating_query": query,
        }
    )


def test_valid_academic_profile_becomes_a_prospective_supervisor() -> None:
    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (_result(),))

    assert isinstance(discovery, SupervisorDiscoveryResult)
    assert len(discovery.prospective_supervisors) == 1
    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 1
    assert discovery.duplicate_result_count == 0
    supervisor = discovery.prospective_supervisors[0]
    assert supervisor.full_name == "Dr Jane Doe"
    assert supervisor.institution == "Example University"
    assert supervisor.department == "Department of Information Systems"
    assert supervisor.status is SupervisorLifecycleStatus.PROSPECTIVE
    assert supervisor.discovery_source == "https://example.edu/people/jane-doe"
    assert supervisor.discovery_query == QUERY_ONE
    assert supervisor.discovery_provenance[0].originating_query == QUERY_ONE


def test_empty_result_set_returns_an_empty_structured_output() -> None:
    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), ())

    assert discovery == SupervisorDiscoveryResult()


@pytest.mark.parametrize(
    "counts",
    [
        {"result_count": 0, "plausible_supervisor_count": 1},
        {
            "result_count": 1,
            "plausible_supervisor_count": 1,
            "duplicate_result_count": 2,
        },
        {"result_count": 1, "plausible_supervisor_count": 1},
    ],
)
def test_structured_discovery_output_rejects_inconsistent_quality_counts(
    counts: dict[str, int],
) -> None:
    with pytest.raises(ValidationError):
        SupervisorDiscoveryResult.model_validate(counts)


def test_normalized_identity_and_canonical_url_duplicates_are_merged() -> None:
    first = _result(
        url="https://example.edu/people/jane-doe/?utm_source=first#research",
        title="Dr Jane Doe | Department of Information Systems | Example University",
        query=QUERY_ONE,
    )
    second = _result(
        url="https://EXAMPLE.edu/people/jane-doe",
        title="Professor Jane Doe | Example   University",
        query=QUERY_TWO,
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (first, second))

    assert len(discovery.prospective_supervisors) == 1
    assert discovery.result_count == 2
    assert discovery.plausible_supervisor_count == 2
    assert discovery.duplicate_result_count == 1
    supervisor = discovery.prospective_supervisors[0]
    assert supervisor.full_name == "Dr Jane Doe"
    assert [item.originating_query for item in supervisor.discovery_provenance] == [
        QUERY_ONE,
        QUERY_TWO,
    ]
    assert [str(item.source_url) for item in supervisor.discovery_provenance] == [
        "https://example.edu/people/jane-doe/?utm_source=first#research",
        "https://example.edu/people/jane-doe",
    ]


def test_one_supervisor_retains_multiple_exact_discovery_queries() -> None:
    results = (
        _result(query=QUERY_ONE),
        _result(query=QUERY_FOUR),
    )

    supervisor = (
        SupervisorDiscoveryAgent().discover(_search_plan(), results).prospective_supervisors[0]
    )

    assert tuple(item.originating_query for item in supervisor.discovery_provenance) == (
        QUERY_ONE,
        QUERY_FOUR,
    )


def test_non_person_and_missing_institution_results_are_excluded() -> None:
    results = (
        _result(
            title="Department of Information Systems | Example University",
            description="Research group directory and projects.",
        ),
        _result(
            url="https://example.org/profile/dr-jane-doe",
            title="Dr Jane Doe | Research profile",
            description="Dr Jane Doe publishes on responsible AI.",
        ),
        _result(
            url="https://example.org/profile/dr-jane-doe-ai",
            title="Dr Jane Doe | AI | Research profile",
            description="Dr Jane Doe publishes on responsible AI.",
        ),
        _result(
            url="https://example.edu/people/maya-chen",
            title="Maya Chen | Pacific Arc University",
            description="Maya Chen is an academic researcher at Pacific Arc University.",
        ),
        _result(
            url="https://example.edu/research/digital-transformation",
            title="Digital Transformation | Example University",
            description="Academic researchers at Example University study this topic.",
        ),
        _result(
            url="https://example.edu/hospital/jane-doe",
            title="Dr Jane Doe | Example University Hospital",
            description="Dr Jane Doe treats patients at Example University Hospital.",
        ),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), results)

    assert [item.full_name for item in discovery.prospective_supervisors] == ["Maya Chen"]


@pytest.mark.parametrize(
    ("title", "expected_institution", "expected_department"),
    [
        (
            "Professor Elias Hart | School of Computing and Strategy | Northbridge University",
            "Northbridge University",
            "School of Computing and Strategy",
        ),
        (
            "Professor Sofia Mensah | School of Organisational Studies | "
            "Meridian School of Management",
            "Meridian School of Management",
            "School of Organisational Studies",
        ),
    ],
)
def test_department_school_is_not_mistaken_for_the_institution(
    title: str,
    expected_institution: str,
    expected_department: str,
) -> None:
    supervisor = (
        SupervisorDiscoveryAgent()
        .discover(
            _search_plan(),
            (_result(title=title),),
        )
        .prospective_supervisors[0]
    )

    assert supervisor.institution == expected_institution
    assert supervisor.department == expected_department


def test_academic_title_and_institution_abbreviation_are_supported() -> None:
    supervisor = (
        SupervisorDiscoveryAgent()
        .discover(
            _search_plan(),
            (
                _result(
                    url="https://example.edu/faculty/jane-doe",
                    title="Associate Professor Jane Doe | Research profile",
                    description="Associate Professor Jane Doe is a researcher with MIT.",
                ),
            ),
        )
        .prospective_supervisors[0]
    )

    assert supervisor.full_name == "Associate Professor Jane Doe"
    assert supervisor.institution == "MIT"


def test_deduplication_synthesizes_provenance_for_legacy_records() -> None:
    first = make_prospective_supervisors()[0].model_copy(
        update={"discovery_source": "https://search.example/first"}
    )
    second = first.model_copy(
        update={
            "discovery_source": "https://search.example/second",
            "discovery_query": QUERY_TWO,
        }
    )

    merged = deduplicate_prospective_supervisors((first, second))

    assert len(merged) == 1
    assert tuple(item.originating_query for item in merged[0].discovery_provenance) == (
        first.discovery_query,
        QUERY_TWO,
    )
    assert tuple(str(item.source_url) for item in merged[0].discovery_provenance) == (
        "https://search.example/first",
        "https://search.example/second",
    )


def test_discovery_produces_no_research_fit_or_availability_output() -> None:
    result = _result(
        description=(
            "Dr Jane Doe is a professor at Example University and the page explicitly "
            "mentions accepting doctoral Candidates."
        )
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))
    serialized = json.loads(discovery.model_dump_json())
    keys = json.dumps(serialized).casefold()

    assert "score" not in keys
    assert "research_fit" not in keys
    assert "availability" not in keys
    assert "accepting" not in keys
    assert discovery.prospective_supervisors[0].status is SupervisorLifecycleStatus.PROSPECTIVE


def test_result_from_an_unplanned_query_is_rejected() -> None:
    with pytest.raises(ValueError, match="not present in SearchPlan"):
        SupervisorDiscoveryAgent().discover(
            _search_plan(),
            (_result(query="unplanned query"),),
        )


def test_canonical_url_and_identifier_are_deterministic() -> None:
    first_url = "https://Example.edu:443/people/jane-doe/?utm_medium=test#bio"
    second_url = "https://example.edu/people/jane-doe"

    assert canonical_profile_url(first_url) == canonical_profile_url(second_url)
    assert canonical_profile_url("https://example.edu") == canonical_profile_url(
        "https://example.edu/"
    )
    assert deterministic_supervisor_id(
        "Dr Jane Doe", "Example University", first_url
    ) == deterministic_supervisor_id("Professor Jane Doe", "example university", second_url)
    assert deterministic_supervisor_id(
        "Dr Jane Doe", "Example University", "https://one.example/supervisor-001"
    ) != deterministic_supervisor_id(
        "Dr Alex Smith", "Other University", "https://two.example/supervisor-001"
    )
