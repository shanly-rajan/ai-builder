"""Optional LangSmith tracing with privacy-safe metadata."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Final, Protocol

from langchain_core.runnables import RunnableConfig
from langsmith import Client, trace, tracing_context
from langsmith.utils import LangSmithRetry

from ..agents.prompts import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    RESEARCH_PLANNING_PROMPT_VERSION,
)
from ..config import Environment, LangSmithSettings
from ..domain import SearchResultRejectionCounts
from ..tools.supervisor_search import SearchErrorCategory, SearchProvider

GRAPH_VERSION: Final = "m13"
LANGSMITH_RETRY_STATUS_CODES: Final = (408, 425, 429, 500, 502, 503, 504)
type TraceScalar = str | int | float | bool


def langsmith_timeout_ms(settings: LangSmithSettings) -> int:
    """Convert the validated request deadline into the SDK's millisecond unit."""
    return max(1, round(settings.request_timeout_seconds * 1_000))


def langsmith_retry_config(settings: LangSmithSettings) -> LangSmithRetry:
    """Return one finite retry policy shared by tracing and evaluation clients."""
    maximum = settings.maximum_retry_count
    return LangSmithRetry(
        total=maximum,
        connect=maximum,
        read=maximum,
        status=maximum,
        other=maximum,
        redirect=0,
        allowed_methods=None,
        status_forcelist=LANGSMITH_RETRY_STATUS_CODES,
        backoff_factor=0.25,
        respect_retry_after_header=True,
    )


class DiscoveryTraceCompletion(Protocol):
    """Complete one discovery span with privacy-safe aggregate counts only."""

    def __call__(
        self,
        raw_result_count: int,
        plausible_supervisor_count: int,
        error_category: SearchErrorCategory | None,
        rejection_counts: SearchResultRejectionCounts | None = None,
    ) -> None: ...


SAFE_TRACE_METADATA_KEYS: Final = (
    "application",
    "environment",
    "graph_version",
    "component",
    "prompt_version",
    "rubric_version",
    "provider",
    "model_provider",
    "attempt_number",
    "raw_result_count",
    "plausible_supervisor_count",
    "rejected_person_not_established_count",
    "rejected_academic_context_not_established_count",
    "rejected_identity_conflict_count",
    "rejected_institution_not_established_count",
    "rejected_incomplete_institution_count",
    "error_category",
    "fallback_search_used",
    "discovery_route",
    "candidate_review_outcome",
    "evaluation_target",
    "evaluation_scenario_id",
)


def sanitize_trace_metadata(metadata: Mapping[str, object]) -> dict[str, TraceScalar]:
    """Copy only allowlisted scalar metadata; sensitive and unknown fields are omitted."""
    sanitized: dict[str, TraceScalar] = {}
    for key in SAFE_TRACE_METADATA_KEYS:
        value = metadata.get(key)
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
    return sanitized


class LangSmithObservability:
    """Create scoped graph traces only when LangSmith is explicitly enabled."""

    def __init__(self, settings: LangSmithSettings, environment: Environment) -> None:
        self._settings = settings
        self._environment = environment

    @property
    def tags(self) -> list[str]:
        """Return non-sensitive graph tags inherited by child runs."""
        return [
            "application:scholarpath",
            f"environment:{self._environment.value}",
            f"graph-version:{GRAPH_VERSION}",
        ]

    @property
    def graph_metadata(self) -> dict[str, TraceScalar]:
        """Return the fixed graph-level metadata allowlist."""
        return sanitize_trace_metadata(
            {
                "application": "scholarpath",
                "environment": self._environment.value,
                "graph_version": GRAPH_VERSION,
            }
        )

    @property
    def planning_node_metadata(self) -> dict[str, TraceScalar]:
        """Return safe metadata attached specifically to the planning node."""
        return sanitize_trace_metadata(
            {
                **self.graph_metadata,
                "component": "research_planning_agent",
                "prompt_version": RESEARCH_PLANNING_PROMPT_VERSION,
            }
        )

    @property
    def evidence_node_metadata(self) -> dict[str, TraceScalar]:
        """Return safe metadata without source URL or extracted page content."""
        return sanitize_trace_metadata(
            {
                **self.graph_metadata,
                "component": "evidence_verification_agent",
                "prompt_version": EVIDENCE_VERIFICATION_PROMPT_VERSION,
            }
        )

    def research_fit_node_metadata(self, rubric_version: str) -> dict[str, TraceScalar]:
        """Return safe scoring metadata for the rubric used by this graph."""
        return sanitize_trace_metadata(
            {
                **self.graph_metadata,
                "component": "research_fit_evaluation_agent",
                "prompt_version": RESEARCH_FIT_PROMPT_VERSION,
                "rubric_version": rubric_version,
            }
        )

    @property
    def independent_review_node_metadata(self) -> dict[str, TraceScalar]:
        """Return safe reviewer metadata without Candidate or evidence payloads."""
        return sanitize_trace_metadata(
            {
                **self.graph_metadata,
                "component": "independent_review_agent",
                "prompt_version": INDEPENDENT_REVIEW_PROMPT_VERSION,
            }
        )

    def discovery_node_metadata(
        self,
        *,
        provider: SearchProvider,
        fallback_search_used: bool,
    ) -> dict[str, TraceScalar]:
        """Return fixed discovery-node metadata without query or result content."""
        return sanitize_trace_metadata(
            {
                **self.graph_metadata,
                "component": "supervisor_discovery_agent",
                "provider": provider.value,
                "fallback_search_used": fallback_search_used,
                "discovery_route": "fallback" if fallback_search_used else "primary",
            }
        )

    def discovery_attempt_metadata(
        self,
        *,
        provider: SearchProvider,
        attempt_number: int,
        raw_result_count: int,
        plausible_supervisor_count: int,
        error_category: SearchErrorCategory | None,
        fallback_search_used: bool,
        rejection_counts: SearchResultRejectionCounts | None = None,
    ) -> dict[str, TraceScalar]:
        """Build aggregate per-attempt metadata with all search content omitted."""
        safe_rejection_counts = rejection_counts or SearchResultRejectionCounts()
        return sanitize_trace_metadata(
            {
                **self.discovery_node_metadata(
                    provider=provider,
                    fallback_search_used=fallback_search_used,
                ),
                "attempt_number": attempt_number,
                "raw_result_count": raw_result_count,
                "plausible_supervisor_count": plausible_supervisor_count,
                "rejected_person_not_established_count": (
                    safe_rejection_counts.person_not_established
                ),
                "rejected_academic_context_not_established_count": (
                    safe_rejection_counts.academic_context_not_established
                ),
                "rejected_identity_conflict_count": (safe_rejection_counts.identity_conflict),
                "rejected_institution_not_established_count": (
                    safe_rejection_counts.institution_not_established
                ),
                "rejected_incomplete_institution_count": (
                    safe_rejection_counts.incomplete_institution
                ),
                "error_category": (error_category.value if error_category is not None else "none"),
            }
        )

    @contextmanager
    def discovery_attempt_span(
        self,
        *,
        provider: SearchProvider,
        attempt_number: int,
        fallback_search_used: bool,
    ) -> Iterator[DiscoveryTraceCompletion]:
        """Trace one provider attempt using empty payloads and safe aggregate metadata only."""

        def no_op_completion(
            raw_result_count: int,
            plausible_supervisor_count: int,
            error_category: SearchErrorCategory | None,
            rejection_counts: SearchResultRejectionCounts | None = None,
        ) -> None:
            del raw_result_count, plausible_supervisor_count, error_category, rejection_counts

        if not self._settings.tracing:
            yield no_op_completion
            return

        initial_metadata = self.discovery_attempt_metadata(
            provider=provider,
            attempt_number=attempt_number,
            raw_result_count=0,
            plausible_supervisor_count=0,
            error_category=None,
            fallback_search_used=fallback_search_used,
        )
        completed = False
        with trace(
            f"{provider.value}_supervisor_search_attempt",
            run_type="tool",
            inputs={},
            tags=["component:supervisor-discovery", f"provider:{provider.value}"],
            metadata=initial_metadata,
        ) as run:

            def complete(
                raw_result_count: int,
                plausible_supervisor_count: int,
                error_category: SearchErrorCategory | None,
                rejection_counts: SearchResultRejectionCounts | None = None,
            ) -> None:
                nonlocal completed
                completed = True
                run.end(
                    outputs={},
                    metadata=self.discovery_attempt_metadata(
                        provider=provider,
                        attempt_number=attempt_number,
                        raw_result_count=raw_result_count,
                        plausible_supervisor_count=plausible_supervisor_count,
                        error_category=error_category,
                        fallback_search_used=fallback_search_used,
                        rejection_counts=rejection_counts,
                    ),
                )

            yield complete
            if not completed:
                complete(0, 0, SearchErrorCategory.UNKNOWN)

    def runnable_config(self, recursion_limit: int) -> RunnableConfig:
        """Build a privacy-safe root RunnableConfig for one graph execution."""
        return {
            "run_name": "scholarpath_graph",
            "recursion_limit": recursion_limit,
            "tags": self.tags,
            "metadata": self.graph_metadata,
        }

    @contextmanager
    def activate(self) -> Iterator[None]:
        """Enable one scoped trace, or explicitly disable tracing without a client."""
        if not self._settings.tracing:
            with tracing_context(enabled=False):
                yield
            return

        api_key = self._settings.require_api_key()
        client = Client(
            api_url=str(self._settings.endpoint),
            api_key=api_key.get_secret_value(),
            timeout_ms=langsmith_timeout_ms(self._settings),
            retry_config=langsmith_retry_config(self._settings),
            hide_inputs=True,
            hide_outputs=True,
            omit_traced_runtime_info=True,
            workspace_id=self._settings.workspace_id,
        )
        try:
            with tracing_context(
                enabled=True,
                project_name=self._settings.project,
                tags=self.tags,
                metadata=self.graph_metadata,
                client=client,
            ):
                yield
            client.flush(timeout=5.0)
        finally:
            client.close(timeout=5.0)
