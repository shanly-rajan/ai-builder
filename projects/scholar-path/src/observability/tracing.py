"""Optional LangSmith tracing with privacy-safe metadata."""

from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from typing import Final

from langchain_core.runnables import RunnableConfig
from langsmith import Client, trace, tracing_context

from ..agents.prompts import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    RESEARCH_PLANNING_PROMPT_VERSION,
)
from ..config import Environment, LangSmithSettings
from ..tools.supervisor_search import SearchErrorCategory, SearchProvider

GRAPH_VERSION: Final = "m11.1"
type TraceScalar = str | int | float | bool
type DiscoveryTraceCompletion = Callable[[int, int, SearchErrorCategory | None], None]
SAFE_TRACE_METADATA_KEYS: Final = (
    "application",
    "environment",
    "graph_version",
    "component",
    "prompt_version",
    "rubric_version",
    "provider",
    "attempt_number",
    "raw_result_count",
    "plausible_supervisor_count",
    "error_category",
    "fallback_search_used",
    "discovery_route",
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
    ) -> dict[str, TraceScalar]:
        """Build aggregate per-attempt metadata with all search content omitted."""
        return sanitize_trace_metadata(
            {
                **self.discovery_node_metadata(
                    provider=provider,
                    fallback_search_used=fallback_search_used,
                ),
                "attempt_number": attempt_number,
                "raw_result_count": raw_result_count,
                "plausible_supervisor_count": plausible_supervisor_count,
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
        ) -> None:
            del raw_result_count, plausible_supervisor_count, error_category

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
