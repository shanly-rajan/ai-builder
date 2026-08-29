"""Unit tests for deterministic M5 Supervisor discovery routing."""

import pytest
from pydantic import ValidationError

from scholarpath.domain import SearchResultRejectionCounts
from scholarpath.graph.discovery import (
    DiscoveryPolicy,
    DiscoveryStoppingCondition,
    DiscoveryTimeoutBehavior,
    SearchAttempt,
    SupervisorDiscoveryRoute,
    prioritize_tavily_fallback_queries,
    route_after_supervisor_discovery,
    select_tavily_fallback_queries,
)
from scholarpath.tools import SearchErrorCategory, SearchProvider
from tests.fixtures import make_search_plan


def _attempt(
    *,
    provider: SearchProvider = SearchProvider.YOU,
    query: str = "enterprise architecture professor university profile",
    attempt_number: int = 1,
    result_count: int = 8,
    plausible_count: int = 6,
    error_category: SearchErrorCategory | None = None,
    retryable: bool = False,
    discovery_round: int = 1,
) -> SearchAttempt:
    if error_category is not None:
        result_count = 0
        plausible_count = 0
    return SearchAttempt(
        provider_used=provider,
        query=query,
        attempt_number=attempt_number,
        result_count=result_count,
        plausible_supervisor_count=plausible_count,
        error_category=error_category,
        retryable=retryable,
        discovery_round=discovery_round,
    )


def _route(
    attempts: tuple[SearchAttempt, ...],
    *,
    policy: DiscoveryPolicy | None = None,
    unique_count: int = 5,
    fallback_used: bool = False,
    discovery_round: int | None = 1,
) -> SupervisorDiscoveryRoute:
    return route_after_supervisor_discovery(
        policy or DiscoveryPolicy(),
        attempts,
        unique_supervisor_count=unique_count,
        fallback_search_used=fallback_used,
        discovery_round=discovery_round,
    )


def test_search_attempt_is_frozen_and_serializes_provider_audit_data() -> None:
    attempt = _attempt()

    assert attempt.model_dump(mode="json") == {
        "provider_used": "you.com",
        "query": "enterprise architecture professor university profile",
        "attempt_number": 1,
        "result_count": 8,
        "plausible_supervisor_count": 6,
        "rejection_counts": None,
        "error_category": None,
        "retryable": False,
        "discovery_round": 1,
    }
    with pytest.raises(ValidationError, match="frozen"):
        attempt.__setattr__("result_count", 9)


def test_successful_search_attempt_persists_complete_rejection_taxonomy() -> None:
    attempt = SearchAttempt(
        provider_used=SearchProvider.YOU,
        query="academic profile",
        attempt_number=1,
        result_count=10,
        plausible_supervisor_count=4,
        rejection_counts=SearchResultRejectionCounts(
            person_not_established=2,
            academic_context_not_established=1,
            identity_conflict=1,
            institution_not_established=1,
            incomplete_institution=1,
        ),
        discovery_round=1,
    )

    assert attempt.rejection_counts is not None
    assert attempt.rejection_counts.total == 6


def test_legacy_search_attempt_without_rejection_taxonomy_still_deserializes() -> None:
    attempt = SearchAttempt.model_validate(
        {
            "provider_used": "you.com",
            "query": "academic profile",
            "attempt_number": 1,
            "result_count": 10,
            "plausible_supervisor_count": 4,
            "error_category": None,
            "retryable": False,
            "discovery_round": 1,
        }
    )

    assert attempt.rejection_counts is None


def test_successful_search_attempt_rejects_unaccounted_taxonomy() -> None:
    with pytest.raises(ValidationError, match="account for every result"):
        SearchAttempt(
            provider_used=SearchProvider.YOU,
            query="academic profile",
            attempt_number=1,
            result_count=10,
            plausible_supervisor_count=4,
            rejection_counts=SearchResultRejectionCounts(person_not_established=5),
            discovery_round=1,
        )


def test_tavily_queries_prioritize_latest_current_round_you_yield_stably() -> None:
    base_queries = make_search_plan().search_queries
    planned_queries = tuple(
        base_queries[index % len(base_queries)].model_copy(update={"query": f"query {index + 1}"})
        for index in range(6)
    )
    attempts = (
        _attempt(query="query 1", plausible_count=8, discovery_round=1),
        _attempt(query="query 2", plausible_count=1, discovery_round=2),
        _attempt(query="query 4", plausible_count=2, discovery_round=2),
        _attempt(query="query 5", plausible_count=2, discovery_round=2),
        _attempt(query="query 6", plausible_count=4, discovery_round=2),
        _attempt(
            query="query 6",
            attempt_number=2,
            result_count=8,
            plausible_count=0,
            discovery_round=2,
        ),
        _attempt(
            provider=SearchProvider.TAVILY,
            query="query 3",
            plausible_count=7,
            discovery_round=2,
        ),
    )

    prioritized = prioritize_tavily_fallback_queries(
        planned_queries,
        attempts,
        discovery_round=2,
    )

    assert tuple(item.query for item in prioritized) == (
        "query 4",
        "query 5",
        "query 2",
        "query 1",
        "query 3",
        "query 6",
    )


def test_resumed_tavily_selection_uses_ranked_untried_queries_before_repeats() -> None:
    base_queries = make_search_plan().search_queries
    planned_queries = tuple(
        base_queries[index % len(base_queries)].model_copy(update={"query": f"query {index + 1}"})
        for index in range(6)
    )
    attempts = (
        _attempt(query="query 4", plausible_count=3, discovery_round=2),
        _attempt(query="query 5", plausible_count=2, discovery_round=2),
        _attempt(
            provider=SearchProvider.TAVILY,
            query="query 5",
            plausible_count=0,
            discovery_round=1,
        ),
        _attempt(
            provider=SearchProvider.TAVILY,
            query="query 4",
            plausible_count=0,
            discovery_round=2,
        ),
    )

    selected = select_tavily_fallback_queries(
        planned_queries,
        attempts,
        discovery_round=2,
        maximum_fallback_count=4,
    )

    assert tuple(item.query for item in selected) == ("query 5", "query 1", "query 2")


def test_tavily_selection_rejects_a_negative_fallback_limit() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        select_tavily_fallback_queries(
            make_search_plan().search_queries,
            (),
            discovery_round=1,
            maximum_fallback_count=-1,
        )


def test_response_contract_error_can_preserve_returned_result_count() -> None:
    attempt = SearchAttempt(
        provider_used=SearchProvider.TAVILY,
        query="fallback query",
        attempt_number=1,
        result_count=3,
        plausible_supervisor_count=0,
        error_category=SearchErrorCategory.RESPONSE_CONTRACT,
        retryable=False,
        discovery_round=1,
    )

    assert attempt.result_count == 3
    assert attempt.error_category is SearchErrorCategory.RESPONSE_CONTRACT


@pytest.mark.parametrize(
    "payload",
    [
        {"attempt_number": 0},
        {"result_count": -1},
        {"plausible_supervisor_count": -1},
        {"discovery_round": 0},
        {"result_count": 1, "plausible_supervisor_count": 2},
        {"error_category": None, "retryable": True},
        {
            "error_category": SearchErrorCategory.TIMEOUT,
            "retryable": True,
            "result_count": 1,
            "plausible_supervisor_count": 1,
        },
    ],
)
def test_search_attempt_rejects_invalid_audit_records(payload: dict[str, object]) -> None:
    values: dict[str, object] = {
        "provider_used": SearchProvider.YOU,
        "query": "academic profile",
        "attempt_number": 1,
        "result_count": 0,
        "plausible_supervisor_count": 0,
        "error_category": SearchErrorCategory.TIMEOUT,
        "retryable": True,
        "discovery_round": 1,
    }
    values.update(payload)

    with pytest.raises(ValidationError):
        SearchAttempt.model_validate(values)


@pytest.mark.parametrize(
    "payload",
    [
        {"minimum_unique_supervisors": 0},
        {"maximum_you_retry_count": -1},
        {"maximum_tavily_fallback_count": -1},
        {"duplicate_result_threshold": -0.01},
        {"duplicate_result_threshold": 1.01},
        {"minimum_plausible_profile_ratio": -0.01},
        {"minimum_plausible_profile_ratio": 1.01},
    ],
)
def test_discovery_policy_rejects_unbounded_or_invalid_values(
    payload: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        DiscoveryPolicy.model_validate(payload)


@pytest.mark.parametrize("provider", [SearchProvider.YOU, SearchProvider.TAVILY])
def test_nonretryable_authentication_error_stops_immediately(
    provider: SearchProvider,
) -> None:
    attempt = _attempt(
        provider=provider,
        error_category=SearchErrorCategory.AUTHENTICATION,
    )

    assert _route((attempt,), unique_count=8) is SupervisorDiscoveryRoute.STOP


def test_other_nonretryable_provider_error_stops_without_tavily() -> None:
    attempt = _attempt(error_category=SearchErrorCategory.INVALID_REQUEST)

    assert _route((attempt,), unique_count=0) is SupervisorDiscoveryRoute.STOP


def test_first_you_timeout_routes_to_one_bounded_retry() -> None:
    timeout = _attempt(error_category=SearchErrorCategory.TIMEOUT, retryable=True)

    assert _route((timeout,), unique_count=0) is SupervisorDiscoveryRoute.RETRY_YOU


def test_you_timeout_after_retry_routes_to_tavily() -> None:
    first = _attempt(error_category=SearchErrorCategory.TIMEOUT, retryable=True)
    second = _attempt(
        attempt_number=2,
        error_category=SearchErrorCategory.TIMEOUT,
        retryable=True,
    )

    assert _route((first, second), unique_count=0) is SupervisorDiscoveryRoute.USE_TAVILY


def test_zero_you_retry_budget_routes_first_timeout_to_tavily() -> None:
    policy = DiscoveryPolicy(maximum_you_retry_count=0)
    timeout = _attempt(error_category=SearchErrorCategory.TIMEOUT, retryable=True)

    assert _route((timeout,), policy=policy, unique_count=0) is SupervisorDiscoveryRoute.USE_TAVILY


def test_timeout_policy_can_route_directly_to_tavily() -> None:
    policy = DiscoveryPolicy(
        timeout_behavior=DiscoveryTimeoutBehavior.TAVILY_IMMEDIATELY,
    )
    timeout = _attempt(error_category=SearchErrorCategory.TIMEOUT, retryable=True)

    assert _route((timeout,), policy=policy, unique_count=0) is SupervisorDiscoveryRoute.USE_TAVILY


def test_timeout_policy_can_stop_with_a_recoverable_status() -> None:
    policy = DiscoveryPolicy(
        timeout_behavior=DiscoveryTimeoutBehavior.STOP_RECOVERABLY,
    )
    timeout = _attempt(error_category=SearchErrorCategory.TIMEOUT, retryable=True)

    assert _route((timeout,), policy=policy, unique_count=0) is (
        SupervisorDiscoveryRoute.STOP_RECOVERABLY
    )


@pytest.mark.parametrize(
    "category",
    [
        SearchErrorCategory.TRANSPORT,
        SearchErrorCategory.RATE_LIMIT,
        SearchErrorCategory.PROVIDER,
    ],
)
def test_retryable_you_provider_error_routes_to_tavily(
    category: SearchErrorCategory,
) -> None:
    failure = _attempt(error_category=category, retryable=True)

    assert _route((failure,), unique_count=0) is SupervisorDiscoveryRoute.USE_TAVILY


def test_resolved_timeout_does_not_override_the_latest_success() -> None:
    first = _attempt(error_category=SearchErrorCategory.TIMEOUT, retryable=True)
    success = _attempt(attempt_number=2)

    assert _route((first, success)) is SupervisorDiscoveryRoute.CONTINUE


@pytest.mark.parametrize(
    "tavily_error",
    [None, SearchErrorCategory.TRANSPORT],
)
def test_retained_minimum_can_continue_after_fallback_attempt(
    tavily_error: SearchErrorCategory | None,
) -> None:
    retained_you_success = _attempt(
        query="successful primary query",
        result_count=6,
        plausible_count=6,
    )
    you_failure = _attempt(
        query="later failing primary query",
        error_category=SearchErrorCategory.PROVIDER,
        retryable=True,
    )
    tavily_attempt = _attempt(
        provider=SearchProvider.TAVILY,
        query="fallback query",
        result_count=6,
        plausible_count=6,
        error_category=tavily_error,
        retryable=tavily_error is not None,
    )

    assert (
        _route(
            (retained_you_success, you_failure, tavily_attempt),
            unique_count=6,
            fallback_used=True,
        )
        is SupervisorDiscoveryRoute.CONTINUE
    )


def test_healthy_unique_results_continue_without_tavily() -> None:
    assert _route((_attempt(),)) is SupervisorDiscoveryRoute.CONTINUE


def test_too_few_unique_supervisors_route_to_tavily() -> None:
    assert _route((_attempt(),), unique_count=4) is SupervisorDiscoveryRoute.USE_TAVILY


def test_duplicate_heavy_results_route_to_tavily() -> None:
    policy = DiscoveryPolicy(
        minimum_unique_supervisors=3,
        duplicate_result_threshold=0.6,
    )
    duplicate_heavy = _attempt(result_count=10, plausible_count=10)

    assert _route((duplicate_heavy,), policy=policy, unique_count=3) is (
        SupervisorDiscoveryRoute.USE_TAVILY
    )


def test_duplicate_ratio_at_the_allowed_threshold_can_continue() -> None:
    policy = DiscoveryPolicy(
        minimum_unique_supervisors=4,
        duplicate_result_threshold=0.5,
    )
    exactly_half_duplicates = _attempt(result_count=8, plausible_count=8)

    assert _route((exactly_half_duplicates,), policy=policy, unique_count=4) is (
        SupervisorDiscoveryRoute.CONTINUE
    )


def test_too_few_plausible_profiles_route_to_tavily() -> None:
    policy = DiscoveryPolicy(
        minimum_unique_supervisors=2,
        minimum_plausible_profile_ratio=0.25,
    )
    low_plausibility = _attempt(result_count=10, plausible_count=2)

    assert _route((low_plausibility,), policy=policy, unique_count=2) is (
        SupervisorDiscoveryRoute.USE_TAVILY
    )


def test_minimum_unique_stopping_condition_can_ignore_quality_metrics() -> None:
    policy = DiscoveryPolicy(
        minimum_unique_supervisors=2,
        stopping_condition=DiscoveryStoppingCondition.MINIMUM_UNIQUE,
    )
    low_plausibility = _attempt(result_count=10, plausible_count=2)

    assert _route((low_plausibility,), policy=policy, unique_count=2) is (
        SupervisorDiscoveryRoute.CONTINUE
    )


def test_tavily_budget_allows_another_fallback_call() -> None:
    policy = DiscoveryPolicy(
        minimum_unique_supervisors=5,
        maximum_tavily_fallback_count=2,
    )
    you = _attempt(result_count=4, plausible_count=2)
    tavily = _attempt(
        provider=SearchProvider.TAVILY,
        query="fallback query one",
        result_count=2,
        plausible_count=1,
    )

    assert _route((you, tavily), policy=policy, unique_count=3, fallback_used=True) is (
        SupervisorDiscoveryRoute.USE_TAVILY
    )


def test_exhausted_tavily_budget_continues_with_retained_minimum() -> None:
    policy = DiscoveryPolicy(
        minimum_unique_supervisors=5,
        maximum_tavily_fallback_count=1,
        duplicate_result_threshold=0.2,
    )
    you = _attempt(result_count=10, plausible_count=8)
    tavily = _attempt(
        provider=SearchProvider.TAVILY,
        query="fallback query one",
        result_count=6,
        plausible_count=4,
    )

    assert _route((you, tavily), policy=policy, unique_count=5, fallback_used=True) is (
        SupervisorDiscoveryRoute.CONTINUE
    )


def test_exhausted_tavily_budget_stops_recoverably_below_minimum() -> None:
    policy = DiscoveryPolicy(
        minimum_unique_supervisors=5,
        maximum_tavily_fallback_count=1,
    )
    tavily_failure = _attempt(
        provider=SearchProvider.TAVILY,
        query="fallback query one",
        error_category=SearchErrorCategory.TRANSPORT,
        retryable=True,
    )

    assert (
        _route(
            (tavily_failure,),
            policy=policy,
            unique_count=2,
            fallback_used=True,
        )
        is SupervisorDiscoveryRoute.STOP_RECOVERABLY
    )


def test_fallback_activation_without_an_attempt_cannot_loop_forever() -> None:
    assert _route((), unique_count=0, fallback_used=True) is (
        SupervisorDiscoveryRoute.STOP_RECOVERABLY
    )


def test_fallback_activation_without_tavily_attempt_stops_after_you_attempts() -> None:
    you_success = _attempt(result_count=2, plausible_count=2)

    assert _route((you_success,), unique_count=2, fallback_used=True) is (
        SupervisorDiscoveryRoute.STOP_RECOVERABLY
    )


def test_routing_considers_only_the_requested_discovery_round() -> None:
    old_authentication_failure = _attempt(
        error_category=SearchErrorCategory.AUTHENTICATION,
        discovery_round=1,
    )
    current_success = _attempt(discovery_round=2)

    assert (
        _route(
            (old_authentication_failure, current_success),
            discovery_round=2,
        )
        is SupervisorDiscoveryRoute.CONTINUE
    )


def test_latest_discovery_round_is_inferred_when_not_supplied() -> None:
    old_timeout = _attempt(
        error_category=SearchErrorCategory.TIMEOUT,
        retryable=True,
        discovery_round=1,
    )
    current_success = _attempt(discovery_round=2)

    assert (
        _route(
            (old_timeout, current_success),
            discovery_round=None,
        )
        is SupervisorDiscoveryRoute.CONTINUE
    )


def test_negative_unique_supervisor_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        _route((_attempt(),), unique_count=-1)
