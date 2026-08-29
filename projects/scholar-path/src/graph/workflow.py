"""ScholarPath graph with resilient, policy-routed Supervisor discovery."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal, Protocol, cast

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command, interrupt
from pydantic import HttpUrl, ValidationError

from ..agents import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    RESEARCH_PLANNING_PROMPT_VERSION,
    EvidenceExtractionInput,
    EvidenceModelInvocationError,
    EvidenceModelOutputError,
    EvidenceVerificationAgent,
    EvidenceVerificationModelPort,
    OpenAIEvidenceVerificationModelAdapter,
    OpenAIPlanningModelAdapter,
    OpenAIResearchFitAdapter,
    PlanningFailureKind,
    PlanningInput,
    PlanningModelInvocationError,
    PlanningModelPort,
    ResearchFitEvaluationAgent,
    ResearchFitEvaluationError,
    ResearchFitInput,
    ResearchFitModelInvocationError,
    ResearchFitModelPort,
    ResearchPlanningAgent,
    ResearchPlanningError,
    ShortlistSynthesisAgent,
    StructuredEvidenceExtractionResult,
    StructuredResearchFitResult,
    StructuredSearchPlanResponse,
    SupervisorDiscoveryAgent,
    deduplicate_prospective_supervisors,
)
from ..agents.independent_review import (
    IndependentReviewAgent,
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewModelPort,
    IndependentReviewPolicy,
    IndependentReviewResult,
)
from ..agents.nebius_review import NebiusReviewModelAdapter
from ..agents.prompts import INDEPENDENT_REVIEW_PROMPT_VERSION
from ..config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    LangSmithSettings,
    NebiusReviewSettings,
    OpenAIEvidenceSettings,
    OpenAIPlanningSettings,
    OpenAIResearchFitSettings,
    ProviderConfigurationError,
    TavilyExtractionSettings,
    TavilySearchSettings,
    YouSearchSettings,
    load_langsmith_settings,
    load_nebius_review_settings,
    load_openai_evidence_settings,
    load_openai_planning_settings,
    load_openai_research_fit_settings,
    load_settings,
    load_tavily_extraction_settings,
    load_tavily_search_settings,
    load_you_search_settings,
)
from ..domain import (
    CandidatePreferenceRevision,
    CandidateReviewAction,
    CandidateReviewDecision,
    IndependentReviewStatus,
    ProspectiveSupervisor,
    ResearchFitRubric,
    SearchPlan,
    SearchResult,
    SupervisorVerificationRecord,
    VerificationStatus,
    apply_candidate_review,
    create_supervisor_shortlist,
)
from ..observability import LangSmithObservability
from ..tools import (
    ContentExtractionError,
    ContentExtractionErrorCategory,
    ContentExtractionPort,
    ContentExtractionProvider,
    ExtractedContent,
    FailureInjectingSupervisorSearch,
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
    SupervisorSearchError,
    SupervisorSearchPort,
    TavilyExtractionAdapter,
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
    preferences_from_profile,
)
from .persistence import create_test_checkpointer
from .review import (
    CandidateApproveResponse,
    CandidateRejectResponse,
    CandidateRequestMoreResponse,
    CandidateReviewResponse,
    build_candidate_review_interrupt_payload,
    candidate_review_payload_from_graph_output,
    candidate_review_response_value,
    parse_candidate_review_response,
)
from .state import (
    RawSupervisorSearchResult,
    ReviewStatus,
    ScholarPathState,
    ScholarPathStateUpdate,
    ToolErrorRecord,
    create_initial_state,
)
from .verification import (
    EvidenceExtractionAttempt,
    EvidenceVerificationRoute,
    VerificationPolicy,
    alternate_official_source_query,
    classify_evidence_source_kind,
    route_after_evidence_sufficiency,
    select_alternate_official_source,
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
CANDIDATE_REVIEW_GATE: Final = "candidate_review_gate"
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
    CANDIDATE_REVIEW_GATE,
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
type ReviewRoute = Literal[
    "candidate_review_gate",
    "save_shortlisted_supervisors",
    "plan_supervisor_searches",
    "__end__",
]
type PlanningRoute = Literal["discover_prospective_supervisors", "__end__"]
type ScholarPathGraph = CompiledStateGraph[
    ScholarPathState, None, ScholarPathState, ScholarPathState
]


class UtcClockPort(Protocol):
    """Return an aware UTC timestamp without coupling graph nodes to wall-clock time."""

    def now(self) -> datetime:
        """Return the current UTC time."""
        ...


class _SystemUtcClock:
    """Production clock used when callers do not inject a deterministic test clock."""

    def now(self) -> datetime:
        """Return the current aware UTC timestamp."""
        return datetime.now(UTC)


def _validated_utc_timestamp(clock: UtcClockPort) -> datetime:
    """Reject naive or non-UTC clock values before they enter persisted graph state."""
    timestamp = clock.now()
    if timestamp.tzinfo is None or timestamp.utcoffset() != timedelta(0):
        raise ValueError("The injected UTC clock must return an aware UTC timestamp")
    return timestamp.astimezone(UTC)


@dataclass(frozen=True, slots=True)
class GraphFixtureConfig:
    """Immutable controls for deterministic walking-skeleton route scenarios."""

    fixtures: WalkingSkeletonFixtures = field(default_factory=build_walking_skeleton_fixtures)
    discovery_policy: DiscoveryPolicy = field(default_factory=DiscoveryPolicy)
    verification_policy: VerificationPolicy = field(default_factory=VerificationPolicy)
    research_fit_rubric: ResearchFitRubric = field(default_factory=ResearchFitRubric)
    independent_review_policy: IndependentReviewPolicy = field(
        default_factory=IndependentReviewPolicy
    )
    shortlist_size: int = REQUIRED_SHORTLIST_SIZE
    max_review_retries: int = 1
    max_review_input_retries: int = 2

    def __post_init__(self) -> None:
        """Reject invalid fixture controls before graph construction."""
        positive_values = {
            "shortlist_size": self.shortlist_size,
        }
        for field_name, value in positive_values.items():
            if value < 1:
                raise ValueError(f"{field_name} must be at least 1")

        if self.shortlist_size != REQUIRED_SHORTLIST_SIZE:
            raise ValueError(
                f"shortlist_size must be {REQUIRED_SHORTLIST_SIZE} for the M2 walking skeleton"
            )
        if self.verification_policy.minimum_verified_supervisors < self.shortlist_size:
            raise ValueError("minimum_verified_supervisors must not be less than shortlist_size")
        retry_limits = {
            "max_review_retries": self.max_review_retries,
            "max_review_input_retries": self.max_review_input_retries,
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
        content_extractor: ContentExtractionPort | None = None,
        evidence_model: EvidenceVerificationModelPort | None = None,
        research_fit_model: ResearchFitModelPort | None = None,
        independent_review_model: IndependentReviewModelPort | None = None,
        alternate_evidence_search: SupervisorSearchPort | None = None,
        utc_clock: UtcClockPort | None = None,
    ) -> None:
        self.config = config
        self.planning_agent = planning_agent
        self.supervisor_search = supervisor_search
        self.tavily_search = tavily_search
        self.content_extractor = content_extractor
        self.alternate_evidence_search = alternate_evidence_search
        self.utc_clock = utc_clock if utc_clock is not None else _SystemUtcClock()
        self.discovery_agent = SupervisorDiscoveryAgent()
        if evidence_model is None:
            raise ValueError("Evidence verification requires an injected model port")
        self.evidence_agent = EvidenceVerificationAgent(evidence_model)
        if research_fit_model is None:
            raise ValueError("Research Fit evaluation requires an injected model port")
        self.research_fit_agent = ResearchFitEvaluationAgent(research_fit_model)
        if independent_review_model is None:
            raise ValueError("Independent review requires an injected model port")
        self.independent_review_agent = IndependentReviewAgent(
            independent_review_model,
            policy=config.independent_review_policy,
        )
        self.shortlist_agent = ShortlistSynthesisAgent(max_results=config.shortlist_size)

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
            "verified_supervisors": [],
            "verification_records": [],
            "alternate_evidence_sources": {},
            "research_fit_assessments": [],
            "research_fit_review_records": [],
            "proposed_shortlist": None,
            "retry_counts": self._retry_counts(state, "evidence", 0),
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
        """Retrieve known pages and convert only grounded structured claims into evidence."""
        update: ScholarPathStateUpdate = {
            "verification_records": [],
            "verified_supervisors": [],
            "evidence_extraction_attempts": [],
            "execution_log": [EXTRACT_SUPERVISOR_EVIDENCE],
        }
        records_by_id = {
            record.prospective_supervisor.supervisor_id: record
            for record in state["verification_records"]
        }
        attempts: list[EvidenceExtractionAttempt] = []
        errors: list[ToolErrorRecord] = []
        retrying_alternate = state["retry_counts"]["evidence"] > 0

        for supervisor in state["prospective_supervisors"]:
            previous = records_by_id.get(supervisor.supervisor_id)
            if (
                retrying_alternate
                and previous is not None
                and previous.verification_status is not VerificationStatus.PARTIALLY_VERIFIED
            ):
                continue

            source_url = supervisor.profile_url
            source_kind = classify_evidence_source_kind(supervisor.profile_url)
            alternate = False
            if retrying_alternate:
                alternate_source = state["alternate_evidence_sources"].get(supervisor.supervisor_id)
                if alternate_source is None:
                    continue
                source_url = alternate_source.source_url
                source_kind = alternate_source.source_kind
                alternate = True

            prior_evidence = previous.evidence if previous is not None else ()
            attempt_number = (
                sum(
                    attempt.supervisor_id == supervisor.supervisor_id
                    and attempt.discovery_round == state["discovery_round"]
                    for attempt in [*state["evidence_extraction_attempts"], *attempts]
                )
                + 1
            )
            if self.content_extractor is None:
                extraction_error = ContentExtractionError(
                    "No content extraction adapter was injected.",
                    provider=ContentExtractionProvider.TAVILY,
                    category=ContentExtractionErrorCategory.AUTHENTICATION,
                    retryable=False,
                    source_url=str(source_url),
                )
                extracted_content = None
            else:
                try:
                    extracted_content = self.content_extractor.extract(source_url)
                    extraction_error = None
                except ContentExtractionError as caught_error:
                    extracted_content = None
                    extraction_error = caught_error
                except Exception:
                    extracted_content = None
                    extraction_error = ContentExtractionError(
                        "Content extraction failed unexpectedly.",
                        provider=ContentExtractionProvider.TAVILY,
                        category=ContentExtractionErrorCategory.PROVIDER,
                        retryable=False,
                        source_url=str(source_url),
                    )

            if extraction_error is not None:
                attempts.append(
                    EvidenceExtractionAttempt(
                        supervisor_id=supervisor.supervisor_id,
                        source_url=source_url,
                        source_kind=source_kind,
                        attempt_number=attempt_number,
                        discovery_round=state["discovery_round"],
                        alternate_source=alternate,
                        successful=False,
                        error_category=extraction_error.category,
                    )
                )
                records_by_id[supervisor.supervisor_id] = (
                    self.evidence_agent.build_verification_record(
                        supervisor,
                        prior_evidence,
                        additional_concerns=(
                            "A requested Supervisor source page could not be extracted.",
                        ),
                    )
                )
                errors.append(
                    self._error(
                        EXTRACT_SUPERVISOR_EVIDENCE,
                        f"content_extraction_{extraction_error.category.value}",
                        "A Supervisor source page could not be extracted.",
                        recoverable=extraction_error.retryable,
                    )
                )
                continue

            assert extracted_content is not None
            if not alternate or str(extracted_content.source_url) != str(source_url):
                source_kind = classify_evidence_source_kind(extracted_content.source_url)
            attempts.append(
                EvidenceExtractionAttempt(
                    supervisor_id=supervisor.supervisor_id,
                    source_url=extracted_content.source_url,
                    source_kind=source_kind,
                    attempt_number=attempt_number,
                    discovery_round=state["discovery_round"],
                    alternate_source=alternate,
                    successful=True,
                )
            )
            try:
                new_claims = self.evidence_agent.extract_claims(
                    supervisor,
                    extracted_content,
                    source_kind,
                )
            except EvidenceModelOutputError:
                records_by_id[supervisor.supervisor_id] = (
                    self.evidence_agent.build_verification_record(
                        supervisor,
                        prior_evidence,
                        additional_concerns=(
                            "The retrieved page could not satisfy the structured "
                            "evidence contract.",
                        ),
                    )
                )
                errors.append(
                    self._error(
                        EXTRACT_SUPERVISOR_EVIDENCE,
                        "evidence_model_output_invalid",
                        "Evidence extraction returned invalid structured output.",
                        recoverable=True,
                    )
                )
            except EvidenceModelInvocationError:
                records_by_id[supervisor.supervisor_id] = (
                    self.evidence_agent.build_verification_record(
                        supervisor,
                        prior_evidence,
                        additional_concerns=("The evidence model could not process the page.",),
                    )
                )
                errors.append(
                    self._error(
                        EXTRACT_SUPERVISOR_EVIDENCE,
                        "evidence_model_failed",
                        "Evidence extraction could not call the structured model.",
                        recoverable=True,
                    )
                )
            else:
                records_by_id[supervisor.supervisor_id] = (
                    self.evidence_agent.build_verification_record(
                        supervisor,
                        (*prior_evidence, *new_claims),
                    )
                )

        ordered_records: list[SupervisorVerificationRecord] = []
        for supervisor in state["prospective_supervisors"]:
            record = records_by_id.get(supervisor.supervisor_id)
            if record is None:
                record = self.evidence_agent.build_verification_record(
                    supervisor,
                    (),
                    additional_concerns=("No official evidence page was available.",),
                )
            ordered_records.append(record)

        update["verification_records"] = ordered_records
        update["verified_supervisors"] = [
            record.verified_supervisor
            for record in ordered_records
            if record.verified_supervisor is not None
        ]
        update["evidence_extraction_attempts"] = attempts
        if errors:
            update["tool_errors"] = errors
        return update

    def supervisor_evidence_sufficient(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Apply the pure verification policy and surface bounded partial completion."""
        update: ScholarPathStateUpdate = {"execution_log": [SUPERVISOR_EVIDENCE_SUFFICIENT]}
        route = route_after_evidence_sufficiency(
            self.config.verification_policy,
            tuple(state["verification_records"]),
            alternate_retry_count=state["retry_counts"]["evidence"],
        )
        if route is EvidenceVerificationRoute.STOP_PARTIAL:
            update["review_status"] = ReviewStatus.EVIDENCE_INCOMPLETE
            update["tool_errors"] = [
                self._error(
                    SUPERVISOR_EVIDENCE_SUFFICIENT,
                    "supervisor_evidence_incomplete",
                    "Supervisor evidence remained below the configured verification minimum.",
                    recoverable=True,
                )
            ]
        return update

    def route_after_evidence(self, state: ScholarPathState) -> EvidenceRoute:
        """Map the pure evidence route into canonical graph edge names."""
        route = route_after_evidence_sufficiency(
            self.config.verification_policy,
            tuple(state["verification_records"]),
            alternate_retry_count=state["retry_counts"]["evidence"],
        )
        return route.value

    def retry_alternate_evidence_source(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Search once per partial record and retain only a selected official source URL."""
        current_retry = state["retry_counts"]["evidence"]
        alternate_sources = dict(state["alternate_evidence_sources"])
        errors: list[ToolErrorRecord] = []
        partial_records = [
            record
            for record in state["verification_records"]
            if record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
        ]
        for record in partial_records:
            supervisor = record.prospective_supervisor
            query = alternate_official_source_query(supervisor)
            if self.alternate_evidence_search is None:
                errors.append(
                    self._error(
                        RETRY_ALTERNATE_EVIDENCE_SOURCE,
                        "alternate_evidence_search_not_configured",
                        "No alternate official-source search adapter is configured.",
                        recoverable=True,
                    )
                )
                continue
            try:
                results = self.alternate_evidence_search.search(query)
            except SearchProviderError as error:
                errors.append(
                    self._search_error_record(
                        RETRY_ALTERNATE_EVIDENCE_SOURCE,
                        error.provider,
                        error,
                    )
                )
                if not error.retryable:
                    break
                continue
            except Exception:
                errors.append(
                    self._error(
                        RETRY_ALTERNATE_EVIDENCE_SOURCE,
                        "alternate_evidence_search_failed",
                        "Alternate official-source search failed unexpectedly.",
                        recoverable=True,
                    )
                )
                continue

            selected = select_alternate_official_source(
                supervisor,
                results,
                query=query,
            )
            if selected is None:
                errors.append(
                    self._error(
                        RETRY_ALTERNATE_EVIDENCE_SOURCE,
                        "alternate_official_source_not_found",
                        "No alternate official Supervisor source could be selected.",
                        recoverable=True,
                    )
                )
                continue
            alternate_sources[supervisor.supervisor_id] = selected

        update: ScholarPathStateUpdate = {
            "retry_counts": self._retry_counts(state, "evidence", current_retry + 1),
            "alternate_evidence_sources": alternate_sources,
            "execution_log": [RETRY_ALTERNATE_EVIDENCE_SOURCE],
        }
        if errors:
            update["tool_errors"] = errors
        return update

    def evaluate_research_fit(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Evaluate each Verified Supervisor through the evidence-bound model port."""
        assessments = []
        errors: list[ToolErrorRecord] = []
        latest_preferences = (
            state["candidate_preferences"][-1] if state["candidate_preferences"] else None
        )
        for supervisor in state["verified_supervisors"]:
            try:
                assessment = self.research_fit_agent.evaluate(
                    state["candidate_profile"],
                    supervisor,
                    preferences=latest_preferences,
                    rubric=self.config.research_fit_rubric,
                )
            except ResearchFitEvaluationError as error:
                errors.append(
                    self._error(
                        EVALUATE_RESEARCH_FIT,
                        f"research_fit_{error.kind.value}",
                        "A Research Fit assessment failed at the typed model boundary "
                        f"after {error.attempts} attempt(s).",
                        recoverable=True,
                    )
                )
                continue
            assessments.append(assessment)

        update: ScholarPathStateUpdate = {
            "research_fit_assessments": assessments,
            "execution_log": [EVALUATE_RESEARCH_FIT],
        }
        if errors:
            update["tool_errors"] = errors
        return update

    def review_fit_assessments(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Independently review each assessment without mutating its M7 score contract."""
        supervisors_by_id = {
            supervisor.supervisor_id: supervisor for supervisor in state["verified_supervisors"]
        }
        records = []
        errors: list[ToolErrorRecord] = []
        for assessment in state["research_fit_assessments"]:
            supervisor = supervisors_by_id.get(assessment.supervisor_id)
            if supervisor is None:
                errors.append(
                    self._error(
                        REVIEW_FIT_ASSESSMENTS,
                        "independent_review_supervisor_missing",
                        "Independent review could not match an assessment to a Verified "
                        "Supervisor.",
                        recoverable=True,
                    )
                )
                continue
            record = self.independent_review_agent.review(
                state["candidate_profile"],
                supervisor,
                assessment,
            )
            records.append(record)
            if record.review_status is IndependentReviewStatus.UNAVAILABLE:
                failure_kind = (
                    record.failure_kind.value if record.failure_kind is not None else "unavailable"
                )
                errors.append(
                    self._error(
                        REVIEW_FIT_ASSESSMENTS,
                        f"independent_review_{failure_kind}",
                        "Independent Research Fit review was unavailable; the original "
                        "assessment was preserved with reduced confidence.",
                        recoverable=True,
                    )
                )

        update: ScholarPathStateUpdate = {
            "research_fit_review_records": records,
            "execution_log": [REVIEW_FIT_ASSESSMENTS],
        }
        if errors:
            update["tool_errors"] = errors
        return update

    def synthesize_supervisor_shortlist(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Create a deterministic, evidence-explained proposal for Candidate review."""
        try:
            proposed = self.shortlist_agent.synthesize(
                state["candidate_profile"].candidate_id,
                state["verified_supervisors"],
                state["research_fit_assessments"],
                _validated_utc_timestamp(self.utc_clock),
                state["research_fit_review_records"],
            )
        except ValueError:
            return {
                "proposed_shortlist": None,
                "review_status": ReviewStatus.RETRY_EXHAUSTED,
                "tool_errors": [
                    self._error(
                        SYNTHESIZE_SUPERVISOR_SHORTLIST,
                        "research_fit_proposal_incomplete",
                        "No valid preliminary Supervisor shortlist could be synthesized.",
                        recoverable=True,
                    )
                ],
                "execution_log": [SYNTHESIZE_SUPERVISOR_SHORTLIST],
            }
        return {
            "proposed_shortlist": proposed,
            "review_status": ReviewStatus.PROPOSED,
            "execution_log": [SYNTHESIZE_SUPERVISOR_SHORTLIST],
        }

    def _invalid_candidate_review_update(
        self,
        state: ScholarPathState,
        *,
        code: str,
        message: str,
    ) -> ScholarPathStateUpdate:
        """Record invalid resume data and either re-prompt or stop at a strict bound."""
        invalid_attempts = state["retry_counts"]["review_input"] + 1
        retry_exhausted = invalid_attempts >= self.config.max_review_input_retries
        return {
            "candidate_review_error": message,
            "review_status": (
                ReviewStatus.RETRY_EXHAUSTED if retry_exhausted else ReviewStatus.PROPOSED
            ),
            "retry_counts": self._retry_counts(state, "review_input", invalid_attempts),
            "tool_errors": [
                self._error(
                    CANDIDATE_REVIEW_GATE,
                    code,
                    message,
                    recoverable=not retry_exhausted,
                )
            ],
            "execution_log": [CANDIDATE_REVIEW_GATE],
        }

    def candidate_review_gate(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Pause for an explicit Candidate response, then validate it deterministically."""
        proposed_shortlist = state["proposed_shortlist"]
        if proposed_shortlist is None:
            return {
                "review_status": ReviewStatus.RETRY_EXHAUSTED,
                "tool_errors": [
                    self._error(
                        CANDIDATE_REVIEW_GATE,
                        "review_proposal_missing",
                        "Candidate review requires a valid preliminary Supervisor shortlist.",
                        recoverable=True,
                    )
                ],
                "execution_log": [CANDIDATE_REVIEW_GATE],
            }

        review_attempt = state["retry_counts"]["review"]
        payload = build_candidate_review_interrupt_payload(
            proposed_shortlist,
            review_iteration=review_attempt + 1,
            maximum_review_iterations=self.config.max_review_retries + 1,
            validation_error=state["candidate_review_error"],
        )
        raw_response = interrupt(payload.model_dump(mode="json"))
        try:
            response = parse_candidate_review_response(raw_response)
        except ValidationError:
            return self._invalid_candidate_review_update(
                state,
                code="review_response_invalid",
                message="Candidate review response does not match an allowed action schema.",
            )

        proposed_by_id = {
            recommendation.supervisor.supervisor_id: recommendation.supervisor
            for recommendation in proposed_shortlist.recommendations
        }
        if isinstance(response, CandidateApproveResponse):
            response_ids = response.supervisor_ids
        elif isinstance(response, CandidateRejectResponse):
            response_ids = tuple(item.supervisor_id for item in response.rejections)
        else:
            response_ids = ()
        unknown_ids = [
            supervisor_id for supervisor_id in response_ids if supervisor_id not in proposed_by_id
        ]
        if unknown_ids:
            return self._invalid_candidate_review_update(
                state,
                code="review_scope_invalid",
                message=(
                    "Candidate review references Supervisor identifiers outside the current "
                    "proposal."
                ),
            )

        base_update: ScholarPathStateUpdate = {
            "candidate_review_error": None,
            "retry_counts": self._retry_counts(state, "review_input", 0),
            "execution_log": [CANDIDATE_REVIEW_GATE],
        }
        if isinstance(response, CandidateApproveResponse):
            approval = CandidateReviewDecision(
                action=CandidateReviewAction.APPROVE,
                supervisor_ids=response.supervisor_ids,
                reason="Candidate explicitly approved these Supervisors.",
            )
            base_update["candidate_feedback"] = [approval]
            base_update["review_status"] = ReviewStatus.APPROVED
            return base_update

        if isinstance(response, CandidateRejectResponse):
            rejection_decisions = [
                CandidateReviewDecision(
                    action=CandidateReviewAction.REJECT,
                    supervisor_ids=(rejection.supervisor_id,),
                    reason=rejection.reason,
                )
                for rejection in response.rejections
            ]
            base_update["candidate_feedback"] = rejection_decisions
            base_update["rejected_supervisors"] = [
                apply_candidate_review(
                    proposed_by_id[decision.supervisor_ids[0]],
                    decision,
                )
                for decision in rejection_decisions
            ]
            base_update["review_status"] = ReviewStatus.REJECTED
        else:
            assert isinstance(response, CandidateRequestMoreResponse)
            request_more = CandidateReviewDecision(
                action=CandidateReviewAction.REQUEST_MORE,
                supervisor_ids=tuple(proposed_by_id),
                reason="Candidate requested a refined Supervisor search.",
                revised_preferences=response.revised_preferences,
            )
            base_update["candidate_feedback"] = [request_more]
            base_update["candidate_preferences"] = [response.revised_preferences]
            base_update["review_status"] = ReviewStatus.REQUEST_MORE

        if review_attempt >= self.config.max_review_retries:
            base_update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
            base_update["tool_errors"] = [
                self._error(
                    CANDIDATE_REVIEW_GATE,
                    "review_retry_exhausted",
                    "Candidate review refinement reached the configured iteration limit.",
                )
            ]
        else:
            base_update["retry_counts"] = {
                **state["retry_counts"],
                "review": review_attempt + 1,
                "review_input": 0,
            }
        return base_update

    def route_after_candidate_review(self, state: ScholarPathState) -> ReviewRoute:
        """Route approval forward and bounded feedback paths back to planning."""
        if state["review_status"] is ReviewStatus.APPROVED:
            return SAVE_SHORTLISTED_SUPERVISORS
        if state["review_status"] in {ReviewStatus.REJECTED, ReviewStatus.REQUEST_MORE}:
            return PLAN_SUPERVISOR_SEARCHES
        if (
            state["review_status"] is ReviewStatus.PROPOSED
            and state["candidate_review_error"] is not None
        ):
            return CANDIDATE_REVIEW_GATE
        return "__end__"

    def save_shortlisted_supervisors(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Persist only the explicit Supervisor IDs in the latest approval."""
        decision = state["candidate_feedback"][-1]
        proposed_shortlist = state["proposed_shortlist"]
        if proposed_shortlist is None:
            raise ValueError("Candidate approval requires a preliminary Supervisor shortlist")
        shortlist = create_supervisor_shortlist(
            state["candidate_profile"].candidate_id,
            [recommendation.supervisor for recommendation in proposed_shortlist.recommendations],
            decision,
            generated_at=self.config.fixtures.generated_at,
            briefing="Candidate-approved shortlist awaiting its deterministic briefing.",
        )
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


class _UnconfiguredContentExtraction:
    """Fail safely if a topology-only graph reaches evidence extraction."""

    def extract(self, source_url: str | HttpUrl) -> ExtractedContent:
        raise ContentExtractionError(
            "No content extraction adapter was injected.",
            provider=ContentExtractionProvider.TAVILY,
            category=ContentExtractionErrorCategory.AUTHENTICATION,
            retryable=False,
            source_url=str(source_url),
        )


class _UnconfiguredEvidenceModel:
    """Fail safely if a topology-only graph reaches structured evidence extraction."""

    def extract(
        self, extraction_input: EvidenceExtractionInput
    ) -> StructuredEvidenceExtractionResult:
        del extraction_input
        raise EvidenceModelInvocationError("No evidence model was injected.")


class _UnconfiguredResearchFitModel:
    """Fail safely if a topology-only graph reaches Research Fit evaluation."""

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        del fit_input, rubric
        raise ResearchFitModelInvocationError("No Research Fit model was injected.")


class _UnconfiguredIndependentReviewModel:
    """Fail safely if a topology-only graph reaches independent review."""

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        del review_input
        raise IndependentReviewModelInvocationError("No independent-review model was injected.")


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


class _LazyTavilyExtraction:
    """Defer Tavily Extract credential validation until a known page is requested."""

    def __init__(self, settings: TavilyExtractionSettings) -> None:
        self._settings = settings
        self._adapter: TavilyExtractionAdapter | None = None

    def extract(self, source_url: str | HttpUrl) -> ExtractedContent:
        if self._adapter is None:
            try:
                configuration = self._settings.for_extraction_adapter()
            except ProviderConfigurationError:
                raise ContentExtractionError(
                    "Tavily Extract credentials are not configured.",
                    provider=ContentExtractionProvider.TAVILY,
                    category=ContentExtractionErrorCategory.AUTHENTICATION,
                    retryable=False,
                    source_url=str(source_url),
                ) from None
            self._adapter = TavilyExtractionAdapter(configuration)
        return self._adapter.extract(source_url)


class _LazyOpenAIEvidenceModel:
    """Defer OpenAI evidence-model validation until extracted content is available."""

    def __init__(self, settings: OpenAIEvidenceSettings) -> None:
        self._settings = settings
        self._adapter: OpenAIEvidenceVerificationModelAdapter | None = None

    def extract(
        self, extraction_input: EvidenceExtractionInput
    ) -> StructuredEvidenceExtractionResult:
        if self._adapter is None:
            try:
                configuration = self._settings.for_evidence_model()
            except ProviderConfigurationError:
                raise EvidenceModelInvocationError(
                    "OpenAI evidence-model credentials are not configured."
                ) from None
            self._adapter = OpenAIEvidenceVerificationModelAdapter(configuration)
        return self._adapter.extract(extraction_input)


class _LazyOpenAIResearchFitModel:
    """Defer OpenAI Research Fit validation until a Verified Supervisor is evaluated."""

    def __init__(self, settings: OpenAIResearchFitSettings) -> None:
        self._settings = settings
        self._adapter: OpenAIResearchFitAdapter | None = None

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        if self._adapter is None:
            try:
                configuration = self._settings.for_research_fit_model()
            except ProviderConfigurationError:
                raise ResearchFitModelInvocationError(
                    "OpenAI Research Fit credentials are not configured."
                ) from None
            self._adapter = OpenAIResearchFitAdapter(configuration)
        return self._adapter.evaluate(fit_input, rubric)


class _LazyNebiusReviewModel:
    """Defer Nebius credential validation until an assessment is reviewed."""

    def __init__(self, settings: NebiusReviewSettings) -> None:
        self._settings = settings
        self._adapter: NebiusReviewModelAdapter | None = None

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        if self._adapter is None:
            try:
                configuration = self._settings.for_review_model()
            except ProviderConfigurationError:
                raise IndependentReviewModelInvocationError(
                    "Nebius independent-review credentials are not configured."
                ) from None
            self._adapter = NebiusReviewModelAdapter(configuration)
        return self._adapter.review(review_input)


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
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    planning_model: PlanningModelPort | None = None,
    supervisor_search: SupervisorSearchPort | None = None,
    tavily_search: SupervisorSearchPort | None = None,
    content_extractor: ContentExtractionPort | None = None,
    evidence_model: EvidenceVerificationModelPort | None = None,
    research_fit_model: ResearchFitModelPort | None = None,
    independent_review_model: IndependentReviewModelPort | None = None,
    alternate_evidence_search: SupervisorSearchPort | None = None,
    observability: LangSmithObservability | None = None,
    utc_clock: UtcClockPort | None = None,
) -> ScholarPathGraph:
    """Compile the graph without instantiating a provider or requiring credentials."""
    resolved_config = config or GraphFixtureConfig()
    resolved_model = planning_model or _UnconfiguredPlanningModel()
    resolved_search = supervisor_search or _UnconfiguredSupervisorSearch(SearchProvider.YOU)
    resolved_tavily_search = tavily_search or _UnconfiguredSupervisorSearch(SearchProvider.TAVILY)
    resolved_content_extractor = content_extractor or _UnconfiguredContentExtraction()
    resolved_evidence_model = evidence_model or _UnconfiguredEvidenceModel()
    resolved_research_fit_model = research_fit_model or _UnconfiguredResearchFitModel()
    resolved_independent_review_model = (
        independent_review_model or _UnconfiguredIndependentReviewModel()
    )
    resolved_alternate_search = alternate_evidence_search or resolved_tavily_search
    nodes = DeterministicScholarPathNodes(
        resolved_config,
        ResearchPlanningAgent(resolved_model),
        resolved_search,
        resolved_tavily_search,
        resolved_content_extractor,
        resolved_evidence_model,
        resolved_research_fit_model,
        resolved_independent_review_model,
        resolved_alternate_search,
        utc_clock,
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
    builder.add_node(
        EXTRACT_SUPERVISOR_EVIDENCE,
        nodes.extract_supervisor_evidence,
        metadata=(
            observability.evidence_node_metadata
            if observability is not None
            else {
                "component": "evidence_verification_agent",
                "prompt_version": EVIDENCE_VERIFICATION_PROMPT_VERSION,
            }
        ),
    )
    builder.add_node(SUPERVISOR_EVIDENCE_SUFFICIENT, nodes.supervisor_evidence_sufficient)
    builder.add_node(RETRY_ALTERNATE_EVIDENCE_SOURCE, nodes.retry_alternate_evidence_source)
    builder.add_node(
        EVALUATE_RESEARCH_FIT,
        nodes.evaluate_research_fit,
        metadata=(
            observability.research_fit_node_metadata(resolved_config.research_fit_rubric.version)
            if observability is not None
            else {
                "component": "research_fit_evaluation_agent",
                "prompt_version": RESEARCH_FIT_PROMPT_VERSION,
                "rubric_version": resolved_config.research_fit_rubric.version,
            }
        ),
    )
    builder.add_node(
        REVIEW_FIT_ASSESSMENTS,
        nodes.review_fit_assessments,
        metadata=(
            observability.independent_review_node_metadata
            if observability is not None
            else {
                "component": "independent_review_agent",
                "prompt_version": INDEPENDENT_REVIEW_PROMPT_VERSION,
            }
        ),
    )
    builder.add_node(SYNTHESIZE_SUPERVISOR_SHORTLIST, nodes.synthesize_supervisor_shortlist)
    builder.add_node(CANDIDATE_REVIEW_GATE, nodes.candidate_review_gate)
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
    builder.add_edge(SYNTHESIZE_SUPERVISOR_SHORTLIST, CANDIDATE_REVIEW_GATE)
    builder.add_conditional_edges(
        CANDIDATE_REVIEW_GATE,
        nodes.route_after_candidate_review,
        [CANDIDATE_REVIEW_GATE, SAVE_SHORTLISTED_SUPERVISORS, PLAN_SUPERVISOR_SEARCHES, END],
    )
    builder.add_edge(SAVE_SHORTLISTED_SUPERVISORS, GENERATE_SHORTLIST_BRIEFING)
    builder.add_edge(GENERATE_SHORTLIST_BRIEFING, END)
    return builder.compile(
        checkpointer=checkpointer,
        name="ScholarPath M9 durable Candidate review graph",
    )


def run_scholarpath_graph(
    config: GraphFixtureConfig | None = None,
    *,
    thread_id: str,
    candidate_review_responses: Sequence[CandidateReviewResponse | Mapping[str, object]] = (),
    checkpointer: BaseCheckpointSaver[Any] | None = None,
    planning_model: PlanningModelPort | None = None,
    supervisor_search: SupervisorSearchPort | None = None,
    tavily_search: SupervisorSearchPort | None = None,
    content_extractor: ContentExtractionPort | None = None,
    evidence_model: EvidenceVerificationModelPort | None = None,
    research_fit_model: ResearchFitModelPort | None = None,
    independent_review_model: IndependentReviewModelPort | None = None,
    alternate_evidence_search: SupervisorSearchPort | None = None,
    application_settings: ApplicationSettings | None = None,
    openai_settings: OpenAIPlanningSettings | None = None,
    you_settings: YouSearchSettings | None = None,
    tavily_settings: TavilySearchSettings | None = None,
    tavily_extraction_settings: TavilyExtractionSettings | None = None,
    openai_evidence_settings: OpenAIEvidenceSettings | None = None,
    openai_research_fit_settings: OpenAIResearchFitSettings | None = None,
    nebius_review_settings: NebiusReviewSettings | None = None,
    langsmith_settings: LangSmithSettings | None = None,
    utc_clock: UtcClockPort | None = None,
) -> ScholarPathState | dict[str, object]:
    """Execute or resume one isolated thread, stopping if no review response remains."""
    normalized_thread_id = thread_id.strip()
    if not normalized_thread_id:
        raise ValueError("thread_id must not be empty")
    if len(normalized_thread_id) > 255:
        raise ValueError("thread_id must not exceed 255 characters")
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
    resolved_content_extractor = content_extractor
    if resolved_content_extractor is None:
        resolved_extraction_settings = (
            tavily_extraction_settings or load_tavily_extraction_settings()
        )
        resolved_content_extractor = _LazyTavilyExtraction(resolved_extraction_settings)
    resolved_evidence_model = evidence_model
    if resolved_evidence_model is None:
        resolved_evidence_settings = openai_evidence_settings or load_openai_evidence_settings()
        resolved_evidence_model = _LazyOpenAIEvidenceModel(resolved_evidence_settings)
    resolved_research_fit_model = research_fit_model
    if resolved_research_fit_model is None:
        resolved_research_fit_settings = (
            openai_research_fit_settings or load_openai_research_fit_settings()
        )
        resolved_research_fit_model = _LazyOpenAIResearchFitModel(resolved_research_fit_settings)
    resolved_independent_review_model = independent_review_model
    if resolved_independent_review_model is None:
        resolved_nebius_review_settings = nebius_review_settings or load_nebius_review_settings()
        resolved_independent_review_model = _LazyNebiusReviewModel(resolved_nebius_review_settings)
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
    resolved_alternate_evidence_search = alternate_evidence_search or resolved_tavily_search
    graph = build_scholarpath_graph(
        resolved_config,
        checkpointer=checkpointer or create_test_checkpointer(),
        planning_model=resolved_planning_model,
        supervisor_search=resolved_supervisor_search,
        tavily_search=resolved_tavily_search,
        content_extractor=resolved_content_extractor,
        evidence_model=resolved_evidence_model,
        research_fit_model=resolved_research_fit_model,
        independent_review_model=resolved_independent_review_model,
        alternate_evidence_search=resolved_alternate_evidence_search,
        observability=observability,
        utc_clock=utc_clock,
    )
    initial_state = create_initial_state(resolved_config.fixtures.candidate_profile)
    recursion_limit = (
        32
        + (2 * resolved_config.discovery_policy.maximum_you_retry_count)
        + (2 * resolved_config.discovery_policy.maximum_tavily_fallback_count)
        + (4 * resolved_config.verification_policy.maximum_alternate_source_retries)
        + (16 * resolved_config.max_review_retries)
        + (2 * resolved_config.max_review_input_retries)
    )
    runnable_config = observability.runnable_config(recursion_limit)
    runnable_config["configurable"] = {"thread_id": normalized_thread_id}
    with observability.activate():
        output: object = graph.invoke(initial_state, config=runnable_config)
        for response in candidate_review_responses:
            if not isinstance(output, Mapping):
                break
            if candidate_review_payload_from_graph_output(output) is None:
                break
            resume_value = (
                candidate_review_response_value(response)
                if isinstance(
                    response,
                    (
                        CandidateApproveResponse,
                        CandidateRejectResponse,
                        CandidateRequestMoreResponse,
                    ),
                )
                else dict(response)
            )
            output = graph.invoke(Command(resume=resume_value), config=runnable_config)
    return cast(ScholarPathState | dict[str, object], output)


def render_scholarpath_mermaid(config: GraphFixtureConfig | None = None) -> str:
    """Render the compiled graph structure without network access."""
    return build_scholarpath_graph(config).get_graph().draw_mermaid()
