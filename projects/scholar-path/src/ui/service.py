"""LangGraph-backed application service used by the Streamlit presentation layer."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import ExitStack
from threading import RLock
from typing import Any, Protocol, cast

from langchain_core.runnables import RunnableConfig
from langgraph.types import Command, StateSnapshot

from ..config import ApplicationSettings, load_settings
from ..domain import CandidateProfile
from ..graph import (
    CandidateReviewResponse,
    ScholarPathRuntime,
    ScholarPathState,
    build_scholarpath_runtime,
    candidate_review_response_value,
    create_initial_state,
    open_local_sqlite_checkpointer,
)
from .controller import (
    candidate_review_payload_from_snapshot,
    canonical_node_names_from_stream_part,
    checkpoint_token_from_snapshot,
    project_graph_state_to_ui,
)
from .models import GraphProgressEvent, UiRunSnapshot

type ProgressSink = Callable[[GraphProgressEvent], None]


class ScholarPathApplicationPort(Protocol):
    """Typed start, inspect, and resume boundary consumed by the UI."""

    def start(
        self,
        candidate_profile: CandidateProfile,
        thread_id: str,
        progress_sink: ProgressSink | None = None,
    ) -> UiRunSnapshot:
        """Start a new isolated research thread and stream safe progress."""
        ...

    def inspect(self, thread_id: str) -> UiRunSnapshot | None:
        """Read the persisted UI projection without advancing the graph."""
        ...

    def resume(
        self,
        thread_id: str,
        checkpoint_token: str,
        response: CandidateReviewResponse,
        progress_sink: ProgressSink | None = None,
    ) -> UiRunSnapshot:
        """Resume exactly one current Candidate review checkpoint."""
        ...


class ScholarPathApplicationError(RuntimeError):
    """Sanitized, recoverable service failure safe for Candidate display."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.safe_message = message


class ScholarPathApplicationService:
    """Serialize access to one compiled graph and project checkpoints for the UI."""

    def __init__(
        self,
        runtime: ScholarPathRuntime,
        *,
        close_callback: Callable[[], None] | None = None,
    ) -> None:
        self._runtime = runtime
        self._close_callback = close_callback
        self._lock = RLock()

    def start(
        self,
        candidate_profile: CandidateProfile,
        thread_id: str,
        progress_sink: ProgressSink | None = None,
    ) -> UiRunSnapshot:
        """Reject thread reuse, then stream a submitted Candidate profile to pause or END."""
        with self._lock:
            config = self._runtime.runnable_config(thread_id)
            existing = self._runtime.graph.get_state(config)
            if existing.values:
                raise ScholarPathApplicationError(
                    "thread_already_started",
                    "This research thread already exists. Reopen it instead of starting again.",
                )
            self._stream(
                create_initial_state(candidate_profile),
                config,
                starting_sequence=0,
                progress_sink=progress_sink,
            )
            return self._inspect_locked(config)

    def inspect(self, thread_id: str) -> UiRunSnapshot | None:
        """Inspect one isolated checkpoint without putting graph state in Session State."""
        with self._lock:
            config = self._runtime.runnable_config(thread_id)
            snapshot = self._runtime.graph.get_state(config)
            if not snapshot.values:
                return None
            return self._project_snapshot(snapshot)

    def resume(
        self,
        thread_id: str,
        checkpoint_token: str,
        response: CandidateReviewResponse,
        progress_sink: ProgressSink | None = None,
    ) -> UiRunSnapshot:
        """Validate the latest checkpoint before consuming one explicit Candidate action."""
        with self._lock:
            config = self._runtime.runnable_config(thread_id)
            snapshot = self._runtime.graph.get_state(config)
            if not snapshot.values:
                raise ScholarPathApplicationError(
                    "thread_not_found",
                    "This research thread could not be found. Start a new Supervisor search.",
                )
            current_token = checkpoint_token_from_snapshot(snapshot)
            if checkpoint_token != current_token:
                raise ScholarPathApplicationError(
                    "stale_candidate_review",
                    "This review changed in another session. Refresh before submitting again.",
                )
            if candidate_review_payload_from_snapshot(snapshot) is None:
                raise ScholarPathApplicationError(
                    "candidate_review_unavailable",
                    "This research thread is not waiting for Candidate review.",
                )
            state = cast(ScholarPathState, snapshot.values)
            self._stream(
                Command(resume=candidate_review_response_value(response)),
                config,
                starting_sequence=len(state["execution_log"]),
                progress_sink=progress_sink,
            )
            return self._inspect_locked(config)

    def _stream(
        self,
        graph_input: ScholarPathState | Command[Any],
        config: RunnableConfig,
        *,
        starting_sequence: int,
        progress_sink: ProgressSink | None,
    ) -> None:
        """Consume v2 updates while forwarding only canonical node names."""
        sequence = starting_sequence
        try:
            with self._runtime.observability.activate():
                for part in self._runtime.graph.stream(
                    graph_input,
                    config=config,
                    stream_mode="updates",
                    version="v2",
                    durability="sync",
                ):
                    for node_name in canonical_node_names_from_stream_part(part):
                        sequence += 1
                        if progress_sink is not None:
                            progress_sink(
                                GraphProgressEvent(
                                    sequence=sequence,
                                    node_name=node_name,
                                )
                            )
        except ScholarPathApplicationError:
            raise
        except Exception as error:
            raise ScholarPathApplicationError(
                "graph_execution_unavailable",
                "ScholarPath could not complete this step. Check provider settings and retry.",
            ) from error

    def _inspect_locked(self, config: RunnableConfig) -> UiRunSnapshot:
        snapshot = self._runtime.graph.get_state(config)
        if not snapshot.values:
            raise ScholarPathApplicationError(
                "checkpoint_unavailable",
                "ScholarPath could not recover the latest research checkpoint.",
            )
        return self._project_snapshot(snapshot)

    @staticmethod
    def _project_snapshot(snapshot: StateSnapshot) -> UiRunSnapshot:
        state = cast(ScholarPathState, snapshot.values)
        return project_graph_state_to_ui(
            state,
            checkpoint_token=checkpoint_token_from_snapshot(snapshot),
            review_payload=candidate_review_payload_from_snapshot(snapshot),
        )

    def close(self) -> None:
        """Release the locally owned SQLite connection when the resource is retired."""
        if self._close_callback is not None:
            self._close_callback()


def create_local_scholarpath_application_service(
    settings: ApplicationSettings | None = None,
) -> ScholarPathApplicationService:
    """Create the local SQLite-backed production service outside the Streamlit module."""
    resolved_settings = settings or load_settings()
    resources = ExitStack()
    try:
        checkpointer = resources.enter_context(
            open_local_sqlite_checkpointer(resolved_settings.checkpoint_database_path)
        )
        runtime = build_scholarpath_runtime(
            checkpointer=checkpointer,
            application_settings=resolved_settings,
        )
    except Exception:
        resources.close()
        raise
    return ScholarPathApplicationService(runtime, close_callback=resources.close)
