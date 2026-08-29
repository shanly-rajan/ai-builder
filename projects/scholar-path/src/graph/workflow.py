"""ScholarPath graph with resilient, policy-routed Supervisor discovery."""

from dataclasses import dataclass, field
from typing import Final, Literal, cast

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from ..agents import (
    RESEARCH_PLANNING_PROMPT_VERSION,
    OpenAIPlanningModelAdapter,
    PlanningFailureKind,
    PlanningInput,
    PlanningModelInvocationError,
    PlanningModelPort,
    ResearchPlanningAgent,
    ResearchPlanningError,
    StructuredSearchPlanResponse,
    SupervisorDiscoveryAgent,
    deduplicate_prospective_supervisors,
)
from ..config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    LangSmithSettings,
    OpenAIPlanningSettings,
    ProviderConfigurationError,
    TavilySearchSettings,
    YouSearchSettings,
    load_langsmith_settings,
    load_openai_planning_settings,
    load_settings,
    load_tavily_search_settings,
    load_you_search_settings,
)
from ..domain import (
    CandidatePreferenceRevision,
    CandidateReviewAction,
    CandidateReviewDecision,
    ProspectiveSupervisor,
    SearchPlan,
    SearchResult,
    apply_candidate_review,
    create_supervisor_shortlist,
    validate_research_fit_evidence,
)
from ..observability import LangSmithObservability
from ..tools import (
    FailureInjectingSupervisorSearch,
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
    SupervisorSearchError,
    SupervisorSearchPort,
    TavilySearchAdapter,
    YouSearchAdapter,
)
from .discovery import (
    DiscoveryPolicy,
    SearchAttempt,
    SupervisorDiscoveryRoute,
    route_after_supervisor_discovery,
)
from .fixtures import (
    WalkingSkeletonFixtures,
    build_walking_skeleton_fixtures,
    default_review_decision,
    preferences_from_profile,
)
from .state import (
    RawSupervisorSearchResult,
    ReviewStatus,
    ScholarPathState,
    ScholarPathStateUpdate,
    ToolErrorRecord,
    create_initial_state,
)

LOAD_CANDIDATE_PREFERENCES: Final = "load_candidate_preferences"
PLAN_SUPERVISOR_SEARCHES: Final = "plan_supervisor_searches"
DISCOVER_PROSPECTIVE_SUPERVISORS: Final = "discover_prospective_supervisors"
ENOUGH_SUPERVISORS_FOUND: Final = "enough_supervisors_found"
FALLBACK_SUPERVISOR_SEARCH: Final = "fallback_supervisor_search"
DEDUPLICATE_SUPERVISORS: Final = "deduplicate_supervisors"
EXTRACT_SUPERVISOR_EVIDENCE: Final = "extract_supervisor_evidence"
SUPERVISOR_EVIDENCE_SUFFICIENT: Final = "supervisor_evidence_sufficient"
RETRY_ALTERNATE_EVIDENCE_SOURCE: Final = "retry_alternate_evidence_source"
EVALUATE_RESEARCH_FIT: Final = "evaluate_research_fit"
REVIEW_FIT_ASSESSMENTS: Final = "review_fit_assessments"
SYNTHESIZE_SUPERVISOR_SHORTLIST: Final = "synthesize_supervisor_shortlist"
CANDIDATE_REVIEW_GATE_STUB: Final = "candidate_review_gate_stub"
SAVE_SHORTLISTED_SUPERVISORS: Final = "save_shortlisted_supervisors"
GENERATE_SHORTLIST_BRIEFING: Final = "generate_shortlist_briefing"

CANONICAL_NODE_NAMES = (
    LOAD_CANDIDATE_PREFERENCES,
    PLAN_SUPERVISOR_SEARCHES,
    DISCOVER_PROSPECTIVE_SUPERVISORS,
    ENOUGH_SUPERVISORS_FOUND,
    FALLBACK_SUPERVISOR_SEARCH,
    DEDUPLICATE_SUPERVISORS,
    EXTRACT_SUPERVISOR_EVIDENCE,
    SUPERVISOR_EVIDENCE_SUFFICIENT,
    RETRY_ALTERNATE_EVIDENCE_SOURCE,
    EVALUATE_RESEARCH_FIT,
    REVIEW_FIT_ASSESSMENTS,
    SYNTHESIZE_SUPERVISOR_SHORTLIST,
    CANDIDATE_REVIEW_GATE_STUB,
    SAVE_SHORTLISTED_SUPERVISORS,
    GENERATE_SHORTLIST_BRIEFING,
)
REQUIRED_SHORTLIST_SIZE: Final = 5
MAX_CONFIGURED_RETRIES: Final = 5

type DiscoveryRoute = Literal[
    "discover_prospective_supervisors",
    "fallback_supervisor_search",
    "deduplicate_supervisors",
    "__end__",
]
type EvidenceRoute = Literal["retry_alternate_evidence_source", "evaluate_research_fit", "__end__"]
type ReviewRoute = Literal["save_shortlisted_supervisors", "plan_supervisor_searches", "__end__"]
type PlanningRoute = Literal["discover_prospective_supervisors", "__end__"]
type ScholarPathGraph = CompiledStateGraph[
    ScholarPathState, None, ScholarPathState, ScholarPathState
]


@dataclass(frozen=True, slots=True)
class GraphFixtureConfig:
    """Immutable controls for deterministic walking-skeleton route scenarios."""

    fixtures: WalkingSkeletonFixtures = field(default_factory=build_walking_skeleton_fixtures)
    discovery_policy: DiscoveryPolicy = field(default_factory=DiscoveryPolicy)
    review_decisions: tuple[CandidateReviewDecision, ...] = field(
        default_factory=lambda: (default_review_decision(),)
    )
    initial_evidence_count: int = 6
    alternate_evidence_count: int = 6
    minimum_verified_supervisors: int = 5
    shortlist_size: int = REQUIRED_SHORTLIST_SIZE
    max_evidence_retries: int = 1
    max_review_retries: int = 1

    def __post_init__(self) -> None:
        """Reject invalid fixture controls before graph construction."""
        fixture_limits = {
            "initial_evidence_count": (
                self.initial_evidence_count,
                len(self.fixtures.verified_supervisors),
            ),
            "alternate_evidence_count": (
                self.alternate_evidence_count,
                len(self.fixtures.verified_supervisors),
            ),
        }
        for field_name, (value, maximum) in fixture_limits.items():
            if not 0 <= value <= maximum:
                raise ValueError(f"{field_name} must be between 0 and {maximum}")

        positive_values = {
            "minimum_verified_supervisors": self.minimum_verified_supervisors,
            "shortlist_size": self.shortlist_size,
        }
        for field_name, value in positive_values.items():
            if value < 1:
                raise ValueError(f"{field_name} must be at least 1")

        if self.shortlist_size != REQUIRED_SHORTLIST_SIZE:
            raise ValueError(
                f"shortlist_size must be {REQUIRED_SHORTLIST_SIZE} for the M2 walking skeleton"
            )
        for field_name, value in (
            ("minimum_verified_supervisors", self.minimum_verified_supervisors),
        ):
            if value < self.shortlist_size:
                raise ValueError(f"{field_name} must not be less than shortlist_size")
        if len(self.fixtures.research_fit_assessments) < self.shortlist_size:
            raise ValueError("fixtures must contain enough Research Fit assessments")

        retry_limits = {
            "max_evidence_retries": self.max_evidence_retries,
            "max_review_retries": self.max_review_retries,
        }
        for field_name, value in retry_limits.items():
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")
            if value > MAX_CONFIGURED_RETRIES:
                raise ValueError(f"{field_name} must not exceed {MAX_CONFIGURED_RETRIES}")


class DeterministicScholarPathNodes:
    """Walking-skeleton nodes with injected planning and resilient search boundaries."""

    def __init__(
        self,
        config: GraphFixtureConfig,
        planning_agent: ResearchPlanningAgent,
        supervisor_search: SupervisorSearchPort | None = None,
        tavily_search: SupervisorSearchPort | None = None,
    ) -> None:
        self.config = config
        self.planning_agent = planning_agent
        self.supervisor_search = supervisor_search
        self.tavily_search = tavily_search
        self.discovery_agent = SupervisorDiscoveryAgent()

    @staticmethod
    def _error(
        node: str,
        code: str,
        message: str,
        *,
        recoverable: bool = False,
    ) -> ToolErrorRecord:
        return ToolErrorRecord(
            node=node,
            code=code,
            message=message,
            recoverable=recoverable,
        )

    @staticmethod
    def _retry_counts(state: ScholarPathState, key: str, value: int) -> dict[str, int]:
        return {**state["retry_counts"], key: value}

    @staticmethod
    def _latest_regions(
        preferences: list[CandidatePreferenceRevision], fallback: tuple[str, ...]
    ) -> tuple[str, ...]:
        for revision in reversed(preferences):
            if revision.preferred_regions is not None:
                return revision.preferred_regions
        return fallback

    @staticmethod
    def _latest_exclusions(
        preferences: list[CandidatePreferenceRevision], fallback: tuple[str, ...]
    ) -> tuple[str, ...]:
        for revision in reversed(preferences):
            if revision.exclusions is not None:
                return revision.exclusions
        return fallback

    def load_candidate_preferences(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Load a typed preference snapshot from the fixture Candidate profile."""
        return {
            "candidate_preferences": [preferences_from_profile(state["candidate_profile"])],
            "execution_log": [LOAD_CANDIDATE_PREFERENCES],
        }

    def plan_supervisor_searches(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Delegate search planning through the typed model port and sanitize failures."""
        profile = state["candidate_profile"]
        regions = self._latest_regions(state["candidate_preferences"], profile.preferred_regions)
        exclusions = self._latest_exclusions(state["candidate_preferences"], profile.exclusions)
        try:
            plan = self.planning_agent.plan(
                profile,
                tuple(state["candidate_preferences"]),
                target_regions=regions,
                exclusions=exclusions,
            )
        except ResearchPlanningError as error:
            error_code = (
                "planning_model_failed"
                if error.kind is PlanningFailureKind.MODEL_INVOCATION
                else "planning_output_invalid"
            )
            return {
                "search_plan": None,
                "review_status": ReviewStatus.RETRY_EXHAUSTED,
                "tool_errors": [
                    self._error(
                        PLAN_SUPERVISOR_SEARCHES,
                        error_code,
                        "Research planning could not produce a valid typed SearchPlan.",
                    )
                ],
                "execution_log": [PLAN_SUPERVISOR_SEARCHES],
            }
        return {
            "search_plan": plan,
            "discovery_round": state["discovery_round"] + 1,
            "execution_log": [PLAN_SUPERVISOR_SEARCHES],
        }

    @staticmethod
    def route_after_planning(state: ScholarPathState) -> PlanningRoute:
        """Continue only when planning produced a validated SearchPlan."""
        if state["search_plan"] is not None:
            return DISCOVER_PROSPECTIVE_SUPERVISORS
        return "__end__"

    @staticmethod
    def _attempt_number(
        attempts: list[SearchAttempt],
        provider: SearchProvider,
        query: str,
        discovery_round: int,
    ) -> int:
        return (
            sum(
                attempt.provider_used is provider
                and attempt.query == query
                and attempt.discovery_round == discovery_round
                for attempt in attempts
            )
            + 1
        )

    @staticmethod
    def _normalize_search_error(
        error: Exception,
        provider: SearchProvider,
    ) -> SearchProviderError:
        if isinstance(error, SearchProviderError):
            return error
        if isinstance(error, SupervisorSearchError):
            return SearchProviderError(
                "Supervisor search failed before returning normalized results.",
                provider=provider,
                category=SearchErrorCategory.UNKNOWN,
                retryable=False,
            )
        return SearchProviderError(
            "Supervisor search failed unexpectedly.",
            provider=provider,
            category=SearchErrorCategory.UNKNOWN,
            retryable=False,
        )

    def _search_error_record(
        self,
        node: str,
        provider: SearchProvider,
        error: SearchProviderError,
    ) -> ToolErrorRecord:
        provider_code = "you" if provider is SearchProvider.YOU else "tavily"
        return self._error(
            node,
            f"{provider_code}_search_{error.category.value}",
            f"{provider.value} Supervisor search failed with a sanitized provider error.",
            recoverable=error.retryable,
        )

    def _execute_search_attempt(
        self,
        *,
        node: str,
        port: SupervisorSearchPort,
        provider: SearchProvider,
        query: str,
        search_plan: SearchPlan,
        attempt_number: int,
        discovery_round: int,
    ) -> tuple[
        list[RawSupervisorSearchResult],
        SearchAttempt,
        ToolErrorRecord | None,
        SearchProviderError | None,
    ]:
        try:
            results = port.search(query)
        except Exception as caught_error:
            error = self._normalize_search_error(caught_error, provider)
            attempt = SearchAttempt(
                provider_used=provider,
                query=query,
                attempt_number=attempt_number,
                result_count=0,
                plausible_supervisor_count=0,
                error_category=error.category,
                retryable=error.retryable,
                discovery_round=discovery_round,
            )
            return [], attempt, self._search_error_record(node, provider, error), error

        try:
            discovery = self.discovery_agent.discover(search_plan, results)
        except Exception:
            error = SearchProviderError(
                "Search results could not satisfy the Supervisor discovery contract.",
                provider=provider,
                category=SearchErrorCategory.RESPONSE_CONTRACT,
                retryable=False,
            )
            attempt = SearchAttempt(
                provider_used=provider,
                query=query,
                attempt_number=attempt_number,
                result_count=len(results),
                plausible_supervisor_count=0,
                error_category=error.category,
                retryable=False,
                discovery_round=discovery_round,
            )
            return [], attempt, self._search_error_record(node, provider, error), error

        attempt = SearchAttempt(
            provider_used=provider,
            query=query,
            attempt_number=attempt_number,
            result_count=len(results),
            plausible_supervisor_count=discovery.plausible_supervisor_count,
            discovery_round=discovery_round,
        )
        raw_results = [
            RawSupervisorSearchResult.from_prospective_supervisor(
                supervisor,
                discovery_round=discovery_round,
            )
            for supervisor in discovery.prospective_supervisors
        ]
        return raw_results, attempt, None, None

    def _available_prospective_supervisors(
        self,
        state: ScholarPathState,
        additional_results: list[RawSupervisorSearchResult] | None = None,
        *,
        discovery_round: int | None = None,
    ) -> tuple[ProspectiveSupervisor, ...]:
        rejected_ids = {supervisor.supervisor_id for supervisor in state["rejected_supervisors"]}
        combined = [*state["raw_search_results"], *(additional_results or [])]
        available = (
            result.to_prospective_supervisor()
            for result in combined
            if result.supervisor_id not in rejected_ids
            and (discovery_round is None or result.discovery_round == discovery_round)
        )
        return deduplicate_prospective_supervisors(available)

    def _policy_route(
        self,
        state: ScholarPathState,
        *,
        additional_attempts: list[SearchAttempt] | None = None,
        additional_results: list[RawSupervisorSearchResult] | None = None,
        fallback_search_used: bool | None = None,
    ) -> SupervisorDiscoveryRoute:
        attempts = [*state["search_attempts"], *(additional_attempts or [])]
        unique_count = len(
            self._available_prospective_supervisors(
                state,
                additional_results,
                discovery_round=state["discovery_round"],
            )
        )
        fallback_used_current_round = (
            state["fallback_search_round"] == state["discovery_round"]
            if fallback_search_used is None
            else fallback_search_used
        )
        return route_after_supervisor_discovery(
            self.config.discovery_policy,
            attempts,
            unique_supervisor_count=unique_count,
            fallback_search_used=fallback_used_current_round,
            discovery_round=state["discovery_round"],
        )

    def discover_prospective_supervisors(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Execute You.com queries with policy-bounded timeout retries and partial success."""
        update: ScholarPathStateUpdate = {
            "raw_search_results": [],
            "search_attempts": [],
            "execution_log": [DISCOVER_PROSPECTIVE_SUPERVISORS],
        }
        search_plan = state["search_plan"]
        if search_plan is None:
            update["tool_errors"] = [
                self._error(
                    DISCOVER_PROSPECTIVE_SUPERVISORS,
                    "search_plan_missing",
                    "Supervisor discovery requires a validated SearchPlan.",
                )
            ]
            return update
        if self.supervisor_search is None:
            update["tool_errors"] = [
                self._error(
                    DISCOVER_PROSPECTIVE_SUPERVISORS,
                    "supervisor_search_not_configured",
                    "Supervisor discovery has no configured You.com search adapter.",
                )
            ]
            return update

        raw_results: list[RawSupervisorSearchResult] = []
        attempts: list[SearchAttempt] = []
        errors: list[ToolErrorRecord] = []
        prior_attempts = list(state["search_attempts"])
        halt_primary = False
        for planned_query in search_plan.search_queries:
            query = planned_query.query
            while True:
                attempt_number = self._attempt_number(
                    [*prior_attempts, *attempts],
                    SearchProvider.YOU,
                    query,
                    state["discovery_round"],
                )
                discovered, attempt, tool_error, provider_error = self._execute_search_attempt(
                    node=DISCOVER_PROSPECTIVE_SUPERVISORS,
                    port=self.supervisor_search,
                    provider=SearchProvider.YOU,
                    query=query,
                    search_plan=search_plan,
                    attempt_number=attempt_number,
                    discovery_round=state["discovery_round"],
                )
                raw_results.extend(discovered)
                attempts.append(attempt)
                if tool_error is not None:
                    errors.append(tool_error)
                if provider_error is None:
                    break

                route = self._policy_route(
                    state,
                    additional_attempts=attempts,
                    additional_results=raw_results,
                    fallback_search_used=False,
                )
                if route is SupervisorDiscoveryRoute.RETRY_YOU:
                    continue
                halt_primary = True
                break
            if halt_primary:
                break

        update["raw_search_results"] = raw_results
        update["search_attempts"] = attempts
        you_retry_count = sum(
            attempt.provider_used is SearchProvider.YOU and attempt.attempt_number > 1
            for attempt in attempts
        )
        if you_retry_count:
            update["retry_counts"] = self._retry_counts(
                state,
                "discovery",
                state["retry_counts"]["discovery"] + you_retry_count,
            )
        if errors:
            update["tool_errors"] = errors
        return update

    def enough_supervisors_found(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Materialize partial discovery and record a clear terminal policy outcome."""
        supervisors = list(self._available_prospective_supervisors(state))
        update: ScholarPathStateUpdate = {
            "prospective_supervisors": supervisors,
            "execution_log": [ENOUGH_SUPERVISORS_FOUND],
        }
        route = self._policy_route(state)
        if route is SupervisorDiscoveryRoute.STOP:
            update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
            update["tool_errors"] = [
                self._error(
                    ENOUGH_SUPERVISORS_FOUND,
                    "supervisor_discovery_stopped",
                    "Supervisor discovery stopped after a non-retryable provider error.",
                )
            ]
        elif route is SupervisorDiscoveryRoute.STOP_RECOVERABLY:
            update["review_status"] = ReviewStatus.DISCOVERY_INCOMPLETE
            update["tool_errors"] = [
                self._error(
                    ENOUGH_SUPERVISORS_FOUND,
                    "supervisor_discovery_incomplete",
                    "Supervisor discovery exhausted its bounded providers with partial results.",
                    recoverable=True,
                )
            ]
        return update

    def route_after_discovery(self, state: ScholarPathState) -> DiscoveryRoute:
        """Map the pure policy decision onto existing canonical graph nodes."""
        route = self._policy_route(state)
        if route is SupervisorDiscoveryRoute.RETRY_YOU:
            return DISCOVER_PROSPECTIVE_SUPERVISORS
        if route is SupervisorDiscoveryRoute.USE_TAVILY:
            return FALLBACK_SUPERVISOR_SEARCH
        if route is SupervisorDiscoveryRoute.CONTINUE:
            return DEDUPLICATE_SUPERVISORS
        return "__end__"

    def fallback_supervisor_search(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Execute a bounded set of Tavily queries while retaining You.com partial success."""
        update: ScholarPathStateUpdate = {
            "raw_search_results": [],
            "search_attempts": [],
            "fallback_search_used": True,
            "fallback_search_round": state["discovery_round"],
            "execution_log": [FALLBACK_SUPERVISOR_SEARCH],
        }
        search_plan = state["search_plan"]
        if search_plan is None or self.tavily_search is None:
            update["tool_errors"] = [
                self._error(
                    FALLBACK_SUPERVISOR_SEARCH,
                    "tavily_search_not_configured",
                    "Tavily fallback search is not configured.",
                )
            ]
            return update

        current_attempts = [
            attempt
            for attempt in state["search_attempts"]
            if attempt.discovery_round == state["discovery_round"]
            and attempt.provider_used is SearchProvider.TAVILY
        ]
        remaining_budget = self.config.discovery_policy.maximum_tavily_fallback_count - len(
            current_attempts
        )
        raw_results: list[RawSupervisorSearchResult] = []
        attempts: list[SearchAttempt] = []
        errors: list[ToolErrorRecord] = []
        planned_queries = search_plan.search_queries
        for fallback_index in range(remaining_budget):
            planned_query = planned_queries[
                (len(current_attempts) + fallback_index) % len(planned_queries)
            ]
            query = planned_query.query
            attempt_number = self._attempt_number(
                [*state["search_attempts"], *attempts],
                SearchProvider.TAVILY,
                query,
                state["discovery_round"],
            )
            discovered, attempt, tool_error, provider_error = self._execute_search_attempt(
                node=FALLBACK_SUPERVISOR_SEARCH,
                port=self.tavily_search,
                provider=SearchProvider.TAVILY,
                query=query,
                search_plan=search_plan,
                attempt_number=attempt_number,
                discovery_round=state["discovery_round"],
            )
            raw_results.extend(discovered)
            attempts.append(attempt)
            if tool_error is not None:
                errors.append(tool_error)
            if provider_error is not None and not provider_error.retryable:
                break

            route = self._policy_route(
                state,
                additional_attempts=attempts,
                additional_results=raw_results,
                fallback_search_used=True,
            )
            if route is not SupervisorDiscoveryRoute.USE_TAVILY:
                break

        update["raw_search_results"] = raw_results
        update["search_attempts"] = attempts
        update["retry_counts"] = self._retry_counts(
            state,
            "discovery",
            state["retry_counts"]["discovery"] + len(attempts),
        )
        if errors:
            update["tool_errors"] = errors
        return update

    def deduplicate_supervisors(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Create a stable, unique Prospective Supervisor snapshot."""
        return {
            "prospective_supervisors": list(self._available_prospective_supervisors(state)),
            "execution_log": [DEDUPLICATE_SUPERVISORS],
        }

    def extract_supervisor_evidence(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Select the configured fixture-backed Verified Supervisor evidence cohort."""
        evidence_retry = state["retry_counts"]["evidence"]
        count = (
            self.config.initial_evidence_count
            if evidence_retry == 0
            else self.config.alternate_evidence_count
        )
        prospective_ids = {
            supervisor.supervisor_id for supervisor in state["prospective_supervisors"]
        }
        rejected_ids = {supervisor.supervisor_id for supervisor in state["rejected_supervisors"]}
        eligible = [
            supervisor
            for supervisor in self.config.fixtures.verified_supervisors
            if supervisor.supervisor_id in prospective_ids
            and supervisor.supervisor_id not in rejected_ids
        ]
        return {
            "verified_supervisors": eligible[:count],
            "execution_log": [EXTRACT_SUPERVISOR_EVIDENCE],
        }

    def supervisor_evidence_sufficient(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Log cohort sufficiency and stop after the configured alternate-source limit."""
        update: ScholarPathStateUpdate = {"execution_log": [SUPERVISOR_EVIDENCE_SUFFICIENT]}
        enough = len(state["verified_supervisors"]) >= self.config.minimum_verified_supervisors
        exhausted = state["retry_counts"]["evidence"] >= self.config.max_evidence_retries
        if not enough and exhausted:
            update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
            update["tool_errors"] = [
                self._error(
                    SUPERVISOR_EVIDENCE_SUFFICIENT,
                    "evidence_retry_exhausted",
                    "Verified Supervisor evidence remained below the configured minimum.",
                )
            ]
        return update

    def route_after_evidence(self, state: ScholarPathState) -> EvidenceRoute:
        """Route deterministically after the logged evidence sufficiency check."""
        if len(state["verified_supervisors"]) >= self.config.minimum_verified_supervisors:
            return EVALUATE_RESEARCH_FIT
        if state["review_status"] is ReviewStatus.RETRY_EXHAUSTED:
            return "__end__"
        return RETRY_ALTERNATE_EVIDENCE_SOURCE

    def retry_alternate_evidence_source(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Increment the alternate-source counter before deterministic re-extraction."""
        current_retry = state["retry_counts"]["evidence"]
        return {
            "retry_counts": self._retry_counts(state, "evidence", current_retry + 1),
            "execution_log": [RETRY_ALTERNATE_EVIDENCE_SOURCE],
        }

    def evaluate_research_fit(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Select fixture assessments belonging to the current verified snapshot."""
        verified_ids = {supervisor.supervisor_id for supervisor in state["verified_supervisors"]}
        assessments = [
            assessment
            for assessment in self.config.fixtures.research_fit_assessments
            if assessment.supervisor_id in verified_ids
        ]
        return {
            "research_fit_assessments": assessments,
            "execution_log": [EVALUATE_RESEARCH_FIT],
        }

    def review_fit_assessments(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Recheck every fixture assessment against its Verified Supervisor evidence."""
        supervisors_by_id = {
            supervisor.supervisor_id: supervisor for supervisor in state["verified_supervisors"]
        }
        for assessment in state["research_fit_assessments"]:
            validate_research_fit_evidence(supervisors_by_id[assessment.supervisor_id], assessment)
        return {
            "research_fit_assessments": list(state["research_fit_assessments"]),
            "execution_log": [REVIEW_FIT_ASSESSMENTS],
        }

    def synthesize_supervisor_shortlist(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Rank Verified Supervisors by score and stable identifier tie-breaker."""
        supervisors_by_id = {
            supervisor.supervisor_id: supervisor for supervisor in state["verified_supervisors"]
        }
        ranked_assessments = sorted(
            state["research_fit_assessments"],
            key=lambda assessment: (-assessment.overall_score, assessment.supervisor_id),
        )
        proposed = [
            supervisors_by_id[assessment.supervisor_id]
            for assessment in ranked_assessments[: self.config.shortlist_size]
        ]
        return {
            "proposed_shortlist": proposed,
            "review_status": ReviewStatus.PROPOSED,
            "execution_log": [SYNTHESIZE_SUPERVISOR_SHORTLIST],
        }

    def candidate_review_gate_stub(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Apply the configured fixture decision and enforce bounded refinement."""
        attempt = state["retry_counts"]["review"]
        update: ScholarPathStateUpdate = {"execution_log": [CANDIDATE_REVIEW_GATE_STUB]}
        if attempt >= len(self.config.review_decisions):
            update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
            update["tool_errors"] = [
                self._error(
                    CANDIDATE_REVIEW_GATE_STUB,
                    "review_fixture_exhausted",
                    "No configured Candidate review decision remains for this refinement cycle.",
                )
            ]
            return update

        decision = self.config.review_decisions[attempt]
        proposed_by_id = {
            supervisor.supervisor_id: supervisor for supervisor in state["proposed_shortlist"]
        }
        unknown_ids = [
            supervisor_id
            for supervisor_id in decision.supervisor_ids
            if supervisor_id not in proposed_by_id
        ]
        if unknown_ids:
            update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
            update["tool_errors"] = [
                self._error(
                    CANDIDATE_REVIEW_GATE_STUB,
                    "review_scope_invalid",
                    "The configured Candidate decision references a Supervisor "
                    "outside the proposal.",
                )
            ]
            return update

        update["candidate_feedback"] = [decision]
        if decision.revised_preferences is not None:
            update["candidate_preferences"] = [decision.revised_preferences]

        if decision.action is CandidateReviewAction.APPROVE:
            if (
                len(proposed_by_id) != self.config.shortlist_size
                or len(decision.supervisor_ids) != self.config.shortlist_size
                or set(decision.supervisor_ids) != set(proposed_by_id)
            ):
                update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
                update["tool_errors"] = [
                    self._error(
                        CANDIDATE_REVIEW_GATE_STUB,
                        "approved_shortlist_incomplete",
                        "Candidate approval must cover the complete five-Supervisor proposal.",
                    )
                ]
                return update
            update["review_status"] = ReviewStatus.APPROVED
            return update

        if decision.action is CandidateReviewAction.REJECT:
            update["rejected_supervisors"] = [
                apply_candidate_review(proposed_by_id[supervisor_id], decision)
                for supervisor_id in decision.supervisor_ids
            ]
            update["review_status"] = ReviewStatus.REJECTED
        else:
            update["review_status"] = ReviewStatus.REQUEST_MORE

        if attempt >= self.config.max_review_retries:
            update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
            update["tool_errors"] = [
                self._error(
                    CANDIDATE_REVIEW_GATE_STUB,
                    "review_retry_exhausted",
                    "Candidate review refinement exceeded the configured retry limit.",
                )
            ]
        else:
            update["retry_counts"] = self._retry_counts(state, "review", attempt + 1)
        return update

    def route_after_candidate_review(self, state: ScholarPathState) -> ReviewRoute:
        """Route approval forward and bounded feedback paths back to planning."""
        if state["review_status"] is ReviewStatus.APPROVED:
            return SAVE_SHORTLISTED_SUPERVISORS
        if state["review_status"] in {ReviewStatus.REJECTED, ReviewStatus.REQUEST_MORE}:
            return PLAN_SUPERVISOR_SEARCHES
        return "__end__"

    def save_shortlisted_supervisors(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Persist the fixture shortlist only after the configured approval decision."""
        decision = state["candidate_feedback"][-1]
        shortlist = create_supervisor_shortlist(
            state["candidate_profile"].candidate_id,
            state["proposed_shortlist"],
            decision,
            generated_at=self.config.fixtures.generated_at,
            briefing="Candidate-approved shortlist awaiting its deterministic briefing.",
        )
        if len(shortlist.shortlisted_supervisors) != self.config.shortlist_size:
            raise ValueError("The completed fixture shortlist must contain five Supervisors")
        return {
            "shortlisted_supervisors": list(shortlist.shortlisted_supervisors),
            "supervisor_shortlist": shortlist,
            "execution_log": [SAVE_SHORTLISTED_SUPERVISORS],
        }

    def generate_shortlist_briefing(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Attach a deterministic briefing to the validated SupervisorShortlist."""
        shortlist = state["supervisor_shortlist"]
        if shortlist is None:
            raise ValueError("A SupervisorShortlist is required before briefing generation")
        count = len(shortlist.shortlisted_supervisors)
        briefing = (
            f"ScholarPath prepared {count} Candidate-approved, evidence-backed "
            "Supervisor recommendations."
        )
        completed_shortlist = shortlist.model_copy(update={"briefing": briefing})
        return {
            "shortlisted_supervisors": list(completed_shortlist.shortlisted_supervisors),
            "supervisor_shortlist": completed_shortlist,
            "shortlist_briefing": briefing,
            "review_status": ReviewStatus.COMPLETED,
            "execution_log": [GENERATE_SHORTLIST_BRIEFING],
        }


class _UnconfiguredPlanningModel:
    """Fail safely if a topology-only graph is accidentally executed."""

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        del planning_input
        raise PlanningModelInvocationError("No planning model was injected.")


class _UnconfiguredSupervisorSearch:
    """Fail safely if a topology-only graph is accidentally executed."""

    def __init__(self, provider: SearchProvider) -> None:
        self._provider = provider

    def search(self, query: str) -> tuple[SearchResult, ...]:
        del query
        raise SearchProviderError(
            "No Supervisor search adapter was injected.",
            provider=self._provider,
            category=SearchErrorCategory.AUTHENTICATION,
            retryable=False,
        )


class _LazyTavilySearch:
    """Defer Tavily credential validation until the fallback is actually routed."""

    def __init__(self, settings: TavilySearchSettings) -> None:
        self._settings = settings
        self._adapter: TavilySearchAdapter | None = None

    def search(self, query: str) -> tuple[SearchResult, ...]:
        if self._adapter is None:
            try:
                configuration = self._settings.for_search_adapter()
            except ProviderConfigurationError:
                raise SearchProviderError(
                    "Tavily fallback credentials are not configured.",
                    provider=SearchProvider.TAVILY,
                    category=SearchErrorCategory.AUTHENTICATION,
                    retryable=False,
                ) from None
            self._adapter = TavilySearchAdapter(configuration)
        return self._adapter.search(query)


def _with_failure_injection(
    port: SupervisorSearchPort,
    provider: SearchProvider,
    mode: DiscoveryFailureMode,
) -> SupervisorSearchPort:
    """Enable deterministic failures only when explicitly configured."""
    if mode is DiscoveryFailureMode.OFF:
        return port
    return FailureInjectingSupervisorSearch(port, provider, mode)


def build_scholarpath_graph(
    config: GraphFixtureConfig | None = None,
    *,
    planning_model: PlanningModelPort | None = None,
    supervisor_search: SupervisorSearchPort | None = None,
    tavily_search: SupervisorSearchPort | None = None,
    observability: LangSmithObservability | None = None,
) -> ScholarPathGraph:
    """Compile the graph without instantiating a provider or requiring credentials."""
    resolved_model = planning_model or _UnconfiguredPlanningModel()
    resolved_search = supervisor_search or _UnconfiguredSupervisorSearch(SearchProvider.YOU)
    resolved_tavily_search = tavily_search or _UnconfiguredSupervisorSearch(SearchProvider.TAVILY)
    nodes = DeterministicScholarPathNodes(
        config or GraphFixtureConfig(),
        ResearchPlanningAgent(resolved_model),
        resolved_search,
        resolved_tavily_search,
    )
    builder: StateGraph[ScholarPathState, None, ScholarPathState, ScholarPathState] = StateGraph(
        ScholarPathState
    )

    builder.add_node(LOAD_CANDIDATE_PREFERENCES, nodes.load_candidate_preferences)
    planning_metadata = (
        observability.planning_node_metadata
        if observability is not None
        else {
            "component": "research_planning_agent",
            "prompt_version": RESEARCH_PLANNING_PROMPT_VERSION,
        }
    )
    builder.add_node(
        PLAN_SUPERVISOR_SEARCHES,
        nodes.plan_supervisor_searches,
        metadata=planning_metadata,
    )
    builder.add_node(DISCOVER_PROSPECTIVE_SUPERVISORS, nodes.discover_prospective_supervisors)
    builder.add_node(ENOUGH_SUPERVISORS_FOUND, nodes.enough_supervisors_found)
    builder.add_node(FALLBACK_SUPERVISOR_SEARCH, nodes.fallback_supervisor_search)
    builder.add_node(DEDUPLICATE_SUPERVISORS, nodes.deduplicate_supervisors)
    builder.add_node(EXTRACT_SUPERVISOR_EVIDENCE, nodes.extract_supervisor_evidence)
    builder.add_node(SUPERVISOR_EVIDENCE_SUFFICIENT, nodes.supervisor_evidence_sufficient)
    builder.add_node(RETRY_ALTERNATE_EVIDENCE_SOURCE, nodes.retry_alternate_evidence_source)
    builder.add_node(EVALUATE_RESEARCH_FIT, nodes.evaluate_research_fit)
    builder.add_node(REVIEW_FIT_ASSESSMENTS, nodes.review_fit_assessments)
    builder.add_node(SYNTHESIZE_SUPERVISOR_SHORTLIST, nodes.synthesize_supervisor_shortlist)
    builder.add_node(CANDIDATE_REVIEW_GATE_STUB, nodes.candidate_review_gate_stub)
    builder.add_node(SAVE_SHORTLISTED_SUPERVISORS, nodes.save_shortlisted_supervisors)
    builder.add_node(GENERATE_SHORTLIST_BRIEFING, nodes.generate_shortlist_briefing)

    builder.add_edge(START, LOAD_CANDIDATE_PREFERENCES)
    builder.add_edge(LOAD_CANDIDATE_PREFERENCES, PLAN_SUPERVISOR_SEARCHES)
    builder.add_conditional_edges(
        PLAN_SUPERVISOR_SEARCHES,
        nodes.route_after_planning,
        [DISCOVER_PROSPECTIVE_SUPERVISORS, END],
    )
    builder.add_edge(DISCOVER_PROSPECTIVE_SUPERVISORS, ENOUGH_SUPERVISORS_FOUND)
    builder.add_conditional_edges(
        ENOUGH_SUPERVISORS_FOUND,
        nodes.route_after_discovery,
        [
            DISCOVER_PROSPECTIVE_SUPERVISORS,
            FALLBACK_SUPERVISOR_SEARCH,
            DEDUPLICATE_SUPERVISORS,
            END,
        ],
    )
    builder.add_edge(FALLBACK_SUPERVISOR_SEARCH, ENOUGH_SUPERVISORS_FOUND)
    builder.add_edge(DEDUPLICATE_SUPERVISORS, EXTRACT_SUPERVISOR_EVIDENCE)
    builder.add_edge(EXTRACT_SUPERVISOR_EVIDENCE, SUPERVISOR_EVIDENCE_SUFFICIENT)
    builder.add_conditional_edges(
        SUPERVISOR_EVIDENCE_SUFFICIENT,
        nodes.route_after_evidence,
        [RETRY_ALTERNATE_EVIDENCE_SOURCE, EVALUATE_RESEARCH_FIT, END],
    )
    builder.add_edge(RETRY_ALTERNATE_EVIDENCE_SOURCE, EXTRACT_SUPERVISOR_EVIDENCE)
    builder.add_edge(EVALUATE_RESEARCH_FIT, REVIEW_FIT_ASSESSMENTS)
    builder.add_edge(REVIEW_FIT_ASSESSMENTS, SYNTHESIZE_SUPERVISOR_SHORTLIST)
    builder.add_edge(SYNTHESIZE_SUPERVISOR_SHORTLIST, CANDIDATE_REVIEW_GATE_STUB)
    builder.add_conditional_edges(
        CANDIDATE_REVIEW_GATE_STUB,
        nodes.route_after_candidate_review,
        [SAVE_SHORTLISTED_SUPERVISORS, PLAN_SUPERVISOR_SEARCHES, END],
    )
    builder.add_edge(SAVE_SHORTLISTED_SUPERVISORS, GENERATE_SHORTLIST_BRIEFING)
    builder.add_edge(GENERATE_SHORTLIST_BRIEFING, END)
    return builder.compile(name="ScholarPath M5 resilient Supervisor discovery graph")


def run_scholarpath_graph(
    config: GraphFixtureConfig | None = None,
    *,
    planning_model: PlanningModelPort | None = None,
    supervisor_search: SupervisorSearchPort | None = None,
    tavily_search: SupervisorSearchPort | None = None,
    application_settings: ApplicationSettings | None = None,
    openai_settings: OpenAIPlanningSettings | None = None,
    you_settings: YouSearchSettings | None = None,
    tavily_settings: TavilySearchSettings | None = None,
    langsmith_settings: LangSmithSettings | None = None,
) -> ScholarPathState:
    """Compose providers lazily, then execute one optionally traced graph run."""
    resolved_config = config or GraphFixtureConfig()
    resolved_application_settings = application_settings or load_settings()
    resolved_langsmith_settings = langsmith_settings or load_langsmith_settings()
    observability = LangSmithObservability(
        resolved_langsmith_settings, resolved_application_settings.environment
    )
    resolved_planning_model = planning_model
    if resolved_planning_model is None:
        resolved_openai_settings = openai_settings or load_openai_planning_settings()
        resolved_planning_model = OpenAIPlanningModelAdapter(
            resolved_openai_settings.for_planning_model()
        )
    resolved_supervisor_search = supervisor_search
    if resolved_supervisor_search is None:
        resolved_you_settings = you_settings or load_you_search_settings()
        resolved_supervisor_search = YouSearchAdapter(resolved_you_settings.for_search_adapter())
    resolved_tavily_search = tavily_search
    if resolved_tavily_search is None:
        resolved_tavily_settings = tavily_settings or load_tavily_search_settings()
        resolved_tavily_search = _LazyTavilySearch(resolved_tavily_settings)
    resolved_supervisor_search = _with_failure_injection(
        resolved_supervisor_search,
        SearchProvider.YOU,
        resolved_application_settings.discovery_failure_mode,
    )
    resolved_tavily_search = _with_failure_injection(
        resolved_tavily_search,
        SearchProvider.TAVILY,
        resolved_application_settings.discovery_failure_mode,
    )
    graph = build_scholarpath_graph(
        resolved_config,
        planning_model=resolved_planning_model,
        supervisor_search=resolved_supervisor_search,
        tavily_search=resolved_tavily_search,
        observability=observability,
    )
    initial_state = create_initial_state(resolved_config.fixtures.candidate_profile)
    recursion_limit = (
        32
        + (2 * resolved_config.discovery_policy.maximum_you_retry_count)
        + (2 * resolved_config.discovery_policy.maximum_tavily_fallback_count)
        + (4 * resolved_config.max_evidence_retries)
        + (16 * resolved_config.max_review_retries)
    )
    runnable_config = observability.runnable_config(recursion_limit)
    with observability.activate():
        return cast(ScholarPathState, graph.invoke(initial_state, config=runnable_config))


def render_scholarpath_mermaid(config: GraphFixtureConfig | None = None) -> str:
    """Render the compiled graph structure without network access."""
    return build_scholarpath_graph(config).get_graph().draw_mermaid()
