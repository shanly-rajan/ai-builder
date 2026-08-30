"""Adversarial tests for deterministic academic-profile layout recognition."""

import json

import pytest

from scholarpath.agents import SupervisorDiscoveryAgent
from scholarpath.domain import (
    PlannedSearchQuery,
    SearchPlan,
    SearchResult,
    SearchResultRejectionCounts,
    SearchSourceType,
    SupervisorLifecycleStatus,
)

PROFILE_QUERY = "enterprise architecture academic profiles"
GROUP_QUERY = "enterprise architecture university research groups"
PUBLICATION_QUERY = "enterprise architecture recent academic publications"
SUPERVISION_QUERY = "enterprise architecture research degree supervision information"


def _search_plan() -> SearchPlan:
    return SearchPlan(
        search_queries=(
            PlannedSearchQuery(
                query=PROFILE_QUERY,
                purpose="Find official university profiles.",
                target_source_types=(SearchSourceType.OFFICIAL_UNIVERSITY_PROFILE,),
            ),
            PlannedSearchQuery(
                query=GROUP_QUERY,
                purpose="Find department and research-group pages.",
                target_source_types=(SearchSourceType.DEPARTMENT_OR_RESEARCH_GROUP,),
            ),
            PlannedSearchQuery(
                query=PUBLICATION_QUERY,
                purpose="Find recent publication evidence.",
                target_source_types=(SearchSourceType.RECENT_PUBLICATION,),
            ),
            PlannedSearchQuery(
                query=SUPERVISION_QUERY,
                purpose="Find explicit research-degree supervision information.",
                target_source_types=(SearchSourceType.RESEARCH_DEGREE_SUPERVISION_INFORMATION,),
            ),
        ),
        expanded_research_concepts=("enterprise architecture", "AI governance"),
        target_regions=("United Kingdom",),
        rationale="Cover each required source type without evaluating Research Fit.",
    )


def _result(
    *,
    url: str,
    title: str,
    description: str = "",
    snippets: tuple[str, ...] = (),
) -> SearchResult:
    return SearchResult.model_validate(
        {
            "url": url,
            "title": title,
            "description": description,
            "snippets": snippets,
            "originating_query": PROFILE_QUERY,
        }
    )


@pytest.mark.parametrize(
    ("url", "description", "snippets"),
    [
        (
            "https://example.edu/people/jane-doe",
            "Jane Doe's research focuses on enterprise architecture and AI governance.",
            (),
        ),
        (
            "https://example.edu/en/persons/jane-doe",
            "Jane Doe's research focuses on enterprise architecture and AI governance.",
            (),
        ),
        (
            "https://example.edu/people/jane-doe",
            "University staff profile.",
            ("Jane Doe's research focuses on enterprise architecture and AI governance.",),
        ),
    ],
)
def test_singular_person_profile_retains_identity_linked_research_support(
    url: str,
    description: str,
    snippets: tuple[str, ...],
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url=url,
                title="Jane Doe | Example University",
                description=description,
                snippets=snippets,
            ),
        ),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 1
    assert discovery.duplicate_result_count == 0
    assert discovery.rejection_counts == SearchResultRejectionCounts()
    assert len(discovery.prospective_supervisors) == 1
    supervisor = discovery.prospective_supervisors[0]
    assert supervisor.full_name == "Jane Doe"
    assert supervisor.institution == "Example University"
    assert supervisor.status is SupervisorLifecycleStatus.PROSPECTIVE
    assert str(supervisor.profile_url) == url
    assert supervisor.discovery_query == PROFILE_QUERY


def test_person_profile_rejects_research_context_that_does_not_name_the_owner() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=(
                    "Research focuses on enterprise architecture and responsible AI systems."
                ),
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


def test_person_shaped_url_does_not_turn_a_generic_topic_into_a_person() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/digital-transformation",
                title="Digital Transformation | Example University",
                description=("Digital transformation research focuses on enterprise systems."),
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


@pytest.mark.parametrize(
    "description",
    [
        "Enterprise Architecture researches responsible AI adoption.",
        "Enterprise Architecture has research projects in responsible AI.",
        "Enterprise Architecture offers academic expertise in AI governance.",
        "Enterprise Architecture's research focuses on responsible AI.",
        "Enterprise Architecture is a researcher at Example University.",
    ],
)
def test_search_plan_topic_phrases_never_become_people(description: str) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/enterprise-architecture",
                title="Enterprise Architecture | Example University",
                description=description,
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


@pytest.mark.parametrize(
    "description",
    [
        "Jane Doe studies adoption patterns.",
        "Jane Doe published a student blog post.",
        "Jane Doe has interests in hiking.",
    ],
)
def test_ambiguous_person_activity_is_not_scholarly_support(description: str) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=description,
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


@pytest.mark.parametrize(
    "description",
    [
        "Jane Doe has no research interests.",
        "Jane Doe's research interests are not stated.",
        "Jane Doe has no publications.",
        "Jane Doe has not published research.",
    ],
)
def test_negated_scholarly_language_is_not_positive_support(description: str) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=description,
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


def test_contrastive_exclusion_does_not_negate_positive_research_support() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=(
                    "Jane Doe's research focuses on AI governance, not consumer chatbots."
                ),
            ),
        ),
    )

    assert [supervisor.full_name for supervisor in discovery.prospective_supervisors] == [
        "Jane Doe"
    ]


def test_later_titled_identity_matching_the_profile_url_supports_seo_title_order() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Example University | Professor Jane Doe",
                description="Official faculty profile.",
            ),
        ),
    )

    assert [supervisor.full_name for supervisor in discovery.prospective_supervisors] == [
        "Professor Jane Doe"
    ]
    assert discovery.prospective_supervisors[0].institution == "Example University"


@pytest.mark.parametrize(
    "title",
    [
        "Jane Doe | Professor Alice Smith | Example University",
        "Jane Doe | Professor Alice Smith at Example University | Example University",
    ],
)
def test_later_different_titled_identity_does_not_override_the_profile_owner(
    title: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title=title,
                description="Official faculty profile.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(identity_conflict=1)


def test_suffix_role_identity_is_not_treated_as_an_unnamed_role_segment() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Alice Smith, Professor | Example University",
                description="Official faculty profile.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(identity_conflict=1)


def test_adjacent_different_name_and_role_are_not_anonymous_owner_support() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Alice Smith | Professor | Example University",
                description="Official faculty profile.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(identity_conflict=1)


def test_repeated_later_titled_owner_identity_supports_the_primary_name() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Professor Jane Doe | Example University",
                description="Official faculty profile.",
            ),
        ),
    )

    assert [supervisor.full_name for supervisor in discovery.prospective_supervisors] == [
        "Jane Doe"
    ]


def test_primary_titled_identity_conflicting_with_person_url_is_rejected() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Professor Alice Smith | Example University",
                description="Official faculty profile.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(identity_conflict=1)


def test_generic_profile_slug_does_not_conflict_with_a_titled_identity() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/profiles/staff-profile",
                title="Professor Jane Doe | Example University",
                description="Official faculty profile.",
            ),
        ),
    )

    assert [supervisor.full_name for supervisor in discovery.prospective_supervisors] == [
        "Professor Jane Doe"
    ]


def test_repeated_abbreviated_title_does_not_extend_the_supervisor_name() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://www.sussex.ac.uk/profiles/123456",
                title=(
                    "Prof Margaret A Boden Prof Margaret | "
                    "People : AI Research Group : University of Sussex"
                ),
                description="Official academic profile.",
            ),
        ),
    )

    assert discovery.rejection_counts == SearchResultRejectionCounts()
    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [("Prof Margaret A Boden", "University of Sussex")]


def test_repeated_person_name_before_role_is_canonicalized_deterministically() -> None:
    result = _result(
        url="https://www.usc.edu/people/yan-liu",
        title="Prof. Yan Liu Yan Liu Director | University of Southern California",
        description="Official academic profile.",
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), (result,))

    assert discovery.rejection_counts == SearchResultRejectionCounts()
    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [("Prof. Yan Liu", "University of Southern California")]
    supervisor = discovery.prospective_supervisors[0]
    assert str(supervisor.discovery_provenance[0].source_url) == str(result.url)
    assert supervisor.discovery_provenance[0].originating_query == PROFILE_QUERY


def test_non_exact_repeated_person_name_is_not_canonicalized() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://www.usc.edu/people/yan-liu",
                title="Prof. Yan Liu Yan Li Director | University of Southern California",
                description="Official academic profile.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(identity_conflict=1)


def test_department_organization_label_is_not_treated_as_a_person() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://www.nyu.edu/faculty/nyu-computer-science",
                title="NYU Computer Science — NYU Computer Science Department",
                description="Academic faculty and research directory.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


@pytest.mark.parametrize("institution", ["University of St", "University of Saint"])
def test_terminal_saint_institution_fragment_is_incomplete(institution: str) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title=f"Professor Jane Doe | {institution}",
                description="Official academic profile.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(incomplete_institution=1)


def test_complete_saint_institution_name_is_preserved() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Professor Jane Doe | University of St Andrews",
                description="Official academic profile.",
            ),
        ),
    )

    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        "University of St Andrews"
    ]


def test_colon_breadcrumb_retains_only_the_strong_institution_fragment() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Professor Jane Doe | People : AI Research Group : Example University",
                description="Official academic profile.",
            ),
        ),
    )

    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        "Example University"
    ]


def test_terminal_initial_and_program_host_do_not_create_a_prospective_supervisor() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://events.example/programmes/faculty-development",
                title=(
                    "Dr. Imelda M | International Faculty Development Program by the School of AI"
                ),
                description="Dr. Imelda M is a speaker in the faculty development programme.",
            ),
        ),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 0
    assert discovery.duplicate_result_count == 0
    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(person_not_established=1)
    assert (
        discovery.rejection_counts.total + discovery.plausible_supervisor_count
        == discovery.result_count
    )


@pytest.mark.parametrize(
    "institution_label",
    [
        "International Faculty Development Programme by the School of AI",
        "Online course delivered by Example College",
        "Research workshop hosted by Example University",
        "AI governance seminar presented by Meridian School of Management",
        "Architecture conference sponsored by Northbridge University",
        "Agentic AI webinar offered by Example Institute",
        "Executive training organized by Example University",
        "Hosted by: Example University",
    ],
)
def test_activity_and_host_labels_do_not_establish_supervisor_affiliation(
    institution_label: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://events.example/speakers/imelda-mensah",
                title=f"Dr. Imelda Mensah | {institution_label}",
                description="Dr. Imelda Mensah is a researcher presenting this session.",
            ),
        ),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 0
    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)
    assert (
        discovery.rejection_counts.total + discovery.plausible_supervisor_count
        == discovery.result_count
    )


@pytest.mark.parametrize(
    "institution_label",
    [
        "Utrecht University and is part of the Human-Centered AI focus area",
        "Utrecht University as well as the HUMAN-AI strategic alliance",
        "us Copyright 2026 University of Sussex [",
    ],
)
def test_narrative_and_page_artifacts_do_not_become_institutions(
    institution_label: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/news/researcher-profile",
                title=f"Professor Jane Doe | {institution_label}",
                description="Jane Doe is a Professor researching responsible AI.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


@pytest.mark.parametrize(
    ("institution_label", "expected"),
    [
        ("University of Leicester [", "University of Leicester"),
        (
            "London · School of Hygiene & Tropical Medicine",
            "London School of Hygiene & Tropical Medicine",
        ),
    ],
)
def test_bounded_institution_punctuation_artifacts_are_normalized(
    institution_label: str,
    expected: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title=f"Professor Jane Doe | {institution_label}",
                description="Official academic profile.",
            ),
        ),
    )

    assert [item.institution for item in discovery.prospective_supervisors] == [expected]


def test_generic_institution_continues_to_owner_linked_complete_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://eps.leeds.ac.uk/computing/staff/84/professor-david-hogg",
                title="Professor David Hogg | University",
                description=("Professor David Hogg is a professor at the University of Leeds."),
            ),
        ),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 1
    assert discovery.rejection_counts == SearchResultRejectionCounts()
    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [("Professor David Hogg", "University of Leeds")]


@pytest.mark.parametrize("generic_label", ["University", "The University", "Institute"])
def test_generic_only_institution_is_not_retained(generic_label: str) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/news/david-hogg",
                title=f"Professor David Hogg | {generic_label}",
                description="Official academic biography.",
            ),
        ),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 0
    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_generic_title_does_not_borrow_another_persons_context_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/news/david-hogg",
                title="Professor David Hogg | University",
                description="Professor Alice Smith is a professor at Other University.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_titled_owner_does_not_borrow_another_persons_context_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/news/david-hogg",
                title="Professor David Hogg | Research profile",
                description="Professor Alice Smith is a professor at Other University.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_titled_owner_retains_its_explicit_context_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/news/david-hogg",
                title="Professor David Hogg | Research profile",
                description="Professor David Hogg is a professor at University of Leeds.",
            ),
        ),
    )

    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [("Professor David Hogg", "University of Leeds")]


@pytest.mark.parametrize(
    ("title", "description"),
    [
        (
            "Professor Xue Zhou | Research profile",
            "Professor Xue Zhou is a professor at University of Leicester [",
        ),
        (
            "Xue Zhou | Research profile",
            (
                "Xue Zhou's research focuses on responsible AI. "
                "Xue Zhou is a researcher at University of Leicester ["
            ),
        ),
    ],
)
def test_context_affiliation_strips_dangling_punctuation_on_every_route(
    title: str,
    description: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/xue-zhou",
                title=title,
                description=description,
            ),
        ),
    )

    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        "University of Leicester"
    ]


@pytest.mark.parametrize(
    "institution",
    [
        "Massachusetts Institute of Technology (MIT)",
        "University of Applied Sciences <UX>",
    ],
)
def test_balanced_institution_suffixes_are_preserved(institution: str) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title=f"Professor Jane Doe | {institution}",
                description="Official academic profile.",
            ),
        ),
    )

    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        institution
    ]


def test_leadership_role_is_narrowed_to_its_explicit_institution() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/liz-bacon",
                title=("Prof. Liz Bacon | Principal and Vice-Chancellor of Abertay University"),
                description="Official academic profile.",
            ),
        ),
    )

    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [("Prof. Liz Bacon", "Abertay University")]


def test_leadership_role_without_explicit_institution_type_is_not_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/news/liz-bacon",
                title="Prof. Liz Bacon | Principal and Vice-Chancellor of Abertay",
                description="Official academic biography.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_publisher_page_label_is_not_an_institution() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://heprofessional.co.uk/ai-teaching-and-learning",
                title="Professor Sam Illingworth | HE Professional",
                description="An academic article about AI in teaching and learning.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_academic_subject_phrase_does_not_override_explicit_result_owner() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url=(
                    "https://openletter.earth/stop-the-uncritical-adoption-of-ai-"
                    "technologies-in-academia"
                ),
                title="Associate Professor Intimate Computing | Research profile",
                description=(
                    "Marieke Peeters is an Associate Professor at "
                    "The Hague University of Applied Sciences."
                ),
            ),
        ),
    )

    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [("Marieke Peeters", "The Hague University of Applied Sciences")]


def test_academic_subject_phrase_without_explicit_person_is_rejected() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/topics/intimate-computing",
                title="Associate Professor Intimate Computing | Research profile",
                description="Academic research topic page.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(person_not_established=1)


@pytest.mark.parametrize(
    ("url", "title", "description", "expected_institution"),
    [
        (
            "https://www.kit.edu/profiles/jane-doe",
            "Professor Jane Doe | KIT",
            "Official academic profile.",
            "KIT",
        ),
        (
            "https://example.edu/news/ibrahim-habli",
            "Professor Ibrahim Habli | UKRI",
            "Professor Ibrahim Habli is a professor at UKRI.",
            "UKRI",
        ),
        (
            "https://example.edu/profiles/123456",
            "Dr Jane Doe | Department of Computing | University of Leeds",
            "Official academic profile.",
            "University of Leeds",
        ),
    ],
)
def test_acronyms_and_sparse_official_profiles_remain_supported(
    url: str,
    title: str,
    description: str,
    expected_institution: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url=url,
                title=title,
                description=description,
            ),
        ),
    )

    assert discovery.plausible_supervisor_count == 1
    assert discovery.rejection_counts == SearchResultRejectionCounts()
    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        expected_institution
    ]


def test_general_page_acronym_is_not_assumed_to_be_an_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url=(
                    "https://www.ukri.org/who-we-are/our-vision-and-strategy/"
                    "artificial-intelligence-centres-for-doctoral-training"
                ),
                title="Professor Ibrahim Habli | UKRI",
                description="Professor Ibrahim Habli contributes to responsible AI research.",
            ),
        ),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 0
    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_latest_live_shapes_have_exact_rejection_accounting() -> None:
    results = (
        _result(
            url="https://example.edu/news/david-hogg",
            title="Professor David Hogg | University",
            description="Official academic biography.",
        ),
        _result(
            url="https://heprofessional.co.uk/ai-teaching-and-learning",
            title="Professor Sam Illingworth | HE Professional",
            description="Academic publisher page.",
        ),
        _result(
            url="https://example.edu/topics/intimate-computing",
            title="Associate Professor Intimate Computing | Research profile",
            description="Academic research topic page.",
        ),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), results)

    assert discovery.result_count == 3
    assert discovery.plausible_supervisor_count == 0
    assert discovery.duplicate_result_count == 0
    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        person_not_established=1,
        institution_not_established=2,
    )
    assert (
        discovery.rejection_counts.total + discovery.plausible_supervisor_count
        == discovery.result_count
    )


def test_school_phrase_alone_on_event_page_does_not_establish_dr_academic_context() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://events.example/speakers/imelda-mensah",
                title="Dr. Imelda Mensah | School of AI",
                description="Event speaker biography.",
            ),
        ),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 0
    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


@pytest.mark.parametrize(
    ("url", "title", "expected_name", "expected_institution"),
    [
        (
            "https://example.edu/people/imelda-m-mensah",
            "Dr. Imelda M Mensah | Department of Computing | Example University",
            "Dr. Imelda M Mensah",
            "Example University",
        ),
        (
            "https://example.edu/people/li-wei",
            "Professor Li Wei | School of Computing | Meridian School of Management",
            "Professor Li Wei",
            "Meridian School of Management",
        ),
        (
            "https://example.edu/people/amina-bello",
            (
                "Dr Amina Bello | Department of Information Systems | "
                "London School of Economics and Political Science"
            ),
            "Dr Amina Bello",
            "London School of Economics and Political Science",
        ),
        (
            "https://example.edu/people/jane-doe",
            "Dr Jane Doe | Associate Professor at Example University",
            "Dr Jane Doe",
            "Example University",
        ),
    ],
)
def test_complete_names_and_standalone_institutions_remain_supported(
    url: str,
    title: str,
    expected_name: str,
    expected_institution: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (_result(url=url, title=title, description="Official profile."),),
    )

    assert discovery.result_count == 1
    assert discovery.plausible_supervisor_count == 1
    assert discovery.duplicate_result_count == 0
    assert discovery.rejection_counts == SearchResultRejectionCounts()
    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [(expected_name, expected_institution)]


@pytest.mark.parametrize(
    "description",
    [
        "José van Dijk's research focuses on responsible AI.",
        "Jose van Dijk's research focuses on responsible AI.",
    ],
)
def test_ascii_profile_context_matches_the_accented_display_identity(
    description: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jose-van-dijk",
                title="José van Dijk | Example University",
                description=description,
            ),
        ),
    )

    assert [supervisor.full_name for supervisor in discovery.prospective_supervisors] == [
        "José van Dijk"
    ]


@pytest.mark.parametrize(
    ("url", "title_name", "context_name"),
    [
        ("https://example.edu/people/jose-van-dijk", "José van Dijk", "Jose van Dijk"),
        ("https://example.edu/people/jane-a-doe", "Jane A Doe", "Jane A. Doe"),
        (
            "https://example.edu/people/anne-marie-smith",
            "Anne-Marie Smith",
            "Anne Marie Smith",
        ),
        (
            "https://example.edu/people/jane-oconnor",
            "Jane O'Connor",
            "Jane O'Connor",
        ),
        (
            "https://example.edu/people/jan-van-der-meer",
            "Jan van der Meer",
            "Jan van der Meer",
        ),
    ],
)
def test_context_identity_variants_can_supply_owner_linked_affiliation(
    url: str,
    title_name: str,
    context_name: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url=url,
                title=f"{title_name} | Research profile",
                description=(
                    f"{context_name}'s research focuses on responsible AI. "
                    f"{context_name} is a researcher at Example University."
                ),
            ),
        ),
    )

    assert [
        (supervisor.full_name, supervisor.institution)
        for supervisor in discovery.prospective_supervisors
    ] == [(title_name, "Example University")]


@pytest.mark.parametrize(
    "description",
    [
        (
            "Jane Doe's research focuses on enterprise architecture. "
            "Professor Alice Smith works at Example University."
        ),
        (
            "Jane Doe's research focuses on enterprise architecture in collaboration "
            "with Example University."
        ),
        (
            "Jane Doe's research focuses on enterprise architecture. "
            "Jane Doe is a researcher in collaboration with Alice Smith "
            "at Example University."
        ),
        (
            "Jane Doe's research focuses on enterprise architecture. "
            "Jane Doe is a researcher in a project with Alice Smith at Example University."
        ),
    ],
)
def test_new_profile_route_never_borrows_an_unlinked_institution(description: str) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Research profile",
                description=description,
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_new_profile_route_accepts_an_owner_linked_context_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Research profile",
                description=(
                    "Jane Doe's research focuses on enterprise architecture. "
                    "Jane Doe is a researcher at Example University."
                ),
            ),
        ),
    )

    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        "Example University"
    ]


def test_owner_clause_with_another_academic_does_not_lend_their_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Research profile",
                description=(
                    "Jane Doe's research focuses on enterprise architecture. "
                    "Jane Doe works with Professor Alice Smith at Example University."
                ),
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_named_title_co_mention_does_not_supply_the_owner_institution() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title=("Jane Doe | Professor Alice Smith at Other University | Research profile"),
                description="Jane Doe's research focuses on enterprise architecture.",
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_owner_linked_affiliation_stops_before_research_activity() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Research profile",
                description=(
                    "Jane Doe's research focuses on enterprise architecture. "
                    "Jane Doe is a researcher at Example University researching AI governance."
                ),
            ),
        ),
    )

    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        "Example University"
    ]


@pytest.mark.parametrize(
    "affiliation_clause",
    [
        (
            "Jane Doe is a researcher at Example University and teaches students "
            "from Other University."
        ),
        ("Jane Doe is a researcher at Example University and collaborates with Other University."),
    ],
)
def test_owner_affiliation_uses_the_first_licensed_institution_only(
    affiliation_clause: str,
) -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Research profile",
                description=(
                    "Jane Doe's research focuses on enterprise architecture. " + affiliation_clause
                ),
            ),
        ),
    )

    assert [supervisor.institution for supervisor in discovery.prospective_supervisors] == [
        "Example University"
    ]


def test_guest_speaking_does_not_establish_current_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Research profile",
                description=(
                    "Jane Doe's research focuses on enterprise architecture. "
                    "Jane Doe is a guest speaker at Example University."
                ),
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_scholarly_support_outside_the_bounded_description_is_ignored() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=(
                    ("x" * 1_001) + " Jane Doe's research focuses on enterprise architecture."
                ),
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )


def test_supported_profile_owner_is_retained_when_a_collaborator_is_also_named() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=(
                    "Jane Doe's research focuses on enterprise architecture. "
                    "Recent work with Professor Alice Smith examines AI governance."
                ),
            ),
        ),
    )

    assert [supervisor.full_name for supervisor in discovery.prospective_supervisors] == [
        "Jane Doe"
    ]
    assert discovery.plausible_supervisor_count == 1
    assert discovery.rejection_counts == SearchResultRejectionCounts()


def test_only_a_different_supported_academic_remains_an_identity_conflict() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=(
                    "Professor Alice Smith researches enterprise architecture "
                    "at Example University."
                ),
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(identity_conflict=1)


def test_identity_linked_research_support_does_not_replace_complete_affiliation() -> None:
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Research profile",
                description=(
                    "Jane Doe's research focuses on enterprise architecture and AI governance."
                ),
            ),
        ),
    )

    assert discovery.prospective_supervisors == ()
    assert discovery.rejection_counts == SearchResultRejectionCounts(institution_not_established=1)


def test_adversarial_batch_has_exact_result_and_rejection_accounting() -> None:
    results = (
        _result(
            url="https://example.edu/people/jane-doe",
            title="Jane Doe | Example University",
            description="Jane Doe's research focuses on enterprise architecture.",
        ),
        _result(
            url="https://example.edu/people/alan-green",
            title="Alan Green | Example University",
            description="Research focuses on enterprise architecture.",
        ),
        _result(
            url="https://example.edu/people/digital-transformation",
            title="Digital Transformation | Example University",
            description="Digital transformation research supports enterprise systems.",
        ),
        _result(
            url="https://example.edu/people/john-brown",
            title="John Brown | Example University",
            description="Professor Alice Smith researches systems at Example University.",
        ),
        _result(
            url="https://example.edu/people/mary-stone",
            title="Mary Stone | Research profile",
            description="Mary Stone's research focuses on AI governance.",
        ),
    )

    discovery = SupervisorDiscoveryAgent().discover(_search_plan(), results)

    assert discovery.result_count == 5
    assert discovery.plausible_supervisor_count == 1
    assert discovery.duplicate_result_count == 0
    assert [supervisor.full_name for supervisor in discovery.prospective_supervisors] == [
        "Jane Doe"
    ]
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=2,
        identity_conflict=1,
        institution_not_established=1,
    )
    assert (
        discovery.rejection_counts.total + discovery.plausible_supervisor_count
        == discovery.result_count
    )


def test_discovery_output_omits_bounded_context_and_ambiguous_terminology() -> None:
    private_marker = "private-context-marker-6b8677"
    discovery = SupervisorDiscoveryAgent().discover(
        _search_plan(),
        (
            _result(
                url="https://example.edu/people/jane-doe",
                title="Jane Doe | Example University",
                description=(
                    f"Jane Doe's research focuses on enterprise architecture. {private_marker}"
                ),
            ),
        ),
    )

    serialized = json.dumps(discovery.model_dump(mode="json")).casefold()
    ambiguous_supervisor_term = " ".join(("supervisor", "candidate"))

    assert private_marker not in serialized
    assert ambiguous_supervisor_term not in serialized
    assert "admission probability" not in serialized
    assert "availability" not in serialized
