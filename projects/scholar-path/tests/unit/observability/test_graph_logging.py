"""Unit tests for privacy-safe graph and provider JSON logging."""

import json
import logging
from collections.abc import Iterator
from io import StringIO

import pytest
from langgraph.errors import GraphInterrupt
from langgraph.types import Interrupt

from scholarpath.config import LogLevel
from scholarpath.graph.state import ScholarPathState
from scholarpath.observability import (
    LOG_SCHEMA_VERSION,
    SCHOLARPATH_STATE_FIELDS,
    GraphExecutionLogger,
    JsonValue,
    SanitizedErrorType,
    configure_application_logging,
    emit_provider_event,
    parse_json_log_line,
    sanitize_error_type,
    summarize_state,
    summarize_update,
)


@pytest.fixture
def structured_log_stream() -> Iterator[tuple[logging.Logger, StringIO]]:
    """Provide an isolated ScholarPath logger and restore global logging state."""
    logger = logging.getLogger("scholarpath")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    logger.handlers.clear()
    stream = StringIO()
    try:
        yield configure_application_logging(LogLevel.DEBUG, stream=stream), stream
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def _events(stream: StringIO) -> list[dict[str, JsonValue]]:
    return [parse_json_log_line(line) for line in stream.getvalue().splitlines()]


def _sensitive_state() -> tuple[dict[str, object], tuple[str, ...]]:
    secrets = (
        "candidate-private-734",
        "A private full research statement about restricted systems.",
        "private-topic",
        "private-preference-reason",
        "site:private.example private query",
        "Dr Private Person",
        "Private University",
        "https://private.example/profile",
        "private-evidence-claim",
        "private-page-content",
        "private-fit-rationale",
        "private-shortlist-briefing",
        "sk-private-provider-secret",
        "thread-private-832",
        "private exception response body",
    )
    state: dict[str, object] = {
        "candidate_profile": {
            "candidate_id": secrets[0],
            "proposed_research_statement": secrets[1],
            "research_topics": [secrets[2]],
        },
        "candidate_preferences": [{"reason": secrets[3]}],
        "candidate_memory_records": [{"content": secrets[3]}],
        "candidate_memory_processed_feedback_count": 1,
        "candidate_memory_available": True,
        "search_plan": {"search_queries": [secrets[4]]},
        "raw_search_results": [{"url": secrets[7], "title": secrets[5]}],
        "prospective_supervisors": [{"full_name": secrets[5]}],
        "verified_supervisors": [{"institution": secrets[6]}],
        "verification_records": [{"claim": secrets[8]}],
        "evidence_extraction_attempts": [{"content": secrets[9]}],
        "alternate_source_attempts": [{"url": secrets[7]}],
        "alternate_evidence_sources": {secrets[5]: secrets[7]},
        "research_fit_assessments": [{"rationale": secrets[10]}],
        "research_fit_review_records": [{"critique": secrets[10]}],
        "proposed_shortlist": {"briefing": secrets[11]},
        "shortlisted_supervisors": [{"full_name": secrets[5]}],
        "rejected_supervisors": [{"full_name": secrets[5]}],
        "candidate_feedback": [{"reason": secrets[3]}],
        "candidate_review_error": secrets[13],
        "tool_errors": [{"message": secrets[14]}],
        "search_attempts": [{"query": secrets[4]}],
        "fallback_search_used": True,
        "fallback_search_round": 2,
        "discovery_round": 3,
        "retry_counts": {
            "discovery": 1,
            "evidence": 2,
            "review": 0,
            "review_input": 1,
            secrets[12]: 999,
        },
        "review_status": "proposed",
        "execution_log": ["plan_supervisor_searches"],
        "supervisor_shortlist": {"briefing": secrets[11]},
        "shortlist_briefing": secrets[11],
        secrets[13]: secrets[12],
    }
    return state, secrets


def test_state_field_allowlist_covers_the_complete_typed_graph_state() -> None:
    assert ScholarPathState.__required_keys__ == SCHOLARPATH_STATE_FIELDS


def test_state_summary_contains_only_counts_statuses_and_presence() -> None:
    state, secrets = _sensitive_state()

    summary = summarize_state(state)

    assert summary["recognized_field_count"] == len(SCHOLARPATH_STATE_FIELDS)
    assert summary["unknown_field_count"] == 1
    fields = summary["fields"]
    assert isinstance(fields, dict)
    assert fields["prospective_supervisors"] == {"count": 1}
    assert fields["verified_supervisors"] == {"count": 1}
    assert fields["candidate_profile"] == {"present": True}
    assert fields["candidate_review_error"] == {"present": True}
    assert fields["shortlist_briefing"] == {"present": True}
    assert fields["review_status"] == {"value": "proposed"}
    assert fields["retry_counts"] == {
        "values": {"discovery": 1, "evidence": 2, "review": 0, "review_input": 1}
    }
    serialized = json.dumps(summary, sort_keys=True)
    assert all(secret not in serialized for secret in secrets)


def test_update_summary_omits_unknown_values_and_invalid_control_values() -> None:
    private_value = "private Candidate review response"

    summary = summarize_update(
        {
            "review_status": private_value,
            "fallback_search_round": private_value,
            "fallback_search_used": private_value,
            "verified_supervisors": [{"private": private_value}],
            "unrecognized_private_field": private_value,
        }
    )

    assert summary == {
        "fields": {
            "fallback_search_round": {"value": None},
            "fallback_search_used": {"value": None},
            "review_status": {"value": "unknown"},
            "verified_supervisors": {"count": 1},
        },
        "recognized_field_count": 4,
        "unknown_field_count": 1,
    }
    assert private_value not in json.dumps(summary)


def test_configure_application_logging_is_idempotent_and_uses_log_level(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream

    configured_again = configure_application_logging(LogLevel.ERROR, stream=stream)

    assert configured_again is logger
    assert logger.level == logging.ERROR
    assert len([handler for handler in logger.handlers if handler.name == "scholarpath-json"]) == 1
    assert logger.propagate is False


def test_broken_log_handler_cannot_change_node_result_or_route() -> None:
    class BrokenHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            del record
            raise RuntimeError("private logging sink failure")

    logger = logging.getLogger("scholarpath-test-broken-handler")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    logger.handlers.clear()
    logger.addHandler(BrokenHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    execution_logger = GraphExecutionLogger(logger)

    def node(state: dict[str, object]) -> dict[str, object]:
        del state
        return {"fallback_search_used": True}

    def route(state: dict[str, object]) -> str:
        del state
        return "fallback_supervisor_search"

    try:
        wrapped_node = execution_logger.wrap_node(
            "enough_supervisors_found",
            node,
            fixed_target="fallback_supervisor_search",
        )
        wrapped_route = execution_logger.wrap_conditional_route(
            "enough_supervisors_found",
            route,
        )

        assert wrapped_node({}) == {"fallback_search_used": True}
        assert wrapped_route({}) == "fallback_supervisor_search"
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
        logger.setLevel(original_level)
        logger.propagate = original_propagate


def test_provider_event_reports_nebius_structured_result_without_payload(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream

    emit_provider_event(
        logger,
        provider="nebius",
        component="independent_review",
        operation="invoke",
        outcome="succeeded",
        metadata={
            "decision": "revise",
            "confidence": "medium",
            "unsupported_reference_count": 2,
            "overlooked_evidence_count": 1,
            "structured_result_received": True,
            "failure_category": "invalid_output",
            "private_critique": "do not log this critique",
            "raw_result": {"secret": "do not log this result"},
        },
    )

    [event] = _events(stream)
    assert event == {
        "component": "independent_review",
        "confidence": "medium",
        "decision": "revise",
        "event": "provider.lifecycle",
        "level": "INFO",
        "operation": "invoke",
        "outcome": "succeeded",
        "overlooked_evidence_count": 1,
        "provider": "nebius",
        "schema_version": LOG_SCHEMA_VERSION,
        "structured_result_received": True,
        "unsupported_reference_count": 2,
    }
    serialized = stream.getvalue()
    assert "failure_category" not in event
    assert "critique" not in serialized
    assert "do not log" not in serialized


def test_provider_event_replaces_unknown_labels_and_omits_invalid_metadata(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream
    private_api_key = "sk-private-provider-secret"

    emit_provider_event(
        logger,
        provider=private_api_key,
        component="private component",
        operation="private operation",
        outcome="failed",
        metadata={
            "decision": private_api_key,
            "confidence": private_api_key,
            "failure_category": private_api_key,
            "result_count": -1,
            "structured_result_received": "true",
            "api_key": private_api_key,
        },
    )

    [event] = _events(stream)
    assert event == {
        "component": "other",
        "event": "provider.lifecycle",
        "level": "ERROR",
        "operation": "other",
        "outcome": "failed",
        "provider": "other",
        "schema_version": LOG_SCHEMA_VERSION,
    }
    assert private_api_key not in stream.getvalue()


def test_failed_provider_event_omits_success_only_metadata(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream

    emit_provider_event(
        logger,
        provider="nebius",
        component="independent_review",
        operation="invoke",
        outcome="failed",
        metadata={
            "decision": "accept",
            "confidence": "high",
            "failure_category": "model_invocation",
            "overlooked_evidence_count": 2,
            "structured_result_received": True,
            "unsupported_reference_count": 1,
        },
    )

    [event] = _events(stream)
    assert event == {
        "component": "independent_review",
        "event": "provider.lifecycle",
        "failure_category": "model_invocation",
        "level": "ERROR",
        "operation": "invoke",
        "outcome": "failed",
        "provider": "nebius",
        "schema_version": LOG_SCHEMA_VERSION,
    }


def test_node_wrapper_logs_start_input_output_and_successful_fixed_transition(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream
    execution_logger = GraphExecutionLogger(logger)
    state, secrets = _sensitive_state()

    def load_preferences(node_state: dict[str, object]) -> dict[str, object]:
        assert node_state is state
        return {"candidate_preferences": [{"reason": secrets[3]}]}

    wrapped = execution_logger.wrap_node(
        "load_candidate_preferences",
        load_preferences,
        fixed_target="plan_supervisor_searches",
        source_from_start=True,
    )

    assert wrapped(state) == {"candidate_preferences": [{"reason": secrets[3]}]}
    events = _events(stream)
    assert [event["event"] for event in events] == [
        "graph.transition",
        "graph.node.input",
        "graph.node.output",
        "graph.transition",
    ]
    assert events[0] | {"level": "INFO", "schema_version": LOG_SCHEMA_VERSION} == events[0]
    assert events[0]["source"] == "__start__"
    assert events[0]["target"] == "load_candidate_preferences"
    assert events[-1]["source"] == "load_candidate_preferences"
    assert events[-1]["target"] == "plan_supervisor_searches"
    serialized = stream.getvalue()
    assert all(secret not in serialized for secret in secrets)


def test_node_wrapper_logs_graph_interrupt_without_payload_and_re_raises(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream
    execution_logger = GraphExecutionLogger(logger)
    private_payload = "private Candidate review payload"
    private_thread_id = "thread-private-832"

    def interrupting_node(state: dict[str, object]) -> dict[str, object]:
        del state
        raise GraphInterrupt((Interrupt(value=private_payload, id=private_thread_id),))

    wrapped = execution_logger.wrap_node("candidate_review_gate", interrupting_node)

    with pytest.raises(GraphInterrupt):
        wrapped({"review_status": "proposed"})
    events = _events(stream)
    assert [event["event"] for event in events] == [
        "graph.node.input",
        "graph.node.interrupt",
    ]
    assert events[-1]["error_type"] == "graph_interrupt"
    assert private_payload not in stream.getvalue()
    assert private_thread_id not in stream.getvalue()


def test_node_wrapper_logs_sanitized_error_and_skips_fixed_transition(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream
    execution_logger = GraphExecutionLogger(logger)
    private_message = "provider response contained a secret"

    def failing_node(state: dict[str, object]) -> dict[str, object]:
        del state
        raise RuntimeError(private_message)

    wrapped = execution_logger.wrap_node(
        "review_fit_assessments",
        failing_node,
        fixed_target="synthesize_supervisor_shortlist",
    )

    with pytest.raises(RuntimeError, match="provider response"):
        wrapped({"review_status": "proposed"})
    events = _events(stream)
    assert [event["event"] for event in events] == ["graph.node.input", "graph.node.error"]
    assert events[-1]["error_type"] == "application"
    assert private_message not in stream.getvalue()


def test_conditional_route_wrapper_logs_selected_edge_and_sanitized_failure(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream
    execution_logger = GraphExecutionLogger(logger)

    def successful_route(state: dict[str, object]) -> str:
        del state
        return "fallback_supervisor_search"

    wrapped_success = execution_logger.wrap_conditional_route(
        "enough_supervisors_found", successful_route
    )
    assert wrapped_success({}) == "fallback_supervisor_search"

    private_error = "private route failure context"

    def failing_route(state: dict[str, object]) -> str:
        del state
        raise TimeoutError(private_error)

    wrapped_failure = execution_logger.wrap_conditional_route(
        "supervisor_evidence_sufficient", failing_route
    )
    with pytest.raises(TimeoutError, match="private route"):
        wrapped_failure({})

    events = _events(stream)
    assert events[0]["event"] == "graph.transition"
    assert events[0]["kind"] == "conditional"
    assert events[0]["source"] == "enough_supervisors_found"
    assert events[0]["target"] == "fallback_supervisor_search"
    assert events[1] == {
        "error_type": "timeout",
        "event": "graph.transition.error",
        "level": "ERROR",
        "schema_version": LOG_SCHEMA_VERSION,
        "source": "supervisor_evidence_sufficient",
    }
    assert private_error not in stream.getvalue()


def test_unknown_transition_target_is_not_stringified(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream
    execution_logger = GraphExecutionLogger(logger)
    private_target = "candidate-private-734"

    execution_logger.log_conditional_transition("plan_supervisor_searches", private_target)

    [event] = _events(stream)
    assert event["target"] == "unknown"
    assert private_target not in stream.getvalue()


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (TimeoutError("private"), SanitizedErrorType.TIMEOUT),
        (ConnectionError("private"), SanitizedErrorType.TRANSPORT),
        (PermissionError("private"), SanitizedErrorType.AUTHENTICATION),
        (ValueError("private"), SanitizedErrorType.APPLICATION),
    ],
)
def test_error_sanitization_uses_closed_categories(
    error: BaseException,
    expected: SanitizedErrorType,
) -> None:
    assert sanitize_error_type(error) is expected


@pytest.mark.parametrize(
    "line",
    [
        "not-json",
        "[]",
        '{"event":"x","level":"INFO","schema_version":2}',
        '{"event":"x","schema_version":1}',
        '{"event":"x","level":"INFO","schema_version":1,"value":NaN}',
    ],
)
def test_json_log_parser_rejects_invalid_envelopes_without_echoing_input(line: str) -> None:
    with pytest.raises(ValueError) as exc_info:
        parse_json_log_line(line)

    assert line not in str(exc_info.value)


def test_json_serialization_has_deterministic_sorted_keys(
    structured_log_stream: tuple[logging.Logger, StringIO],
) -> None:
    logger, stream = structured_log_stream

    emit_provider_event(
        logger,
        provider="nebius",
        component="independent_review",
        operation="invoke",
        outcome="started",
        metadata={"attempt_number": 1},
    )

    line = stream.getvalue().strip()
    assert line == json.dumps(
        parse_json_log_line(line),
        allow_nan=False,
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )
