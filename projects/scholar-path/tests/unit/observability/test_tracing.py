"""Unit tests for optional tracing and privacy-safe trace metadata."""

import json
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from pydantic import SecretStr

from scholarpath.config import Environment, LangSmithSettings
from scholarpath.domain import ResearchFitRubric
from scholarpath.graph import GraphFixtureConfig, build_scholarpath_graph
from scholarpath.observability import (
    GRAPH_VERSION,
    SAFE_TRACE_METADATA_KEYS,
    LangSmithObservability,
    sanitize_trace_metadata,
)
from tests.fakes import FakePlanningModel


def test_trace_metadata_uses_an_allowlist_and_redacts_sensitive_candidate_data() -> None:
    candidate_name = "Ada Synthetic"
    candidate_email = "ada.synthetic@example.test"
    full_statement = "A complete and deliberately sensitive research statement."
    raw_api_key = "langsmith-test-secret"

    metadata = sanitize_trace_metadata(
        {
            "application": "scholarpath",
            "environment": "test",
            "graph_version": GRAPH_VERSION,
            "component": "research_planning_agent",
            "prompt_version": "research-planning-v1",
            "candidate_name": candidate_name,
            "candidate_email": candidate_email,
            "candidate_id": "candidate-sensitive-001",
            "research_statement": full_statement,
            "api_key": raw_api_key,
        }
    )

    assert set(metadata) <= set(SAFE_TRACE_METADATA_KEYS)
    serialized = json.dumps(metadata)
    for sensitive_value in (
        candidate_name,
        candidate_email,
        "candidate-sensitive-001",
        full_statement,
        raw_api_key,
    ):
        assert sensitive_value not in serialized


def test_observability_adds_environment_and_graph_version_without_secrets() -> None:
    raw_api_key = "langsmith-test-secret"
    settings = LangSmithSettings(
        tracing=True,
        api_key=SecretStr(raw_api_key),
        project="scholarpath-tests",
    )
    observability = LangSmithObservability(settings, Environment.TEST)

    assert observability.tags == ["environment:test", f"graph-version:{GRAPH_VERSION}"]
    assert observability.graph_metadata == {
        "application": "scholarpath",
        "environment": "test",
        "graph_version": GRAPH_VERSION,
    }
    assert observability.planning_node_metadata["component"] == "research_planning_agent"
    assert observability.evidence_node_metadata["component"] == "evidence_verification_agent"
    assert observability.evidence_node_metadata["prompt_version"] == "evidence-verification-v1"
    research_fit_metadata = observability.research_fit_node_metadata("research-fit-rubric-v1")
    assert research_fit_metadata == {
        **observability.graph_metadata,
        "component": "research_fit_evaluation_agent",
        "prompt_version": "research-fit-evaluation-v1",
        "rubric_version": "research-fit-rubric-v1",
    }
    independent_review_metadata = observability.independent_review_node_metadata
    assert independent_review_metadata == {
        **observability.graph_metadata,
        "component": "independent_review_agent",
        "prompt_version": "independent-review-v1",
    }
    assert raw_api_key not in json.dumps(observability.planning_node_metadata)
    assert raw_api_key not in json.dumps(observability.evidence_node_metadata)
    assert raw_api_key not in json.dumps(research_fit_metadata)
    assert raw_api_key not in json.dumps(independent_review_metadata)


def test_planning_node_receives_only_the_sanitized_observability_metadata() -> None:
    observability = LangSmithObservability(
        LangSmithSettings(tracing=False),
        Environment.TEST,
    )

    graph = build_scholarpath_graph(
        planning_model=FakePlanningModel(),
        observability=observability,
    ).get_graph()

    assert graph.nodes["plan_supervisor_searches"].metadata == (
        observability.planning_node_metadata
    )
    assert graph.nodes["extract_supervisor_evidence"].metadata == (
        observability.evidence_node_metadata
    )
    assert graph.nodes["evaluate_research_fit"].metadata == (
        observability.research_fit_node_metadata("research-fit-rubric-v1")
    )
    assert graph.nodes["review_fit_assessments"].metadata == (
        observability.independent_review_node_metadata
    )


def test_research_fit_trace_metadata_uses_the_configured_rubric_version() -> None:
    observability = LangSmithObservability(
        LangSmithSettings(tracing=False),
        Environment.TEST,
    )
    config = GraphFixtureConfig(
        research_fit_rubric=ResearchFitRubric(version="research-fit-rubric-experiment")
    )

    graph = build_scholarpath_graph(config, observability=observability).get_graph()
    metadata = graph.nodes["evaluate_research_fit"].metadata

    assert metadata is not None
    assert metadata["rubric_version"] == "research-fit-rubric-experiment"


def test_disabled_tracing_never_constructs_a_langsmith_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_client_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Disabled tracing must not instantiate a LangSmith client")

    monkeypatch.setattr("scholarpath.observability.tracing.Client", fail_if_client_is_constructed)
    observability = LangSmithObservability(
        LangSmithSettings(tracing=False),
        Environment.TEST,
    )

    with observability.activate():
        config = observability.runnable_config(recursion_limit=42)

    assert config.get("recursion_limit") == 42
    assert config.get("run_name") == "scholarpath_graph"


def test_enabled_tracing_hides_input_and_output_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_options: dict[str, object] = {}
    context_options: dict[str, object] = {}

    class ClientDouble:
        def flush(self, timeout: float | None = None) -> None:
            assert timeout == 5.0

        def close(self, timeout: float | None = None) -> None:
            assert timeout == 5.0

    def construct_client(**kwargs: object) -> ClientDouble:
        client_options.update(kwargs)
        return ClientDouble()

    @contextmanager
    def capture_context(**kwargs: object) -> Iterator[None]:
        context_options.update(kwargs)
        yield

    monkeypatch.setattr("scholarpath.observability.tracing.Client", construct_client)
    monkeypatch.setattr("scholarpath.observability.tracing.tracing_context", capture_context)
    observability = LangSmithObservability(
        LangSmithSettings(
            tracing=True,
            api_key=SecretStr("not-a-real-langsmith-secret"),
            project="scholarpath-tests",
        ),
        Environment.TEST,
    )

    with observability.activate():
        pass

    assert client_options["hide_inputs"] is True
    assert client_options["hide_outputs"] is True
    assert client_options["omit_traced_runtime_info"] is True
    assert context_options["enabled"] is True
    assert context_options["metadata"] == observability.graph_metadata
