"""Offline transport-to-domain integration for the M11.3 discovery repair."""

import httpx
from pydantic import SecretStr

from scholarpath.agents import SupervisorDiscoveryAgent
from scholarpath.config import YouSearchConfiguration
from scholarpath.domain import PlannedSearchQuery, SearchPlan, SearchResultRejectionCounts
from scholarpath.tools import YouSearchAdapter
from tests.fakes import make_valid_planning_response


def test_you_results_flow_through_conservative_academic_profile_recognition() -> None:
    """Normalize provider data, retain one supported person, and reject one topic page."""
    planning_response = make_valid_planning_response()
    search_plan = SearchPlan(
        search_queries=tuple(
            PlannedSearchQuery(
                query=item.query,
                purpose=item.purpose,
                target_source_types=tuple(item.target_source_types),
            )
            for item in planning_response.search_queries
        ),
        expanded_research_concepts=tuple(planning_response.expanded_research_concepts),
        target_regions=("United Kingdom",),
        rationale=planning_response.rationale,
    )
    query = search_plan.search_queries[0].query

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        return httpx.Response(
            200,
            request=request,
            json={
                "results": {
                    "web": [
                        {
                            "url": "https://example.edu/en/persons/jane-doe",
                            "title": "Jane Doe | Example University",
                            "description": (
                                "Jane Doe's research focuses on enterprise architecture "
                                "and responsible AI governance."
                            ),
                        },
                        {
                            "url": "https://example.edu/people/digital-transformation",
                            "title": "Digital Transformation | Example University",
                            "description": (
                                "Digital transformation research supports enterprise systems."
                            ),
                        },
                    ]
                }
            },
        )

    configuration = YouSearchConfiguration.model_validate(
        {
            "api_key": SecretStr("not-a-live-secret"),
            "endpoint": "https://ydc-index.io/v1/search",
            "timeout_seconds": 3,
            "result_count": 10,
        }
    )
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        normalized_results = YouSearchAdapter(configuration, client=client).search(query)

    discovery = SupervisorDiscoveryAgent().discover(search_plan, normalized_results)

    assert discovery.result_count == 2
    assert discovery.plausible_supervisor_count == 1
    assert discovery.rejection_counts == SearchResultRejectionCounts(
        academic_context_not_established=1
    )
    assert len(discovery.prospective_supervisors) == 1
    supervisor = discovery.prospective_supervisors[0]
    assert supervisor.full_name == "Jane Doe"
    assert supervisor.institution == "Example University"
    assert str(supervisor.profile_url) == "https://example.edu/en/persons/jane-doe"
    assert supervisor.discovery_query == query
    assert {
        (str(item.source_url), item.originating_query) for item in supervisor.discovery_provenance
    } == {("https://example.edu/en/persons/jane-doe", query)}
