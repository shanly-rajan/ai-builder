"""Pure policy contracts and routing for resilient Supervisor discovery."""

from collections.abc import Sequence
from enum import StrEnum
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, StrictBool, model_validator

from ..domain import PlannedSearchQuery, SearchResultRejectionCounts
from ..tools import SearchErrorCategory, SearchProvider


class DiscoveryTimeoutBehavior(StrEnum):
    """Deterministic action taken when You.com does not answer in time."""

    RETRY_THEN_TAVILY = "retry_then_tavily"
    TAVILY_IMMEDIATELY = "tavily_immediately"
    STOP_RECOVERABLY = "stop_recoverably"


class DiscoveryStoppingCondition(StrEnum):
    """Quality gate that allows discovery to continue downstream."""

    MINIMUM_UNIQUE = "minimum_unique"
    MINIMUM_UNIQUE_AND_QUALITY = "minimum_unique_and_quality"


class SupervisorDiscoveryRoute(StrEnum):
    """Provider-neutral decisions returned by the pure discovery router."""

    RETRY_YOU = "retry_you"
    USE_TAVILY = "use_tavily"
    CONTINUE = "continue"
    STOP = "stop"
    STOP_RECOVERABLY = "stop_recoverably"


class SearchAttempt(BaseModel):
    """Sanitized record of one provider call in a discovery round."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    provider_used: SearchProvider
    query: str = Field(min_length=1)
    attempt_number: int = Field(ge=1)
    result_count: int = Field(ge=0)
    plausible_supervisor_count: int = Field(ge=0)
    rejection_counts: SearchResultRejectionCounts | None = None
    error_category: SearchErrorCategory | None = None
    retryable: StrictBool = False
    discovery_round: int = Field(ge=1)

    @model_validator(mode="after")
    def attempt_counts_and_error_are_consistent(self) -> "SearchAttempt":
        """Reject impossible combinations before they enter graph history."""
        if self.plausible_supervisor_count > self.result_count:
            raise ValueError("plausible_supervisor_count must not exceed result_count")
        if self.error_category is None and self.retryable:
            raise ValueError("a successful SearchAttempt cannot be retryable")
        if self.error_category is not None and self.plausible_supervisor_count != 0:
            raise ValueError("a failed SearchAttempt cannot contain plausible profiles")
        if self.error_category is not None and self.rejection_counts is not None:
            raise ValueError("a failed SearchAttempt cannot contain rejection counts")
        if (
            self.error_category is None
            and self.rejection_counts is not None
            and self.rejection_counts.total + self.plausible_supervisor_count != self.result_count
        ):
            raise ValueError("successful SearchAttempt counts must account for every result")
        if (
            self.error_category is not None
            and self.error_category is not SearchErrorCategory.RESPONSE_CONTRACT
            and self.result_count != 0
        ):
            raise ValueError("a provider failure cannot contain returned results")
        return self


class DiscoveryPolicy(BaseModel):
    """Finite, deterministic resilience and quality controls for discovery."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    minimum_unique_supervisors: int = Field(default=5, ge=1)
    maximum_prospective_supervisors: int = Field(default=20, ge=1, le=100)
    maximum_you_retry_count: int = Field(default=1, ge=0, le=10)
    maximum_tavily_fallback_count: int = Field(default=4, ge=0, le=100)
    timeout_behavior: DiscoveryTimeoutBehavior = DiscoveryTimeoutBehavior.RETRY_THEN_TAVILY
    duplicate_result_threshold: float = Field(default=0.6, ge=0.0, le=1.0)
    minimum_plausible_profile_ratio: float = Field(default=0.25, ge=0.0, le=1.0)
    stopping_condition: DiscoveryStoppingCondition = (
        DiscoveryStoppingCondition.MINIMUM_UNIQUE_AND_QUALITY
    )

    @model_validator(mode="after")
    def maximum_must_cover_minimum(self) -> Self:
        """Ensure the downstream cohort cap cannot invalidate the discovery minimum."""
        if self.maximum_prospective_supervisors < self.minimum_unique_supervisors:
            raise ValueError(
                "maximum_prospective_supervisors must not be less than minimum_unique_supervisors"
            )
        return self


def _current_round_attempts(
    attempts: Sequence[SearchAttempt], discovery_round: int | None
) -> tuple[SearchAttempt, ...]:
    if discovery_round is None:
        if not attempts:
            return ()
        discovery_round = max(attempt.discovery_round for attempt in attempts)
    return tuple(attempt for attempt in attempts if attempt.discovery_round == discovery_round)


def _latest_attempts_by_query(
    attempts: Sequence[SearchAttempt], provider: SearchProvider
) -> tuple[SearchAttempt, ...]:
    latest: dict[str, SearchAttempt] = {}
    for attempt in attempts:
        if attempt.provider_used is not provider:
            continue
        previous = latest.get(attempt.query)
        if previous is None or attempt.attempt_number >= previous.attempt_number:
            latest[attempt.query] = attempt
    return tuple(latest.values())


def prioritize_tavily_fallback_queries(
    planned_queries: Sequence[PlannedSearchQuery],
    attempts: Sequence[SearchAttempt],
    *,
    discovery_round: int,
) -> tuple[PlannedSearchQuery, ...]:
    """Prioritize primary-provider signals without changing the fallback budget.

    Only the latest You.com attempt for each query in the current discovery round
    contributes a yield. Queries with equal yields retain their original SearchPlan
    order, including queries with no plausible profiles or no primary attempt.
    """
    current_attempts = _current_round_attempts(attempts, discovery_round)
    latest_you_attempts = _latest_attempts_by_query(current_attempts, SearchProvider.YOU)
    plausible_counts = {
        attempt.query: attempt.plausible_supervisor_count for attempt in latest_you_attempts
    }
    indexed_queries = tuple(enumerate(planned_queries))
    return tuple(
        planned_query
        for _, planned_query in sorted(
            indexed_queries,
            key=lambda item: (-plausible_counts.get(item[1].query, 0), item[0]),
        )
    )


def select_tavily_fallback_queries(
    planned_queries: Sequence[PlannedSearchQuery],
    attempts: Sequence[SearchAttempt],
    *,
    discovery_round: int,
    maximum_fallback_count: int,
) -> tuple[PlannedSearchQuery, ...]:
    """Select the remaining bounded calls, exhausting ranked untried queries first."""
    if maximum_fallback_count < 0:
        raise ValueError("maximum_fallback_count must not be negative")
    current_attempts = _current_round_attempts(attempts, discovery_round)
    tavily_attempts = tuple(
        attempt for attempt in current_attempts if attempt.provider_used is SearchProvider.TAVILY
    )
    remaining_budget = max(0, maximum_fallback_count - len(tavily_attempts))
    if remaining_budget == 0 or not planned_queries:
        return ()

    prioritized = prioritize_tavily_fallback_queries(
        planned_queries,
        current_attempts,
        discovery_round=discovery_round,
    )
    attempted_queries = {attempt.query for attempt in tavily_attempts}
    untried = tuple(item for item in prioritized if item.query not in attempted_queries)
    already_tried = tuple(item for item in prioritized if item.query in attempted_queries)
    ordered = (*untried, *already_tried)
    return tuple(ordered[index % len(ordered)] for index in range(remaining_budget))


def _has_unresolved_nonretryable_error(attempts: Sequence[SearchAttempt]) -> bool:
    return any(attempt.error_category is not None and not attempt.retryable for attempt in attempts)


def _quality_metrics(
    attempts: Sequence[SearchAttempt], unique_supervisor_count: int
) -> tuple[float, float]:
    result_count = sum(attempt.result_count for attempt in attempts)
    plausible_count = sum(attempt.plausible_supervisor_count for attempt in attempts)
    plausible_ratio = plausible_count / result_count if result_count else 0.0
    duplicate_count = max(0, plausible_count - unique_supervisor_count)
    duplicate_ratio = duplicate_count / plausible_count if plausible_count else 0.0
    return plausible_ratio, duplicate_ratio


def _stopping_condition_met(
    policy: DiscoveryPolicy,
    attempts: Sequence[SearchAttempt],
    unique_supervisor_count: int,
) -> bool:
    if unique_supervisor_count < policy.minimum_unique_supervisors:
        return False
    if policy.stopping_condition is DiscoveryStoppingCondition.MINIMUM_UNIQUE:
        return True
    plausible_ratio, duplicate_ratio = _quality_metrics(attempts, unique_supervisor_count)
    return (
        plausible_ratio >= policy.minimum_plausible_profile_ratio
        and duplicate_ratio <= policy.duplicate_result_threshold
    )


def _fallback_or_finish(
    policy: DiscoveryPolicy,
    attempts: Sequence[SearchAttempt],
    unique_supervisor_count: int,
) -> SupervisorDiscoveryRoute:
    tavily_attempt_count = sum(
        attempt.provider_used is SearchProvider.TAVILY for attempt in attempts
    )
    if tavily_attempt_count < policy.maximum_tavily_fallback_count:
        return SupervisorDiscoveryRoute.USE_TAVILY
    if unique_supervisor_count >= policy.minimum_unique_supervisors:
        return SupervisorDiscoveryRoute.CONTINUE
    return SupervisorDiscoveryRoute.STOP_RECOVERABLY


def route_after_supervisor_discovery(
    policy: DiscoveryPolicy,
    attempts: Sequence[SearchAttempt],
    *,
    unique_supervisor_count: int,
    fallback_search_used: bool,
    discovery_round: int | None = None,
) -> SupervisorDiscoveryRoute:
    """Choose the next bounded discovery action without performing provider calls."""
    if unique_supervisor_count < 0:
        raise ValueError("unique_supervisor_count must not be negative")

    current_attempts = _current_round_attempts(attempts, discovery_round)
    latest_you = _latest_attempts_by_query(current_attempts, SearchProvider.YOU)
    latest_tavily = _latest_attempts_by_query(current_attempts, SearchProvider.TAVILY)
    unresolved_attempts = (*latest_you, *latest_tavily)

    if any(
        attempt.error_category is SearchErrorCategory.AUTHENTICATION and not attempt.retryable
        for attempt in unresolved_attempts
    ):
        return SupervisorDiscoveryRoute.STOP

    if _has_unresolved_nonretryable_error(unresolved_attempts):
        return SupervisorDiscoveryRoute.STOP

    # Once fallback has actually been attempted, a sufficient retained cohort can
    # continue even though the primary provider's latest attempt remains retryable.
    # This is what turns multi-query discovery into partial success instead of forcing
    # the complete fallback budget to be spent after any primary-provider outage.
    if (
        fallback_search_used
        and latest_tavily
        and _stopping_condition_met(policy, current_attempts, unique_supervisor_count)
    ):
        return SupervisorDiscoveryRoute.CONTINUE

    timed_out_you = tuple(
        attempt for attempt in latest_you if attempt.error_category is SearchErrorCategory.TIMEOUT
    )
    if timed_out_you:
        if policy.timeout_behavior is DiscoveryTimeoutBehavior.STOP_RECOVERABLY:
            return SupervisorDiscoveryRoute.STOP_RECOVERABLY
        if policy.timeout_behavior is DiscoveryTimeoutBehavior.RETRY_THEN_TAVILY and any(
            attempt.attempt_number <= policy.maximum_you_retry_count for attempt in timed_out_you
        ):
            return SupervisorDiscoveryRoute.RETRY_YOU
        return _fallback_or_finish(policy, current_attempts, unique_supervisor_count)

    if any(attempt.error_category is not None and attempt.retryable for attempt in latest_you):
        return _fallback_or_finish(policy, current_attempts, unique_supervisor_count)

    if _stopping_condition_met(policy, current_attempts, unique_supervisor_count):
        return SupervisorDiscoveryRoute.CONTINUE

    # A fallback activation that could not produce an attempt (for example, missing
    # configuration) must not route back to the same activation indefinitely.
    if fallback_search_used and not latest_tavily:
        if unique_supervisor_count >= policy.minimum_unique_supervisors:
            return SupervisorDiscoveryRoute.CONTINUE
        return SupervisorDiscoveryRoute.STOP_RECOVERABLY
    return _fallback_or_finish(policy, current_attempts, unique_supervisor_count)
