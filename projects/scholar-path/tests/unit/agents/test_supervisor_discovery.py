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
    SearchResultRejectionCounts,
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
    snippets: tuple[str, ...] = (),
    query: str = QUERY_ONE,
) -> SearchResult:
    return SearchResult.model_validate(
        {
            "url": url,
            "title": title,
            "description": description,
            "snippets": snippets,
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
    assert discovery.rejection_counts == SearchResultRejectionCounts()
    supervisor = discovery.prospective_supervisors[0]
    assert supervisor.full_name == "Dr Jane Doe"
    assert supervisor.institution == "Example University"
    assert supervisor.department == "Department of Information Systems"
    assert supervisor.status is SupervisorLifecycleStatus.PROSPECTIVE
    assert supervisor.discovery_source == "https://example.edu/people/jane-doe"
    assert supervisor.discovery_query == QUERY_ONE
    assert supervisor.discovery_provenance[0].originating_query == QUERY_ONE


def test_realistic_provider_layouts_retain_multiple_plausible_supervisors() -> None:
    results = (
        _result(
            url="https://uct.example/staff-directory/jane-doe",
            title="Jane Doe - Associate Professor - University of Cape Town",
            description="Research profile for distributed systems and digital infrastructure.",
        ),
        _result(
            url="https://wits.example/academic-staff/thabo-mokoena",
            title="Mokoena, Thabo | Senior Lecturer | University of the Witwatersrand",
            description="Faculty research profile in information systems.",
        ),
        _result(
            url="https://unimelb.example/find-an-expert/priya-raman",
            title="Priya Raman | Staff profile",
            description="Staff profile.",
            snippets=(
                "Priya Raman is an Associate Professor in the School of Computing "
                "at University of Melbourne.",
            ),
        ),
        _result(
            url="https://ethz.example/directory/jose-van-dijk",
            title="José van Dijk | Professor of Information Systems | ETH Zürich",
            description="Research profile in secure digital platforms.",
        ),
        _result(
            url="https://imperial.example/experts/amina-bello",
            title="Amina Bello | Reader in Computer Science | Imperial College London",
            description="Academic profile in distributed computing.",
        ),
        _result(
            url="https://nus.example/faculty/li-wei",
            title="Professor Li Wei | School of Computing | National University of Singapore",
            description="Researches dependable software architecture.",
        ),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), results)

    assert discovery.result_count == 6
    assert discovery.plausible_supervisor_count == 6
    assert [item.full_name for item in discovery.prospective_supervisors] == [
        "Jane Doe",
        "Thabo Mokoena",
        "Priya Raman",
        "José van Dijk",
        "Amina Bello",
        "Professor Li Wei",
    ]
    assert [item.institution for item in discovery.prospective_supervisors] == [
        "University of Cape Town",
        "University of the Witwatersrand",
        "University of Melbourne",
        "ETH Zürich",
        "Imperial College London",
        "National University of Singapore",
    ]


def test_snippets_do_not_turn_non_academic_people_or_directories_into_supervisors() -> None:
    results = (
        _result(
            url="https://example.edu/directory",
            title="Staff Directory | Example University",
            description="Browse academic researchers and faculty members.",
        ),
        _result(
            url="https://example.edu/news/jane-doe",
            title="Jane Doe | Example University",
            description="University news.",
            snippets=("Jane Doe is the Chief Executive of Example Ventures.",),
        ),
        _result(
            url="https://example.edu/staff-directory/dr-jane-doe",
            title="Dr Jane Doe | Example University Hospital",
            description="Dr Jane Doe treats patients in the hospital.",
        ),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), results)

    assert discovery.prospective_supervisors == ()


def test_conflicting_snippet_person_does_not_create_a_mixed_profile_identity() -> None:
    result = _result(
        url="https://example.edu/people/jane-doe",
        title="Jane Doe | Example University",
        description="Academic staff profile.",
        snippets=("Professor Alice Smith researches distributed systems at Example University.",),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts.identity_conflict == 1


def test_conflicting_snippet_person_excludes_a_non_profile_result() -> None:
    result = _result(
        url="https://example.edu/news/jane-doe",
        title="Jane Doe | Example University",
        description="University research news.",
        snippets=("Professor Alice Smith discusses the work.",),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors == ()


def test_combined_role_and_institution_segment_is_normalized_to_institution() -> None:
    result = _result(
        url="https://example.edu/people/jane-doe",
        title="Jane Doe | Associate Professor at Example University",
        description="Academic research profile.",
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors[0].institution == "Example University"


def test_incomplete_title_institution_falls_through_to_complete_bounded_context() -> None:
    result = _result(
        url="https://www.uel.ac.uk/about-uel/news/professor-nazrul-islam",
        title="Professor Nazrul Islam | University of",
        description=(
            "Professor Nazrul Islam is Director of Research Degrees at the "
            "University of East London."
        ),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert len(discovery.prospective_supervisors) == 1
    assert discovery.prospective_supervisors[0].full_name == "Professor Nazrul Islam"
    assert discovery.prospective_supervisors[0].institution == "University of East London"


@pytest.mark.parametrize("connector", ["and", "at", "for", "of", "the", "with"])
def test_incomplete_institution_without_complete_context_is_excluded(connector: str) -> None:
    result = _result(
        url="https://example.edu/news/professor-nazrul-islam",
        title=f"Professor Nazrul Islam | Example University {connector}",
        description="Professor Nazrul Islam is an academic researcher.",
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts.incomplete_institution == 1


def test_discovery_records_each_privacy_safe_rejection_category() -> None:
    results = (
        _result(
            url="https://example.edu/directory",
            title="Staff Directory | Example University",
            description="Research group directory.",
        ),
        _result(
            url="https://example.edu/news/jane-doe",
            title="Jane Doe | Example University",
            description="University news.",
        ),
        _result(
            url="https://example.edu/news/identity-conflict",
            title="Jane Doe | Example University",
            description="Academic staff profile.",
            snippets=("Professor Alice Smith researches systems at Example University.",),
        ),
        _result(
            url="https://example.org/profile/jane-doe",
            title="Professor Jane Doe | Research profile",
            description="Professor Jane Doe is an academic researcher.",
        ),
        _result(
            url="https://example.edu/news/professor-nazrul-islam",
            title="Professor Nazrul Islam | Example University of",
            description="Professor Nazrul Islam is an academic researcher.",
        ),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), results)

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        person_not_established=1,
        academic_context_not_established=1,
        identity_conflict=1,
        institution_not_established=1,
        incomplete_institution=1,
    )
    assert discovery.rejection_counts.total == discovery.result_count


@pytest.mark.parametrize(
    "description",
    [
        "Professor of Computer Science at Example University.",
        "Associate Professor in Information Systems at Example University.",
    ],
)
def test_singular_person_profile_accepts_unnamed_academic_role_summary(
    description: str,
) -> None:
    result = _result(
        url="https://example.edu/people/jane-doe",
        title="Jane Doe | Example University",
        description=description,
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert [item.full_name for item in discovery.prospective_supervisors] == ["Jane Doe"]


def test_affiliation_excludes_trailing_academic_activity_clause() -> None:
    result = _result(
        url="https://example.edu/people/jane-doe",
        title="Jane Doe | Associate Professor",
        description="Jane Doe is a professor at Example University and researches systems.",
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors[0].institution == "Example University"


@pytest.mark.parametrize(
    "page_label",
    [
        "MIT News",
        "IEEE Article",
        "AI Research",
        "Example University News",
        "Institute Directory",
    ],
)
def test_acronym_page_labels_are_not_treated_as_institutions(page_label: str) -> None:
    result = _result(
        url="https://example.org/news/jane-doe",
        title=f"Jane Doe | Professor of Computing | {page_label}",
        description="Jane Doe is an academic researcher.",
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors == ()


@pytest.mark.parametrize(
    ("url", "title"),
    [
        (
            "https://example.edu/team/digital-transformation",
            "Digital Transformation | Example University",
        ),
        (
            "https://example.edu/directory/artificial-intelligence",
            "Artificial Intelligence | Example University",
        ),
        (
            "https://example.edu/experts/responsible-innovation",
            "Responsible Innovation | Example University",
        ),
    ],
)
def test_capitalized_topic_pages_are_not_treated_as_people(url: str, title: str) -> None:
    result = _result(
        url=url,
        title=title,
        description="Academic researcher profile.",
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors == ()


@pytest.mark.parametrize("institution", ["UJ", "TU Delft", "KU Leuven"])
def test_short_acronym_institutions_are_retained(institution: str) -> None:
    result = _result(
        url="https://example.edu/people/jane-doe",
        title=f"Jane Doe | Associate Professor | {institution}",
        description=f"Jane Doe is an Associate Professor at {institution}.",
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.prospective_supervisors[0].institution == institution


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


def test_structured_discovery_output_requires_all_results_to_be_accounted_for() -> None:
    with pytest.raises(ValidationError, match="account for every result"):
        SupervisorDiscoveryResult(result_count=1)


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
    ("url", "title", "expected_institution", "expected_department"),
    [
        (
            "https://example.edu/people/elias-hart",
            "Professor Elias Hart | School of Computing and Strategy | Northbridge University",
            "Northbridge University",
            "School of Computing and Strategy",
        ),
        (
            "https://example.edu/people/sofia-mensah",
            "Professor Sofia Mensah | School of Organisational Studies | "
            "Meridian School of Management",
            "Meridian School of Management",
            "School of Organisational Studies",
        ),
    ],
)
def test_department_school_is_not_mistaken_for_the_institution(
    url: str,
    title: str,
    expected_institution: str,
    expected_department: str,
) -> None:
    supervisor = (
        SupervisorDiscoveryAgent()
        .discover(
            _search_plan(),
            (_result(url=url, title=title, description="Academic research profile."),),
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
                    description="Associate Professor Jane Doe is a researcher at MIT.",
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
