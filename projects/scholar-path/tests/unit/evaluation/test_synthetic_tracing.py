"""Synthetic traces retain counts while discarding inputs, prose, credentials, and errors."""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast

import pytest
from langsmith import Client
from langsmith.utils import LangSmithRetry
from pydantic import HttpUrl, SecretStr

from scholarpath.config import Environment, LangSmithSettings
from scholarpath.evaluation.scenarios import EVALUATION_SCENARIOS
from scholarpath.evaluation.synthetic_tracing import (
    SYNTHETIC_EVALUATION_TRACE_TAG,
    WITHHELD_ERROR,
    SyntheticEvaluationObservability,
    create_synthetic_trace_client,
    safe_synthetic_payload,
)
from scholarpath.observability import LangSmithObservability, summarize_state, summarize_update

PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"


def _state() -> dict[str, object]:
    return {
        "candidate_profile": {"candidate_id": PRIVATE, "proposed_research_statement": PRIVATE},
        "candidate_preferences": [{"research_topics": [PRIVATE]}],
        "prospective_supervisors": [{"full_name": PRIVATE, "source_url": PRIVATE}],
        "verification_records": [{"supporting_excerpt": PRIVATE}],
        "review_status": "proposed",
        "retry_counts": {"evidence": 1, PRIVATE: PRIVATE},
        "execution_log": ["extract_supervisor_evidence", PRIVATE],
        "tool_errors": [{"message": PRIVATE}],
        "unknown_private_field": PRIVATE,
    }


def _projection() -> dict[str, object]:
    return {
        "target": "graph_fake",
        "scenario_id": PRIVATE,
        "candidate_preferences": {"research_topics": [PRIVATE]},
        "prospective_supervisor_ids": [PRIVATE, PRIVATE],
        "verification_records": [{"full_name": PRIVATE}],
        "assessments": [{"rationale": PRIVATE}],
        "independent_reviews": [{"critique": PRIVATE}],
        "proposed_supervisor_ids": [PRIVATE],
        "shortlisted_supervisor_ids": [],
        "rejected_supervisor_ids": [PRIVATE],
        "search_attempts": [{"query": PRIVATE}],
        "execution_log": ["load_candidate_preferences", PRIVATE, "candidate_review_gate"],
        "fallback_search_used": True,
        "interrupted": True,
        "review_status": "proposed",
    }


def test_raw_graph_state_and_updates_use_existing_safe_summaries() -> None:
    state = _state()
    update = {"verified_supervisors": [PRIVATE], "shortlist_briefing": PRIVATE}
    assert safe_synthetic_payload(state) == summarize_state(state)
    assert safe_synthetic_payload({"state": state}) == {"state": summarize_state(state)}
    assert safe_synthetic_payload({"update": update}) == {"update": summarize_update(update)}
    assert PRIVATE not in json.dumps(safe_synthetic_payload(state))


@pytest.mark.parametrize("wrapper", ["input", "inputs", "output", "outputs"])
def test_sdk_wrappers_keep_only_safe_graph_summaries(wrapper: str) -> None:
    source = {wrapper: _state(), "unrecognized": PRIVATE}
    sanitized = safe_synthetic_payload(source)
    assert sanitized == {wrapper: summarize_state(_state())}
    assert PRIVATE not in json.dumps(sanitized)


def test_graph_projection_retains_only_counts_and_closed_route_values() -> None:
    sanitized = safe_synthetic_payload(_projection())
    assert sanitized == {
        "target": "graph_fake",
        "counts": {
            "prospective_supervisors": 2,
            "verification_records": 1,
            "assessments": 1,
            "independent_reviews": 1,
            "proposed_supervisors": 1,
            "shortlisted_supervisors": 0,
            "rejected_supervisors": 1,
            "search_attempts": 1,
        },
        "execution_log": ["load_candidate_preferences", "candidate_review_gate"],
        "fallback_search_used": True,
        "interrupted": True,
        "review_status": "proposed",
    }
    assert PRIVATE not in json.dumps(sanitized)


def test_projection_rejects_fake_boolean_status_and_count_text() -> None:
    source = _projection()
    source.update(
        {
            "review_status": PRIVATE,
            "fallback_search_used": PRIVATE,
            "interrupted": 1,
            "prospective_supervisor_ids": PRIVATE,
        }
    )
    sanitized = safe_synthetic_payload(source)
    assert "review_status" not in sanitized
    assert "fallback_search_used" not in sanitized
    assert "interrupted" not in sanitized
    assert PRIVATE not in json.dumps(sanitized)


def test_root_scenario_uses_catalog_identity_and_ignores_all_incoming_free_text() -> None:
    scenario = EVALUATION_SCENARIOS[0]
    source = {
        "scenario": {
            "scenario_id": scenario.scenario_id,
            "target": PRIVATE,
            "candidate_preferences": PRIVATE,
            "tags": [PRIVATE],
            "config": {"secret": PRIVATE},
        }
    }
    assert safe_synthetic_payload(source) == {
        "evaluation_scenario_id": scenario.scenario_id,
        "evaluation_target": scenario.target.value,
        "synthetic_data": True,
    }
    assert safe_synthetic_payload({"scenario": {"scenario_id": PRIVATE}}) == {}


def test_metadata_allows_only_typed_closed_values_even_under_known_keys() -> None:
    source = {
        "application": "scholarpath",
        "environment": Environment.TEST.value,
        "evaluation_scenario_id": EVALUATION_SCENARIOS[0].scenario_id,
        "model_provider": "fake",
        "candidate_review_outcome": "reject",
        "fallback_search_used": True,
        "attempt_number": 2,
        "graph_version": PRIVATE,
        "prompt_version": PRIVATE,
        "provider": PRIVATE,
        "component": PRIVATE,
        "raw_result_count": True,
        "plausible_supervisor_count": -1,
        "candidate_id": PRIVATE,
        "api_key": PRIVATE,
        "evaluation_target": PRIVATE,
        "langgraph_step": float("nan"),
    }
    expected = {
        "application": "scholarpath",
        "environment": "test",
        "evaluation_scenario_id": EVALUATION_SCENARIOS[0].scenario_id,
        "model_provider": "fake",
        "candidate_review_outcome": "reject",
        "fallback_search_used": True,
        "attempt_number": 2,
    }
    assert safe_synthetic_payload(source) == expected
    assert safe_synthetic_payload({"metadata": source}) == {"metadata": expected}
    assert PRIVATE not in json.dumps(safe_synthetic_payload(source))


@pytest.mark.parametrize(
    "source",
    [
        None,
        PRIVATE,
        [PRIVATE],
        {PRIVATE: PRIVATE},
        {"scenario": PRIVATE},
        {"metadata": {"secret": PRIVATE}},
    ],
)
def test_unrecognized_payload_shapes_fail_closed(source: object) -> None:
    assert safe_synthetic_payload(source) == {}


@pytest.mark.parametrize(
    "error", [PRIVATE, RuntimeError(PRIVATE), {"Authorization": PRIVATE}, None]
)
def test_error_scrubber_always_returns_the_sdk_error_key(error: object) -> None:
    assert safe_synthetic_payload({"error": error, "more": PRIVATE}) == {"error": WITHHELD_ERROR}


@pytest.mark.parametrize(
    "source",
    [_state(), {"state": _state()}, _projection(), {"metadata": {"application": "scholarpath"}}],
)
def test_sanitization_never_mutates_or_aliases_original_nested_mappings(
    source: dict[str, object],
) -> None:
    before = deepcopy(source)
    sanitized = safe_synthetic_payload(source)
    assert source == before
    assert sanitized is not source
    sanitized["mutated"] = True
    for value in sanitized.values():
        if isinstance(value, dict):
            value["changed"] = True
        elif isinstance(value, list):
            value.append("changed")
    assert source == before


def test_nested_unknown_wrappers_are_bounded() -> None:
    source: dict[str, object] = {"private": PRIVATE}
    for _ in range(50):
        source = {"inputs": source}
    assert safe_synthetic_payload(source) == {}


def test_synthetic_observability_inherits_parent_context_without_closing_the_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SimpleNamespace(close=lambda **_: pytest.fail("Inherited client must not be closed"))
    parent = SimpleNamespace(
        tags=[SYNTHETIC_EVALUATION_TRACE_TAG],
        client=client,
        session_name="approved-synthetic-project",
    )
    captured: dict[str, object] = {}

    @contextmanager
    def capture_context(**kwargs: object) -> Iterator[None]:
        captured.update(kwargs)
        yield

    monkeypatch.setattr(
        "scholarpath.evaluation.synthetic_tracing.get_current_run_tree", lambda: parent
    )
    monkeypatch.setattr("scholarpath.evaluation.synthetic_tracing.tracing_context", capture_context)
    monkeypatch.setattr(
        "scholarpath.evaluation.synthetic_tracing.Client",
        lambda **_: pytest.fail("Do not construct another client"),
    )
    observability = SyntheticEvaluationObservability()
    assert isinstance(observability, LangSmithObservability)
    with observability.activate():
        pass
    assert captured["enabled"] is True
    assert captured["parent"] is parent
    assert captured["client"] is client
    assert captured["project_name"] == parent.session_name
    assert captured["metadata"] == observability.graph_metadata
    assert "environment:test" in observability.tags


@pytest.mark.parametrize(
    "parent",
    [None, SimpleNamespace(tags=[]), SimpleNamespace(tags=None), SimpleNamespace(tags=[PRIVATE])],
)
def test_synthetic_context_without_allowlisted_parent_fails_before_execution(
    parent: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scholarpath.evaluation.synthetic_tracing.get_current_run_tree", lambda: parent
    )
    monkeypatch.setattr(
        "scholarpath.evaluation.synthetic_tracing.tracing_context",
        lambda **_: pytest.fail("Do not activate tracing"),
    )
    with (
        pytest.raises(RuntimeError, match="allowlisted synthetic evaluation parent"),
        SyntheticEvaluationObservability().activate(),
    ):
        pytest.fail("Unapproved synthetic execution must not start")


def test_synthetic_client_uses_one_payload_anonymizer_and_shared_bounded_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}
    client = object()

    def factory(**kwargs: object) -> object:
        captured.update(kwargs)
        return client

    monkeypatch.setattr("scholarpath.evaluation.synthetic_tracing.Client", factory)
    settings = LangSmithSettings(
        tracing=False,
        api_key=SecretStr("fake-secret"),
        endpoint=HttpUrl("https://eu.api.smith.langchain.com"),
        workspace_id="fake-workspace",
        request_timeout_seconds=7.5,
        maximum_retry_count=1,
    )
    assert create_synthetic_trace_client(settings) is client
    assert captured["anonymizer"] is safe_synthetic_payload
    assert captured["hide_inputs"] is False
    assert captured["hide_outputs"] is False
    assert captured["hide_metadata"] is False
    assert captured["omit_traced_runtime_info"] is True
    assert captured["api_url"] == str(settings.endpoint)
    assert captured["workspace_id"] == "fake-workspace"
    assert captured["timeout_ms"] == 7500
    assert isinstance(captured["retry_config"], LangSmithRetry)
    assert captured["retry_config"].total == 1
    assert captured["retry_config"].redirect == 0


def test_installed_sdk_applies_anonymizer_to_inputs_outputs_metadata_and_errors() -> None:
    # This client never sends a request. Exercise the pinned SDK's local filter boundary.
    client = Client(
        api_key="fake-secret",
        api_url="https://api.smith.langchain.com",
        auto_batch_tracing=False,
        anonymizer=safe_synthetic_payload,
        hide_inputs=False,
        hide_outputs=False,
        hide_metadata=False,
        omit_traced_runtime_info=True,
    )
    try:
        payloads: tuple[tuple[str, dict[str, object]], ...] = (
            ("_hide_run_inputs", _state()),
            ("_hide_run_outputs", _projection()),
            ("_hide_run_metadata", {"application": "scholarpath", "provider": PRIVATE}),
        )
        for method, payload in payloads:
            filter_payload = cast(
                Callable[[dict[str, object]], dict[str, object]], getattr(client, method)
            )
            original = deepcopy(payload)
            filtered = filter_payload(payload)
            assert filtered
            assert PRIVATE not in json.dumps(filtered)
            assert payload == original
        filter_error = cast(Callable[[str], str], client._hide_run_error)
        assert filter_error(PRIVATE) == WITHHELD_ERROR
    finally:
        client.close()
