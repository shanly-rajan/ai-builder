"""Unit tests for typed Research Planning Agent orchestration."""

import pytest
from pydantic import ValidationError

from scholarpath.agents import (
    PlanningModelOutputError,
    ResearchPlanningAgent,
    StructuredSearchPlanResponse,
)
from scholarpath.domain import CandidatePreferenceRevision, SearchSourceType
from tests.fakes import FakePlanningModel, make_valid_planning_response
from tests.fixtures import make_candidate_profile


def test_candidate_profile_and_remembered_preferences_map_to_planning_input() -> None:
    profile = make_candidate_profile(
        proposed_research_statement="A distinctive synthetic doctoral research statement.",
        research_topics=("topic alpha", "topic beta"),
        preferred_study_modes=("hybrid",),
        preferred_research_orientation="applied",
        methodological_interests=("design science",),
    )
    remembered_preferences = (
        CandidatePreferenceRevision(preferred_regions=("South Africa",)),
        CandidatePreferenceRevision(exclusions=("fully residential programmes",)),
    )
    model = FakePlanningModel()
    agent = ResearchPlanningAgent(model)

    agent.plan(
        profile,
        remembered_preferences,
        target_regions=("South Africa", "Netherlands"),
        exclusions=("fully residential programmes",),
    )

    assert model.call_count == 1
    planning_input = model.inputs[0]
    assert planning_input.proposed_research_statement == profile.proposed_research_statement
    assert planning_input.research_topics == profile.research_topics
    assert planning_input.preferred_study_modes == profile.preferred_study_modes
    assert planning_input.preferred_research_orientation == profile.preferred_research_orientation
    assert planning_input.methodological_interests == profile.methodological_interests
    assert planning_input.remembered_candidate_preferences == remembered_preferences
    assert planning_input.target_regions == ("South Africa", "Netherlands")
    assert planning_input.exclusions == ("fully residential programmes",)
    assert "candidate_id" not in type(planning_input).model_fields


def test_valid_structured_response_becomes_an_executable_search_plan() -> None:
    response = make_valid_planning_response()
    model = FakePlanningModel((response,))

    plan = ResearchPlanningAgent(model).plan(
        make_candidate_profile(),
        (),
        target_regions=("South Africa",),
        exclusions=("fully residential programmes",),
    )

    assert len(plan.search_queries) == 4
    assert tuple(item.query for item in plan.search_queries) == tuple(
        item.query for item in response.search_queries
    )
    assert tuple(item.purpose for item in plan.search_queries) == tuple(
        item.purpose for item in response.search_queries
    )
    assert {
        source_type for query in plan.search_queries for source_type in query.target_source_types
    } == set(SearchSourceType)
    assert plan.expanded_research_concepts == tuple(response.expanded_research_concepts)
    assert plan.target_regions == ("South Africa",)
    assert plan.rationale == response.rationale
    assert type(plan).model_validate_json(plan.model_dump_json()) == plan


def test_structured_response_rejects_an_empty_query_list() -> None:
    payload = make_valid_planning_response().model_dump(mode="python")
    payload["search_queries"] = []

    with pytest.raises(ValidationError, match="four to eight search queries"):
        StructuredSearchPlanResponse.model_validate(payload)


def test_structured_response_rejects_normalized_duplicate_queries() -> None:
    payload = make_valid_planning_response().model_dump(mode="python")
    search_queries = payload["search_queries"]
    assert isinstance(search_queries, list)
    first_query = search_queries[0]
    second_query = search_queries[1]
    assert isinstance(first_query, dict)
    assert isinstance(second_query, dict)
    second_query["query"] = f"  {str(first_query['query']).upper()}  "

    with pytest.raises(ValidationError, match="Search queries must be distinct"):
        StructuredSearchPlanResponse.model_validate(payload)


@pytest.mark.parametrize(
    ("query", "message"),
    (
        (
            "site:.edu OR site:.ac.uk enterprise architecture professor",
            "at most one site: filter",
        ),
        (
            "professor AND architecture OR governance NOT healthcare",
            "at most two explicit Boolean operators",
        ),
        (
            'professor "enterprise architecture" "responsible AI"',
            "at most one quoted phrase",
        ),
    ),
)
def test_structured_response_rejects_overconstrained_query_syntax(
    query: str,
    message: str,
) -> None:
    payload = make_valid_planning_response().model_dump(mode="python")
    search_queries = payload["search_queries"]
    assert isinstance(search_queries, list)
    first_query = search_queries[0]
    assert isinstance(first_query, dict)
    first_query["query"] = query

    with pytest.raises(ValidationError, match=message):
        StructuredSearchPlanResponse.model_validate(payload)


def test_structured_response_accepts_bounded_provider_portable_query_syntax() -> None:
    payload = make_valid_planning_response().model_dump(mode="python")
    search_queries = payload["search_queries"]
    assert isinstance(search_queries, list)
    first_query = search_queries[0]
    assert isinstance(first_query, dict)
    first_query["query"] = 'site:example.edu professor "enterprise architecture" AND governance'

    response = StructuredSearchPlanResponse.model_validate(payload)

    assert response.search_queries[0].query == first_query["query"]


def test_natural_language_conjunctions_are_not_treated_as_boolean_operators() -> None:
    payload = make_valid_planning_response().model_dump(mode="python")
    search_queries = payload["search_queries"]
    assert isinstance(search_queries, list)
    first_query = search_queries[0]
    assert isinstance(first_query, dict)
    first_query["query"] = "architecture and governance or resilience and responsible innovation"

    response = StructuredSearchPlanResponse.model_validate(payload)

    assert response.search_queries[0].query == first_query["query"]


def test_malformed_output_is_retried_once_then_a_valid_response_is_accepted() -> None:
    model = FakePlanningModel(
        (
            PlanningModelOutputError("synthetic malformed output"),
            make_valid_planning_response(),
        )
    )

    plan = ResearchPlanningAgent(model).plan(
        make_candidate_profile(),
        (),
        target_regions=("United Kingdom",),
        exclusions=(),
    )

    assert model.call_count == 2
    assert len(plan.search_queries) == 4
    assert model.inputs[0] == model.inputs[1]


def test_overconstrained_query_output_is_retried_once_then_repaired() -> None:
    valid_response = make_valid_planning_response()
    overconstrained_query = valid_response.search_queries[0].model_copy(
        update={"query": "site:.edu OR site:.ac.uk professor architecture"}
    )
    invalid_response = valid_response.model_copy(
        update={
            "search_queries": [
                overconstrained_query,
                *valid_response.search_queries[1:],
            ]
        }
    )
    model = FakePlanningModel((invalid_response, valid_response))

    plan = ResearchPlanningAgent(model).plan(
        make_candidate_profile(),
        (),
        target_regions=("South Africa",),
        exclusions=(),
    )

    assert model.call_count == 2
    assert plan.search_queries[0].query == valid_response.search_queries[0].query
    assert model.inputs[0] == model.inputs[1]
