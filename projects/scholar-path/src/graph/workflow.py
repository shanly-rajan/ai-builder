"""ScholarPath graph with an injected M3 Research Planning Agent."""

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
    LangSmithSettings,
    OpenAIPlanningSettings,
    YouSearchSettings,
    load_langsmith_settings,
    load_openai_planning_settings,
    load_settings,
    load_you_search_settings,
)
from ..domain import (
    CandidatePreferenceRevision,
    CandidateReviewAction,
    CandidateReviewDecision,
    ProspectiveSupervisor,
    SearchResult,
    apply_candidate_review,
    create_supervisor_shortlist,
    validate_research_fit_evidence,
)
from ..observability import LangSmithObservability
from ..tools import (
    SupervisorSearchError,
    SupervisorSearchPort,
    SupervisorSearchResponseError,
    SupervisorSearchTimeoutError,
    SupervisorSearchTransportError,
    YouSearchAdapter,
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

type DiscoveryRoute = Literal["fallback_supervisor_search", "deduplicate_supervisors", "__end__"]
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
    review_decisions: tuple[CandidateReviewDecision, ...] = field(
        default_factory=lambda: (default_review_decision(),)
    )
    primary_discovery_count: int = 8
    fallback_discovery_count: int = 0
    minimum_discovery_results: int = 5
    initial_evidence_count: int = 6
    alternate_evidence_count: int = 6
    minimum_verified_supervisors: int = 5
    shortlist_size: int = REQUIRED_SHORTLIST_SIZE
    max_discovery_retries: int = 1
    max_evidence_retries: int = 1
    max_review_retries: int = 1

    def __post_init__(self) -> None:
        """Reject invalid fixture controls before graph construction."""
        fixture_limits = {
            "primary_discovery_count": (
                self.primary_discovery_count,
                len(self.fixtures.raw_search_results),
            ),
            "fallback_discovery_count": (
                self.fallback_discovery_count,
                len(self.fixtures.raw_search_results),
            ),
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
            "minimum_discovery_results": self.minimum_discovery_results,
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
            ("minimum_discovery_results", self.minimum_discovery_results),
            ("minimum_verified_supervisors", self.minimum_verified_supervisors),
        ):
            if value < self.shortlist_size:
                raise ValueError(f"{field_name} must not be less than shortlist_size")
        if len(self.fixtures.research_fit_assessments) < self.shortlist_size:
            raise ValueError("fixtures must contain enough Research Fit assessments")

        retry_limits = {
            "max_discovery_retries": self.max_discovery_retries,
            "max_evidence_retries": self.max_evidence_retries,
            "max_review_retries": self.max_review_retries,
        }
        for field_name, value in retry_limits.items():
            if value < 0:
                raise ValueError(f"{field_name} must not be negative")
            if value > MAX_CONFIGURED_RETRIES:
                raise ValueError(f"{field_name} must not exceed {MAX_CONFIGURED_RETRIES}")


class DeterministicScholarPathNodes:
    """Walking-skeleton nodes with injected planning and primary discovery boundaries."""

    def __init__(
        self,
        config: GraphFixtureConfig,
        planning_agent: ResearchPlanningAgent,
        supervisor_search: SupervisorSearchPort | None = None,
    ) -> None:
        self.config = config
        self.planning_agent = planning_agent
        self.supervisor_search = supervisor_search
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
        return {"search_plan": plan, "execution_log": [PLAN_SUPERVISOR_SEARCHES]}

    @staticmethod
    def route_after_planning(state: ScholarPathState) -> PlanningRoute:
        """Continue only when planning produced a validated SearchPlan."""
        if state["search_plan"] is not None:
            return DISCOVER_PROSPECTIVE_SUPERVISORS
        return "__end__"

    def discover_prospective_supervisors(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Execute planned You.com queries and append typed discovery output."""
        update: ScholarPathStateUpdate = {
            "raw_search_results": [],
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
                    "Supervisor discovery has no configured search adapter.",
                )
            ]
            return update

        search_results: list[SearchResult] = []
        search_errors: list[ToolErrorRecord] = []
        for planned_query in search_plan.search_queries:
            try:
                search_results.extend(self.supervisor_search.search(planned_query.query))
            except SupervisorSearchError as error:
                retryable = isinstance(
                    error,
                    (SupervisorSearchTimeoutError, SupervisorSearchTransportError),
                ) or (isinstance(error, SupervisorSearchResponseError) and error.retryable)
                search_errors.append(
                    self._error(
                        DISCOVER_PROSPECTIVE_SUPERVISORS,
                        "supervisor_search_failed",
                        "A planned Supervisor search could not return normalized results.",
                        recoverable=retryable,
                    )
                )
            except Exception:
                search_errors.append(
                    self._error(
                        DISCOVER_PROSPECTIVE_SUPERVISORS,
                        "supervisor_search_failed",
                        "A planned Supervisor search could not return normalized results.",
                    )
                )

        try:
            discovery = self.discovery_agent.discover(search_plan, search_results)
        except (TypeError, ValueError):
            update["tool_errors"] = [
                *search_errors,
                self._error(
                    DISCOVER_PROSPECTIVE_SUPERVISORS,
                    "supervisor_discovery_output_invalid",
                    "Supervisor discovery could not produce a valid structured result.",
                ),
            ]
            return update

        selected = discovery.prospective_supervisors[: self.config.primary_discovery_count]
        update["raw_search_results"] = [
            RawSupervisorSearchResult.from_prospective_supervisor(supervisor)
            for supervisor in selected
        ]
        if search_errors:
            update["tool_errors"] = search_errors
        return update

    def _available_prospective_supervisors(
        self, state: ScholarPathState
    ) -> tuple[ProspectiveSupervisor, ...]:
        rejected_ids = {supervisor.supervisor_id for supervisor in state["rejected_supervisors"]}
        available = (
            result.to_prospective_supervisor()
            for result in state["raw_search_results"]
            if result.supervisor_id not in rejected_ids
        )
        return deduplicate_prospective_supervisors(available)

    def enough_supervisors_found(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Log discovery sufficiency and record bounded exhaustion when necessary."""
        update: ScholarPathStateUpdate = {"execution_log": [ENOUGH_SUPERVISORS_FOUND]}
        enough = (
            len(self._available_prospective_supervisors(state))
            >= self.config.minimum_discovery_results
        )
        exhausted = state["retry_counts"]["discovery"] >= self.config.max_discovery_retries
        if not enough and exhausted:
            update["review_status"] = ReviewStatus.RETRY_EXHAUSTED
            update["tool_errors"] = [
                self._error(
                    ENOUGH_SUPERVISORS_FOUND,
                    "discovery_retry_exhausted",
                    "Supervisor discovery remained below the configured minimum.",
                )
            ]
        return update

    def route_after_discovery(self, state: ScholarPathState) -> DiscoveryRoute:
        """Route deterministically after the logged discovery sufficiency check."""
        if (
            len(self._available_prospective_supervisors(state))
            >= self.config.minimum_discovery_results
        ):
            return DEDUPLICATE_SUPERVISORS
        if state["review_status"] is ReviewStatus.RETRY_EXHAUSTED:
            return "__end__"
        return FALLBACK_SUPERVISOR_SEARCH

    def fallback_supervisor_search(self, state: ScholarPathState) -> ScholarPathStateUpdate:
        """Append one configured fallback fixture batch and increment its retry count."""
        current_retry = state["retry_counts"]["discovery"]
        start = self.config.primary_discovery_count + (
            current_retry * self.config.fallback_discovery_count
        )
        stop = start + self.config.fallback_discovery_count
        return {
            "raw_search_results": list(self.config.fixtures.raw_search_results[start:stop]),
            "retry_counts": self._retry_counts(state, "discovery", current_retry + 1),
            "execution_log": [FALLBACK_SUPERVISOR_SEARCH],
        }

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

    def search(self, query: str) -> tuple[SearchResult, ...]:
        del query
        raise SupervisorSearchTransportError("No Supervisor search adapter was injected.")


def build_scholarpath_graph(
    config: GraphFixtureConfig | None = None,
    *,
    planning_model: PlanningModelPort | None = None,
    supervisor_search: SupervisorSearchPort | None = None,
    observability: LangSmithObservability | None = None,
) -> ScholarPathGraph:
    """Compile the graph without instantiating a provider or requiring credentials."""
    resolved_model = planning_model or _UnconfiguredPlanningModel()
    resolved_search = supervisor_search or _UnconfiguredSupervisorSearch()
    nodes = DeterministicScholarPathNodes(
        config or GraphFixtureConfig(),
        ResearchPlanningAgent(resolved_model),
        resolved_search,
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
        [FALLBACK_SUPERVISOR_SEARCH, DEDUPLICATE_SUPERVISORS, END],
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
    return builder.compile(name="ScholarPath M4 You.com discovery graph")


def run_scholarpath_graph(
    config: GraphFixtureConfig | None = None,
    *,
    planning_model: PlanningModelPort | None = None,
    supervisor_search: SupervisorSearchPort | None = None,
    application_settings: ApplicationSettings | None = None,
    openai_settings: OpenAIPlanningSettings | None = None,
    you_settings: YouSearchSettings | None = None,
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
    graph = build_scholarpath_graph(
        resolved_config,
        planning_model=resolved_planning_model,
        supervisor_search=resolved_supervisor_search,
        observability=observability,
    )
    initial_state = create_initial_state(resolved_config.fixtures.candidate_profile)
    recursion_limit = (
        32
        + (4 * resolved_config.max_discovery_retries)
        + (4 * resolved_config.max_evidence_retries)
        + (16 * resolved_config.max_review_retries)
    )
    runnable_config = observability.runnable_config(recursion_limit)
    with observability.activate():
        return cast(ScholarPathState, graph.invoke(initial_state, config=runnable_config))


def render_scholarpath_mermaid(config: GraphFixtureConfig | None = None) -> str:
    """Render the compiled graph structure without network access."""
    return build_scholarpath_graph(config).get_graph().draw_mermaid()
