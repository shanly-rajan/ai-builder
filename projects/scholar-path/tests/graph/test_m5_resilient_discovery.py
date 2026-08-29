"""Graph scenarios for M5's bounded You.com-to-Tavily discovery policy."""

from typing import cast

import pytest
from pydantic import SecretStr

from scholarpath.agents import PlanningSearchQueryResponse
from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
    TavilySearchSettings,
)
from scholarpath.domain import (
    CandidatePreferenceRevision,
    SearchResult,
    SearchSourceType,
)
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRequestMoreResponse,
    DiscoveryPolicy,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    build_walking_skeleton_fixtures,
    default_review_decision,
    run_scholarpath_graph,
)
from scholarpath.tools import (
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
    SupervisorSearchPort,
    SupervisorSearchTimeoutError,
)
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_fake_search_outcomes,
    make_valid_planning_response,
)


def _queries() -> tuple[str, ...]:
    return tuple(item.query for item in make_valid_planning_response().search_queries)


def _empty_outcomes() -> dict[str, tuple[SearchResult, ...]]:
    return {query: () for query in _queries()}


def _retryable_error(provider: SearchProvider) -> SearchProviderError:
    return SearchProviderError(
        "Synthetic provider failure whose details must not escape into graph state.",
        provider=provider,
        category=SearchErrorCategory.PROVIDER,
        retryable=True,
    )


def _approval_response() -> CandidateApproveResponse:
    return CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )


def _as_state(output: ScholarPathState | dict[str, object]) -> ScholarPathState:
    return cast(ScholarPathState, output)


def _run(
    you_search: SupervisorSearchPort,
    tavily_search: SupervisorSearchPort,
    *,
    policy: DiscoveryPolicy | None = None,
    failure_mode: DiscoveryFailureMode = DiscoveryFailureMode.OFF,
    planning_model: FakePlanningModel | None = None,
) -> ScholarPathState:
    return _as_state(
        run_scholarpath_graph(
            GraphFixtureConfig(discovery_policy=policy or DiscoveryPolicy()),
            thread_id="legacy-m5-discovery",
            candidate_review_responses=(_approval_response(),),
            planning_model=planning_model or FakePlanningModel(),
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            supervisor_search=you_search,
            tavily_search=tavily_search,
            content_extractor=FakeContentExtraction(),
            evidence_model=FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=failure_mode,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        ),
    )


def test_successful_you_route_does_not_call_tavily() -> None:
    you_search = FakeSupervisorSearch()
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert tavily_search.calls == []
    assert final_state["fallback_search_used"] is False
    assert {attempt.provider_used for attempt in final_state["search_attempts"]} == {
        SearchProvider.YOU
    }
    successful_attempts = tuple(
        attempt for attempt in final_state["search_attempts"] if attempt.error_category is None
    )
    assert successful_attempts
    assert all(attempt.rejection_counts is not None for attempt in successful_attempts)
    assert all(
        attempt.rejection_counts is not None
        and attempt.rejection_counts.total + attempt.plausible_supervisor_count
        == attempt.result_count
        for attempt in successful_attempts
    )


def test_realistic_fallback_summaries_reach_downstream_evidence_processing() -> None:
    query = _queries()[0]
    raw_profiles = build_walking_skeleton_fixtures().raw_search_results[:6]
    realistic_results = tuple(
        SearchResult(
            url=profile.profile_url,
            title=f"{profile.full_name} | Associate Professor | {profile.institution}",
            description=(
                f"Academic research profile for {profile.full_name}. Current faculty member "
                f"at {profile.institution}."
            ),
            originating_query=query,
        )
        for profile in raw_profiles
    )
    tavily_outcomes = _empty_outcomes()
    tavily_outcomes[query] = realistic_results

    final_state = _run(
        FakeSupervisorSearch(_empty_outcomes()),
        FakeSupervisorSearch(tavily_outcomes),
    )

    assert final_state["fallback_search_used"] is True
    assert len(final_state["prospective_supervisors"]) == 6
    assert "deduplicate_supervisors" in final_state["execution_log"]
    assert "extract_supervisor_evidence" in final_state["execution_log"]


def test_successful_you_route_does_not_construct_or_validate_tavily(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_tavily_adapter_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("A healthy You.com route must not construct Tavily")

    monkeypatch.setattr(
        "scholarpath.graph.workflow.TavilySearchAdapter",
        fail_if_tavily_adapter_is_constructed,
    )

    final_state = _as_state(
        run_scholarpath_graph(
            thread_id="legacy-m5-lazy-tavily",
            candidate_review_responses=(_approval_response(),),
            planning_model=FakePlanningModel(),
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            supervisor_search=FakeSupervisorSearch(),
            content_extractor=FakeContentExtraction(),
            evidence_model=FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            tavily_settings=TavilySearchSettings(api_key=None),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=DiscoveryFailureMode.OFF,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        )
    )

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert final_state["fallback_search_used"] is False


def test_missing_tavily_key_is_typed_only_when_fallback_is_routed() -> None:
    final_state = _as_state(
        run_scholarpath_graph(
            thread_id="legacy-m5-missing-tavily-key",
            candidate_review_responses=(_approval_response(),),
            planning_model=FakePlanningModel(),
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            supervisor_search=FakeSupervisorSearch(_empty_outcomes()),
            content_extractor=FakeContentExtraction(),
            evidence_model=FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            tavily_settings=TavilySearchSettings(api_key=None),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=DiscoveryFailureMode.OFF,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        )
    )

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["fallback_search_used"] is True
    assert final_state["search_attempts"][-1].provider_used is SearchProvider.TAVILY
    assert final_state["search_attempts"][-1].error_category is SearchErrorCategory.AUTHENTICATION


def test_lazy_tavily_adapter_is_constructed_once_and_reused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fallback_search = FakeSupervisorSearch()
    construction_count = 0

    def construct_fake_tavily_adapter(configuration: object) -> FakeSupervisorSearch:
        nonlocal construction_count
        del configuration
        construction_count += 1
        return fallback_search

    monkeypatch.setattr(
        "scholarpath.graph.workflow.TavilySearchAdapter",
        construct_fake_tavily_adapter,
    )

    final_state = _as_state(
        run_scholarpath_graph(
            thread_id="legacy-m5-tavily-reuse",
            candidate_review_responses=(_approval_response(),),
            planning_model=FakePlanningModel(),
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            supervisor_search=FakeSupervisorSearch(_empty_outcomes()),
            content_extractor=FakeContentExtraction(),
            evidence_model=FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            tavily_settings=TavilySearchSettings(api_key=SecretStr("not-a-real-tavily-secret")),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=DiscoveryFailureMode.OFF,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        )
    )

    assert construction_count == 1
    assert len(fallback_search.calls) == 3
    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_you_timeout_is_retried_once_before_continuing() -> None:
    outcomes = make_fake_search_outcomes()
    first_query = _queries()[0]
    you_search = FakeSupervisorSearch(
        outcomes,
        scripts={
            first_query: [
                SupervisorSearchTimeoutError("Synthetic timeout."),
                outcomes[first_query],
            ]
        },
    )
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    first_query_attempts = [
        attempt
        for attempt in final_state["search_attempts"]
        if attempt.provider_used is SearchProvider.YOU and attempt.query == first_query
    ]
    assert [attempt.attempt_number for attempt in first_query_attempts] == [1, 2]
    assert first_query_attempts[0].error_category is SearchErrorCategory.TIMEOUT
    assert first_query_attempts[1].error_category is None
    assert final_state["retry_counts"]["discovery"] == 1
    assert tavily_search.calls == []
    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_you_retry_failure_routes_to_tavily() -> None:
    first_query = _queries()[0]
    you_search = FakeSupervisorSearch(
        scripts={
            first_query: [
                SupervisorSearchTimeoutError("First synthetic timeout."),
                SupervisorSearchTimeoutError("Second synthetic timeout."),
            ]
        }
    )
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    assert you_search.calls == [first_query, first_query]
    assert len(tavily_search.calls) == 3
    assert final_state["fallback_search_used"] is True
    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_empty_you_results_route_to_tavily() -> None:
    you_search = FakeSupervisorSearch(_empty_outcomes())
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    assert you_search.calls == list(_queries())
    assert tavily_search.calls
    assert final_state["fallback_search_used"] is True
    assert len(final_state["prospective_supervisors"]) >= 5
    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_tavily_budget_prioritizes_productive_you_query_slots() -> None:
    base_response = make_valid_planning_response()
    extra_queries = (
        PlanningSearchQueryResponse(
            query="enterprise systems academic expertise university",
            purpose="Find additional official academic profiles.",
            target_source_types=[SearchSourceType.OFFICIAL_UNIVERSITY_PROFILE],
        ),
        PlanningSearchQueryResponse(
            query="responsible technology faculty research centre",
            purpose="Find additional department and research-group profiles.",
            target_source_types=[SearchSourceType.DEPARTMENT_OR_RESEARCH_GROUP],
        ),
    )
    planned_response = type(base_response).model_validate(
        {
            **base_response.model_dump(),
            "search_queries": [*base_response.search_queries, *extra_queries],
        }
    )
    queries = tuple(item.query for item in planned_response.search_queries)
    fixture_results = tuple(
        result for batch in make_fake_search_outcomes().values() for result in batch
    )
    you_outcomes: dict[str, tuple[SearchResult, ...]] = {query: () for query in queries}
    you_outcomes[queries[3]] = tuple(
        result.model_copy(update={"originating_query": queries[3]})
        for result in fixture_results[:2]
    )
    you_outcomes[queries[4]] = tuple(
        result.model_copy(update={"originating_query": queries[4]})
        for result in fixture_results[2:4]
    )
    you_search = FakeSupervisorSearch(you_outcomes)
    tavily_search = FakeSupervisorSearch({query: () for query in queries})

    final_state = _run(
        you_search,
        tavily_search,
        policy=DiscoveryPolicy(maximum_tavily_fallback_count=4),
        planning_model=FakePlanningModel((planned_response,)),
    )

    assert tavily_search.calls == [queries[3], queries[4], queries[0], queries[1]]
    assert len(tavily_search.calls) == 4
    assert len(final_state["prospective_supervisors"]) == 4
    assert final_state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE


def test_duplicate_heavy_you_results_route_to_tavily() -> None:
    ordinary_outcomes = make_fake_search_outcomes()
    base_results = tuple(result for query in _queries() for result in ordinary_outcomes[query])[:5]
    result_patterns = (
        (0, 1, 2, 3),
        (4, 0, 0, 0),
        (0, 0, 0, 0),
        (0, 0, 0, 0),
    )
    duplicate_outcomes = {
        query: tuple(
            base_results[index].model_copy(update={"originating_query": query})
            for index in result_patterns[query_index]
        )
        for query_index, query in enumerate(_queries())
    }
    you_search = FakeSupervisorSearch(duplicate_outcomes)
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    assert tavily_search.calls
    assert final_state["fallback_search_used"] is True
    assert len(final_state["prospective_supervisors"]) >= 5
    you_attempts = [
        attempt
        for attempt in final_state["search_attempts"]
        if attempt.provider_used is SearchProvider.YOU
    ]
    assert sum(attempt.plausible_supervisor_count for attempt in you_attempts) == 16


def test_nonretryable_authentication_error_stops_without_tavily() -> None:
    first_query = _queries()[0]
    authentication_error = SearchProviderError(
        "Synthetic authentication failure.",
        provider=SearchProvider.YOU,
        category=SearchErrorCategory.AUTHENTICATION,
        retryable=False,
        status_code=401,
    )
    you_search = FakeSupervisorSearch(scripts={first_query: [authentication_error]})
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    assert you_search.calls == [first_query]
    assert tavily_search.calls == []
    assert final_state["fallback_search_used"] is False
    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["search_attempts"][0].error_category is SearchErrorCategory.AUTHENTICATION
    assert final_state["tool_errors"][-1].code == "supervisor_discovery_stopped"


def test_discovery_contract_failure_preserves_provider_result_count() -> None:
    first_query = _queries()[0]
    mismatched_result = make_fake_search_outcomes()[first_query][0].model_copy(
        update={"originating_query": "query not present in the SearchPlan"}
    )
    you_search = FakeSupervisorSearch({first_query: (mismatched_result,)})
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    assert you_search.calls == [first_query]
    assert tavily_search.calls == []
    assert final_state["search_attempts"][0].result_count == 1
    assert final_state["search_attempts"][0].error_category is SearchErrorCategory.RESPONSE_CONTRACT
    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED


def test_partial_you_results_survive_a_later_provider_failure() -> None:
    queries = _queries()
    outcomes = make_fake_search_outcomes()
    you_outcomes: dict[str, tuple[SearchResult, ...] | Exception] = {
        **{query: outcomes[query] for query in queries[:3]},
        queries[3]: _retryable_error(SearchProvider.YOU),
    }
    you_search = FakeSupervisorSearch(you_outcomes)
    tavily_search = FakeSupervisorSearch(_empty_outcomes())

    final_state = _run(you_search, tavily_search)

    assert len(final_state["prospective_supervisors"]) == 6
    assert len(final_state["raw_search_results"]) == 6
    assert final_state["fallback_search_used"] is True
    assert len(tavily_search.calls) == 1
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert any(error.code == "you_search_provider" for error in final_state["tool_errors"])


def test_both_providers_failing_ends_with_clear_recoverable_status() -> None:
    final_state = _run(
        FakeSupervisorSearch(),
        FakeSupervisorSearch(),
        failure_mode=DiscoveryFailureMode.BOTH_PROVIDERS_RETRYABLE_ERROR,
    )

    assert final_state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE
    assert final_state["execution_log"][-1] == "enough_supervisors_found"
    assert final_state["fallback_search_used"] is True
    assert final_state["prospective_supervisors"] == []
    assert final_state["tool_errors"][-1].code == "supervisor_discovery_incomplete"
    assert final_state["tool_errors"][-1].recoverable is True


def test_retry_limits_bound_all_provider_calls() -> None:
    policy = DiscoveryPolicy(
        maximum_you_retry_count=1,
        maximum_tavily_fallback_count=2,
    )
    first_query = _queries()[0]
    you_search = FakeSupervisorSearch(
        scripts={
            first_query: [
                SupervisorSearchTimeoutError("First synthetic timeout."),
                SupervisorSearchTimeoutError("Second synthetic timeout."),
            ]
        }
    )
    tavily_search = FakeSupervisorSearch(
        {query: _retryable_error(SearchProvider.TAVILY) for query in _queries()}
    )

    final_state = _run(you_search, tavily_search, policy=policy)

    assert len(you_search.calls) == 2
    assert len(tavily_search.calls) == 2
    assert len(final_state["search_attempts"]) == 4
    assert final_state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE


def test_search_attempt_state_records_required_routing_fields() -> None:
    you_search = FakeSupervisorSearch(_empty_outcomes())
    tavily_search = FakeSupervisorSearch()

    final_state = _run(you_search, tavily_search)

    assert final_state["search_attempts"]
    for attempt in final_state["search_attempts"]:
        serialized = attempt.model_dump(mode="json")
        assert {
            "provider_used",
            "query",
            "attempt_number",
            "result_count",
            "error_category",
        } <= serialized.keys()
    assert final_state["fallback_search_used"] is True


def test_request_more_evaluates_duplicate_quality_within_the_new_round() -> None:
    ordinary_outcomes = make_fake_search_outcomes()
    repeated_result = ordinary_outcomes[_queries()[0]][0]
    scripts: dict[str, list[tuple[SearchResult, ...] | Exception]] = {
        query: [
            ordinary_outcomes[query],
            (repeated_result.model_copy(update={"originating_query": query}),),
        ]
        for query in _queries()
    }
    approval = _approval_response()
    request_more = CandidateRequestMoreResponse(
        action="request_more",
        revised_preferences=CandidatePreferenceRevision(
            preferred_regions=("Netherlands",),
        ),
    )
    config = GraphFixtureConfig(
        discovery_policy=DiscoveryPolicy(maximum_tavily_fallback_count=1),
    )
    you_search = FakeSupervisorSearch(scripts=scripts)
    tavily_search = FakeSupervisorSearch(_empty_outcomes())

    final_state = _as_state(
        run_scholarpath_graph(
            config,
            thread_id="legacy-m5-request-more",
            candidate_review_responses=(request_more, approval),
            planning_model=FakePlanningModel(),
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            supervisor_search=you_search,
            tavily_search=tavily_search,
            content_extractor=FakeContentExtraction(),
            evidence_model=FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=FakeIndependentReviewModel(),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                discovery_failure_mode=DiscoveryFailureMode.OFF,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        )
    )

    assert final_state["discovery_round"] == 2
    assert len(tavily_search.calls) == 1
    assert final_state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE
    assert {result.discovery_round for result in final_state["raw_search_results"]} == {1, 2}
    assert len(final_state["prospective_supervisors"]) == 8
