"""Privacy-safe structured application logging for ScholarPath graph execution.

The logger deliberately projects graph state into aggregate counts and status
flags. It never serializes domain objects, identifiers, search content,
evidence, model prose, credentials, checkpoint data, or exception messages.
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Callable, Mapping
from contextlib import suppress
from enum import StrEnum
from functools import wraps
from io import TextIOBase
from typing import ParamSpec, TypeVar, cast

from langgraph.errors import GraphInterrupt

from ..config import LogLevel

type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list["JsonValue"] | dict[str, "JsonValue"]

P = ParamSpec("P")
R = TypeVar("R")

LOG_SCHEMA_VERSION = 1
APPLICATION_LOGGER_NAME = "scholarpath"

SCHOLARPATH_STATE_FIELDS = frozenset(
    {
        "candidate_profile",
        "candidate_preferences",
        "candidate_memory_records",
        "candidate_memory_processed_feedback_count",
        "candidate_memory_available",
        "search_plan",
        "raw_search_results",
        "prospective_supervisors",
        "verified_supervisors",
        "verification_records",
        "evidence_extraction_attempts",
        "alternate_source_attempts",
        "alternate_evidence_sources",
        "research_fit_assessments",
        "research_fit_review_records",
        "proposed_shortlist",
        "shortlisted_supervisors",
        "rejected_supervisors",
        "candidate_feedback",
        "candidate_review_error",
        "tool_errors",
        "search_attempts",
        "fallback_search_used",
        "fallback_search_round",
        "discovery_round",
        "retry_counts",
        "review_status",
        "execution_log",
        "supervisor_shortlist",
        "shortlist_briefing",
    }
)

_COUNT_FIELDS = frozenset(
    {
        "candidate_preferences",
        "candidate_memory_records",
        "raw_search_results",
        "prospective_supervisors",
        "verified_supervisors",
        "verification_records",
        "evidence_extraction_attempts",
        "alternate_source_attempts",
        "alternate_evidence_sources",
        "research_fit_assessments",
        "research_fit_review_records",
        "shortlisted_supervisors",
        "rejected_supervisors",
        "candidate_feedback",
        "tool_errors",
        "search_attempts",
        "execution_log",
    }
)
_PRESENCE_FIELDS = frozenset(
    {
        "candidate_profile",
        "search_plan",
        "proposed_shortlist",
        "candidate_review_error",
        "supervisor_shortlist",
        "shortlist_briefing",
    }
)
_BOOLEAN_FIELDS = frozenset({"candidate_memory_available", "fallback_search_used"})
_COUNTER_FIELDS = frozenset(
    {
        "candidate_memory_processed_feedback_count",
        "fallback_search_round",
        "discovery_round",
    }
)
_SAFE_RETRY_KEYS = ("discovery", "evidence", "review", "review_input")
_SAFE_REVIEW_STATUSES = frozenset(
    {
        "pending",
        "proposed",
        "approved",
        "rejected",
        "request_more",
        "completed",
        "retry_exhausted",
        "discovery_incomplete",
        "evidence_incomplete",
    }
)

GRAPH_LOG_NODE_NAMES = frozenset(
    {
        "__start__",
        "__end__",
        "load_candidate_preferences",
        "plan_supervisor_searches",
        "discover_prospective_supervisors",
        "enough_supervisors_found",
        "fallback_supervisor_search",
        "deduplicate_supervisors",
        "extract_supervisor_evidence",
        "supervisor_evidence_sufficient",
        "retry_alternate_evidence_source",
        "evaluate_research_fit",
        "review_fit_assessments",
        "synthesize_supervisor_shortlist",
        "candidate_review_gate",
        "learn_candidate_preferences",
        "save_shortlisted_supervisors",
        "generate_shortlist_briefing",
    }
)

_SAFE_PROVIDERS = frozenset(
    {
        "fixture",
        "langsmith",
        "mem0",
        "nebius",
        "openai",
        "sqlite",
        "tavily",
        "unconfigured",
        "you.com",
    }
)
_SAFE_PROVIDER_COMPONENTS = frozenset(
    {
        "candidate_preference_memory",
        "checkpoint_persistence",
        "evidence_verification",
        "independent_review",
        "langsmith_tracing",
        "research_fit_evaluation",
        "research_planning",
        "supervisor_discovery",
    }
)
_SAFE_PROVIDER_OPERATIONS = frozenset(
    {"checkpoint", "extract", "invoke", "load", "resume", "search", "store", "trace"}
)
_SAFE_PROVIDER_OUTCOMES = frozenset({"failed", "retrying", "skipped", "started", "succeeded"})
_SAFE_REVIEW_DECISIONS = frozenset({"accept", "revise"})
_SAFE_CONFIDENCE_VALUES = frozenset({"high", "low", "medium", "not_available"})

SAFE_PROVIDER_METADATA_KEYS = frozenset(
    {
        "attempt_number",
        "decision",
        "duration_ms",
        "fallback_used",
        "confidence",
        "failure_category",
        "overlooked_evidence_count",
        "result_count",
        "retryable",
        "structured_result_received",
        "unsupported_reference_count",
    }
)


class SanitizedErrorType(StrEnum):
    """Closed error taxonomy safe to serialize without provider messages."""

    GRAPH_INTERRUPT = "graph_interrupt"
    TIMEOUT = "timeout"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    TRANSPORT = "transport"
    CONFIGURATION = "configuration"
    INVALID_OUTPUT = "invalid_output"
    MODEL_INVOCATION = "model_invocation"
    INVALID_EVIDENCE_REFERENCE = "invalid_evidence_reference"
    PROVIDER = "provider"
    APPLICATION = "application"


_SAFE_FAILURE_CATEGORIES = frozenset(error_type.value for error_type in SanitizedErrorType)


def _safe_nonnegative_integer(value: object) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        return None
    return value


def _collection_count(value: object) -> int | None:
    if isinstance(value, (list, tuple, set, frozenset, Mapping)):
        return len(value)
    return None


def _enum_value(value: object) -> object:
    if isinstance(value, StrEnum):
        return value.value
    return value


def _summarize_state_field(field_name: str, value: object) -> JsonValue:
    summary: JsonValue
    if field_name in _COUNT_FIELDS:
        summary = {"count": _collection_count(value)}
    elif field_name in _PRESENCE_FIELDS:
        summary = {"present": value is not None and value != ""}
    elif field_name in _BOOLEAN_FIELDS:
        summary = {"value": value if isinstance(value, bool) else None}
    elif field_name in _COUNTER_FIELDS:
        summary = {"value": _safe_nonnegative_integer(value)}
    elif field_name == "retry_counts":
        retry_counts = value if isinstance(value, Mapping) else {}
        summary = {
            "values": {
                key: _safe_nonnegative_integer(retry_counts.get(key)) for key in _SAFE_RETRY_KEYS
            }
        }
    elif field_name == "review_status":
        status = _enum_value(value)
        if isinstance(status, str) and status in _SAFE_REVIEW_STATUSES:
            summary = {"value": status}
        else:
            summary = {"value": "unknown"}
    else:
        summary = {"present": value is not None}
    return summary


def _summarize_mapping(values: Mapping[str, object]) -> dict[str, JsonValue]:
    recognized_fields = sorted(SCHOLARPATH_STATE_FIELDS.intersection(values))
    return {
        "fields": {
            field_name: _summarize_state_field(field_name, values[field_name])
            for field_name in recognized_fields
        },
        "recognized_field_count": len(recognized_fields),
        "unknown_field_count": len(set(values).difference(SCHOLARPATH_STATE_FIELDS)),
    }


def summarize_state(state: Mapping[str, object]) -> dict[str, JsonValue]:
    """Summarize a complete graph state without copying domain values."""
    return _summarize_mapping(state)


def summarize_update(update: Mapping[str, object]) -> dict[str, JsonValue]:
    """Summarize a node update without copying domain values."""
    return _summarize_mapping(update)


def sanitize_error_type(error: BaseException) -> SanitizedErrorType:
    """Classify an exception without exposing its class name, message, or arguments."""
    if isinstance(error, GraphInterrupt):
        return SanitizedErrorType.GRAPH_INTERRUPT
    if isinstance(error, TimeoutError):
        return SanitizedErrorType.TIMEOUT
    if isinstance(error, ConnectionError):
        return SanitizedErrorType.TRANSPORT
    if isinstance(error, PermissionError):
        return SanitizedErrorType.AUTHENTICATION
    return SanitizedErrorType.APPLICATION


def _json_line(event: str, level: int, payload: Mapping[str, JsonValue]) -> str:
    record: dict[str, JsonValue] = {
        "event": event,
        "level": logging.getLevelName(level),
        "schema_version": LOG_SCHEMA_VERSION,
        **payload,
    }
    return json.dumps(
        record,
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def _emit(
    logger: logging.Logger,
    level: int,
    event: str,
    payload: Mapping[str, JsonValue],
) -> None:
    # Logging is observational. A broken local handler must never mutate a
    # workflow outcome, consume a retry, or create a new graph route.
    with suppress(Exception):
        logger.log(level, _json_line(event, level, payload))


def _is_valid_json_value(value: object) -> bool:
    if value is None or isinstance(value, (str, bool, int)):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if isinstance(value, list):
        return all(_is_valid_json_value(item) for item in value)
    if isinstance(value, dict):
        return all(
            isinstance(key, str) and _is_valid_json_value(item) for key, item in value.items()
        )
    return False


def parse_json_log_line(line: str) -> dict[str, JsonValue]:
    """Parse one ScholarPath JSON event using the public log-line convention."""
    try:
        parsed: object = json.loads(line)
    except (json.JSONDecodeError, TypeError) as error:
        raise ValueError("Structured log line must contain valid JSON.") from error
    if not isinstance(parsed, dict) or not _is_valid_json_value(parsed):
        raise ValueError("Structured log line must contain a finite JSON object.")
    if parsed.get("schema_version") != LOG_SCHEMA_VERSION:
        raise ValueError("Structured log line has an unsupported schema version.")
    if not isinstance(parsed.get("event"), str) or not isinstance(parsed.get("level"), str):
        raise ValueError("Structured log line is missing its event envelope.")
    return cast(dict[str, JsonValue], parsed)


def configure_application_logging(
    level: LogLevel,
    *,
    stream: TextIOBase | None = None,
) -> logging.Logger:
    """Configure the ScholarPath logger once with newline-delimited JSON output."""
    logger = logging.getLogger(APPLICATION_LOGGER_NAME)
    logger.setLevel(level.value)
    logger.propagate = False

    existing = next(
        (handler for handler in logger.handlers if handler.get_name() == "scholarpath-json"),
        None,
    )
    if existing is None:
        handler = logging.StreamHandler(stream)
        handler.set_name("scholarpath-json")
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
    else:
        existing.setLevel(logging.NOTSET)
        if stream is not None and isinstance(existing, logging.StreamHandler):
            existing.setStream(stream)
    return logger


def _safe_provider_metadata(
    metadata: Mapping[str, object],
    *,
    outcome: str,
) -> dict[str, JsonValue]:
    safe: dict[str, JsonValue] = {}
    for key in sorted(SAFE_PROVIDER_METADATA_KEYS.intersection(metadata)):
        value = _enum_value(metadata[key])
        if key in {"attempt_number", "duration_ms", "result_count"} or (
            outcome == "succeeded"
            and key in {"overlooked_evidence_count", "unsupported_reference_count"}
        ):
            integer = _safe_nonnegative_integer(value)
            if integer is not None:
                safe[key] = integer
        elif key in {"fallback_used", "retryable"} or (
            key == "structured_result_received" and outcome == "succeeded"
        ):
            if isinstance(value, bool):
                safe[key] = value
        elif key == "failure_category" and outcome in {"failed", "retrying"}:
            failure_category = _allowlisted_string(value, _SAFE_FAILURE_CATEGORIES)
            if failure_category is not None:
                safe[key] = failure_category
        elif key == "decision" and outcome == "succeeded":
            decision = _allowlisted_string(value, _SAFE_REVIEW_DECISIONS)
            if decision is not None:
                safe[key] = decision
        elif key == "confidence" and outcome == "succeeded":
            confidence = _allowlisted_string(value, _SAFE_CONFIDENCE_VALUES)
            if confidence is not None:
                safe[key] = confidence
    return safe


def _allowlisted_string(value: object, allowed_values: frozenset[str]) -> str | None:
    if isinstance(value, str) and value in allowed_values:
        return value
    return None


# The keyword-only envelope keeps each auditable provider dimension explicit.
def emit_provider_event(  # pylint: disable=too-many-arguments
    logger: logging.Logger,
    *,
    provider: str,
    component: str,
    operation: str,
    outcome: str,
    metadata: Mapping[str, object] | None = None,
) -> None:
    """Emit one allowlisted provider lifecycle event without request or response content."""
    payload: dict[str, JsonValue] = {
        "component": component if component in _SAFE_PROVIDER_COMPONENTS else "other",
        "operation": operation if operation in _SAFE_PROVIDER_OPERATIONS else "other",
        "outcome": outcome if outcome in _SAFE_PROVIDER_OUTCOMES else "other",
        "provider": provider if provider in _SAFE_PROVIDERS else "other",
    }
    payload.update(_safe_provider_metadata(metadata or {}, outcome=outcome))
    level = logging.ERROR if outcome == "failed" else logging.INFO
    _emit(logger, level, "provider.lifecycle", payload)


class GraphExecutionLogger:
    """Log node boundaries and routes through privacy-safe aggregate events."""

    def __init__(
        self,
        logger: logging.Logger | None = None,
    ) -> None:
        self._logger = logger or logging.getLogger(f"{APPLICATION_LOGGER_NAME}.graph")

    def _safe_node(self, node_name: object) -> str:
        if isinstance(node_name, str) and node_name in GRAPH_LOG_NODE_NAMES:
            return node_name
        return "unknown"

    def log_node_input(self, node_name: str, state: Mapping[str, object]) -> None:
        """Log the safe aggregate input view for one node invocation."""
        _emit(
            self._logger,
            logging.INFO,
            "graph.node.input",
            {"node": self._safe_node(node_name), "state": summarize_state(state)},
        )

    def log_node_output(self, node_name: str, update: Mapping[str, object]) -> None:
        """Log the safe aggregate output view for one successful node invocation."""
        _emit(
            self._logger,
            logging.INFO,
            "graph.node.output",
            {"node": self._safe_node(node_name), "update": summarize_update(update)},
        )

    def log_node_interrupt(self, node_name: str) -> None:
        """Log a LangGraph interrupt without its Candidate-review payload."""
        _emit(
            self._logger,
            logging.INFO,
            "graph.node.interrupt",
            {
                "error_type": SanitizedErrorType.GRAPH_INTERRUPT.value,
                "node": self._safe_node(node_name),
            },
        )

    def log_node_error(self, node_name: str, error: BaseException) -> None:
        """Log only a closed error category and relegate details to typed state errors."""
        _emit(
            self._logger,
            logging.ERROR,
            "graph.node.error",
            {
                "error_type": sanitize_error_type(error).value,
                "node": self._safe_node(node_name),
            },
        )

    def log_fixed_transition(self, source_node: str, target_node: str) -> None:
        """Log a selected fixed edge after its source node returns successfully."""
        _emit(
            self._logger,
            logging.INFO,
            "graph.transition",
            {
                "kind": "fixed",
                "source": self._safe_node(source_node),
                "target": self._safe_node(target_node),
            },
        )

    def log_conditional_transition(self, source_node: str, target_node: object) -> None:
        """Log a selected conditional edge without stringifying arbitrary route objects."""
        _emit(
            self._logger,
            logging.INFO,
            "graph.transition",
            {
                "kind": "conditional",
                "source": self._safe_node(source_node),
                "target": self._safe_node(target_node),
            },
        )

    def _log_transition_error(self, source_node: str, error: BaseException) -> None:
        _emit(
            self._logger,
            logging.ERROR,
            "graph.transition.error",
            {
                "error_type": sanitize_error_type(error).value,
                "source": self._safe_node(source_node),
            },
        )

    def wrap_node(
        self,
        node_name: str,
        node: Callable[P, R],
        *,
        fixed_target: str | None = None,
        source_from_start: bool = False,
    ) -> Callable[P, R]:
        """Wrap a node with safe input/output, interrupt, error, and fixed-edge events."""

        @wraps(node)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            if source_from_start:
                self.log_fixed_transition("__start__", node_name)
            state_value: object = args[0] if args else kwargs.get("state")
            state = state_value if isinstance(state_value, Mapping) else {}
            self.log_node_input(node_name, state)
            try:
                result = node(*args, **kwargs)
            except GraphInterrupt:
                self.log_node_interrupt(node_name)
                raise
            except Exception as error:
                self.log_node_error(node_name, error)
                raise
            update = result if isinstance(result, Mapping) else {}
            self.log_node_output(node_name, update)
            if fixed_target is not None:
                self.log_fixed_transition(node_name, fixed_target)
            return result

        return wrapped

    def wrap_conditional_route(
        self,
        source_node: str,
        route: Callable[P, R],
    ) -> Callable[P, R]:
        """Wrap a routing function and log only its allowlisted selected target."""

        @wraps(route)
        def wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
            try:
                target = route(*args, **kwargs)
            except Exception as error:
                self._log_transition_error(source_node, error)
                raise
            self.log_conditional_transition(source_node, target)
            return target

        return wrapped


__all__ = [
    "APPLICATION_LOGGER_NAME",
    "GRAPH_LOG_NODE_NAMES",
    "LOG_SCHEMA_VERSION",
    "SAFE_PROVIDER_METADATA_KEYS",
    "SCHOLARPATH_STATE_FIELDS",
    "GraphExecutionLogger",
    "JsonScalar",
    "JsonValue",
    "SanitizedErrorType",
    "configure_application_logging",
    "emit_provider_event",
    "parse_json_log_line",
    "sanitize_error_type",
    "summarize_state",
    "summarize_update",
]
