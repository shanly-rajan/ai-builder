"""Optional LangSmith tracing with privacy-safe metadata."""

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from typing import Final

from langchain_core.runnables import RunnableConfig
from langsmith import Client, tracing_context

from ..agents.prompts import RESEARCH_PLANNING_PROMPT_VERSION
from ..config import Environment, LangSmithSettings

GRAPH_VERSION: Final = "m4"
type TraceScalar = str | int | float | bool
SAFE_TRACE_METADATA_KEYS: Final = (
    "application",
    "environment",
    "graph_version",
    "component",
    "prompt_version",
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
            api_key=api_key.get_secret_value(),
            hide_inputs=True,
            hide_outputs=True,
            omit_traced_runtime_info=True,
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
