"""Unit tests for optional tracing and privacy-safe trace metadata."""

import json
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from pydantic import HttpUrl, SecretStr

from scholarpath.config import Environment, LangSmithSettings
from scholarpath.domain import ResearchFitRubric, SearchResultRejectionCounts
from scholarpath.graph import GraphFixtureConfig, build_scholarpath_graph
from scholarpath.observability import (
    GRAPH_VERSION,
    SAFE_TRACE_METADATA_KEYS,
    LangSmithObservability,
    sanitize_trace_metadata,
)
from scholarpath.tools import SearchProvider
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
            "prompt_version": "research-planning-v2",
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

    assert observability.tags == [
        "application:scholarpath",
        "environment:test",
        f"graph-version:{GRAPH_VERSION}",
    ]
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
        "prompt_version": "independent-review-v3",
    }
    assert raw_api_key not in json.dumps(observability.planning_node_metadata)
    assert raw_api_key not in json.dumps(observability.evidence_node_metadata)
    assert raw_api_key not in json.dumps(research_fit_metadata)
    assert raw_api_key not in json.dumps(independent_review_metadata)


def test_discovery_metadata_contains_only_safe_aggregate_routing_facts() -> None:
    observability = LangSmithObservability(
        LangSmithSettings(tracing=False),
        Environment.TEST,
    )
    private_query = 'site:private.example "sensitive Candidate research"'
    rejection_counts = SearchResultRejectionCounts(
        person_not_established=2,
        academic_context_not_established=1,
        identity_conflict=1,
        institution_not_established=2,
        incomplete_institution=1,
    )
    metadata = sanitize_trace_metadata(
        {
            **observability.discovery_attempt_metadata(
                provider=SearchProvider.YOU,
                attempt_number=2,
                raw_result_count=10,
                plausible_supervisor_count=3,
                error_category=None,
                fallback_search_used=False,
                rejection_counts=rejection_counts,
            ),
            "query": private_query,
            "candidate_id": "candidate-private-001",
            "raw_results": [{"url": "https://private.example/profile"}],
            "supervisor_name": "Private Person",
            "api_key": "private-provider-secret",
        }
    )

    assert metadata == {
        **observability.graph_metadata,
        "component": "supervisor_discovery_agent",
        "provider": "you.com",
        "attempt_number": 2,
        "raw_result_count": 10,
        "plausible_supervisor_count": 3,
        "rejected_person_not_established_count": 2,
        "rejected_academic_context_not_established_count": 1,
        "rejected_identity_conflict_count": 1,
        "rejected_institution_not_established_count": 2,
        "rejected_incomplete_institution_count": 1,
        "error_category": "none",
        "fallback_search_used": False,
        "discovery_route": "primary",
    }
    serialized = json.dumps(metadata)
    assert private_query not in serialized
    assert "candidate-private-001" not in serialized
    assert "private.example" not in serialized
    assert "Private Person" not in serialized
    assert "private-provider-secret" not in serialized


def test_discovery_attempt_span_uses_empty_payloads_and_safe_final_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    class RunDouble:
        def end(
            self,
            *,
            outputs: dict[str, object] | None = None,
            metadata: dict[str, object] | None = None,
        ) -> None:
            captured["outputs"] = outputs
            captured["final_metadata"] = metadata

    @contextmanager
    def capture_trace(name: str, **kwargs: object) -> Iterator[RunDouble]:
        captured["name"] = name
        captured.update(kwargs)
        yield RunDouble()

    monkeypatch.setattr("scholarpath.observability.tracing.trace", capture_trace)
    observability = LangSmithObservability(
        LangSmithSettings(
            tracing=True,
            api_key=SecretStr("unused-test-key"),
            project="scholarpath-tests",
        ),
        Environment.TEST,
    )

    with observability.discovery_attempt_span(
        provider=SearchProvider.YOU,
        attempt_number=1,
        fallback_search_used=False,
    ) as complete:
        complete(
            8,
            2,
            None,
            SearchResultRejectionCounts(
                person_not_established=1,
                academic_context_not_established=1,
                identity_conflict=1,
                institution_not_established=2,
                incomplete_institution=1,
            ),
        )

    assert captured["name"] == "you.com_supervisor_search_attempt"
    assert captured["inputs"] == {}
    assert captured["outputs"] == {}
    assert captured["final_metadata"] == observability.discovery_attempt_metadata(
        provider=SearchProvider.YOU,
        attempt_number=1,
        raw_result_count=8,
        plausible_supervisor_count=2,
        error_category=None,
        fallback_search_used=False,
        rejection_counts=SearchResultRejectionCounts(
            person_not_established=1,
            academic_context_not_established=1,
            identity_conflict=1,
            institution_not_established=2,
            incomplete_institution=1,
        ),
    )


def test_discovery_metadata_uses_zero_rejection_counts_for_failed_or_legacy_attempts() -> None:
    observability = LangSmithObservability(
        LangSmithSettings(tracing=False),
        Environment.TEST,
    )

    metadata = observability.discovery_attempt_metadata(
        provider=SearchProvider.TAVILY,
        attempt_number=1,
        raw_result_count=0,
        plausible_supervisor_count=0,
        error_category=None,
        fallback_search_used=True,
    )

    assert metadata["rejected_person_not_established_count"] == 0
    assert metadata["rejected_academic_context_not_established_count"] == 0
    assert metadata["rejected_identity_conflict_count"] == 0
    assert metadata["rejected_institution_not_established_count"] == 0
    assert metadata["rejected_incomplete_institution_count"] == 0


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
    assert graph.nodes["discover_prospective_supervisors"].metadata == (
        observability.discovery_node_metadata(
            provider=SearchProvider.YOU,
            fallback_search_used=False,
        )
    )
    assert graph.nodes["fallback_supervisor_search"].metadata == (
        observability.discovery_node_metadata(
            provider=SearchProvider.TAVILY,
            fallback_search_used=True,
        )
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
            endpoint=HttpUrl("https://eu.api.smith.langchain.com"),
            project="scholarpath-tests",
            workspace_id="workspace-test-001",
        ),
        Environment.TEST,
    )

    with observability.activate():
        pass

    assert client_options["hide_inputs"] is True
    assert client_options["hide_outputs"] is True
    assert client_options["omit_traced_runtime_info"] is True
    assert client_options["api_url"] == "https://eu.api.smith.langchain.com/"
    assert client_options["workspace_id"] == "workspace-test-001"
    assert context_options["enabled"] is True
    assert context_options["metadata"] == observability.graph_metadata
