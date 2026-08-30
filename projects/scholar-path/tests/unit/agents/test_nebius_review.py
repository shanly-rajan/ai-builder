"""Offline contracts for the Nebius independent-review adapter."""

import json
import logging
from io import StringIO
from typing import cast

import pytest
from langchain_core.runnables import RunnableConfig, RunnableLambda
from pydantic import SecretStr

from scholarpath.agents.independent_review import (
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewModelOutputError,
    IndependentReviewResult,
)
from scholarpath.agents.nebius_review import NebiusReviewModelAdapter
from scholarpath.agents.prompts import INDEPENDENT_REVIEW_PROMPT_VERSION
from scholarpath.config import NebiusReviewConfiguration
from scholarpath.domain import EvidenceConfidence, IndependentReviewDecision
from scholarpath.observability import parse_json_log_line
from tests.fixtures import (
    make_candidate_profile,
    make_research_fit_assessment,
    make_verified_supervisor,
)


def _review_input() -> IndependentReviewInput:
    return IndependentReviewInput.from_domain(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )


def _structured_result() -> IndependentReviewResult:
    return IndependentReviewResult(
        decision=IndependentReviewDecision.ACCEPT,
        recommended_score=87,
        unsupported_claim_ids=[],
        overlooked_evidence_ids=[],
        confidence=EvidenceConfidence.HIGH,
        critique="The initial assessment is supported by its cited evidence.",
    )


def _configuration() -> NebiusReviewConfiguration:
    return NebiusReviewConfiguration.model_validate(
        {
            "api_key": SecretStr("not-a-real-nebius-review-key"),
            "model": "synthetic-nebius-review-model",
            "endpoint": "https://review.example.test/v1/",
            "timeout_seconds": 9.0,
        }
    )


class ChatNebiusReviewDouble:
    """Minimal ChatOpenAI double recording schema and trace configuration."""

    def __init__(self, outcome: IndependentReviewResult | dict[str, object] | Exception) -> None:
        self.outcome = outcome
        self.structured_schema: type[IndependentReviewResult] | None = None
        self.structured_options: dict[str, object] = {}
        self.runnable_configs: list[RunnableConfig] = []
        self.inputs: list[object] = []

    def with_structured_output(
        self,
        schema: type[IndependentReviewResult],
        **kwargs: object,
    ) -> RunnableLambda[object, object]:
        self.structured_schema = schema
        self.structured_options = kwargs

        def invoke(value: object, config: RunnableConfig) -> object:
            self.inputs.append(value)
            self.runnable_configs.append(config)
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

        return RunnableLambda(invoke)


def _patch_chat_openai(
    monkeypatch: pytest.MonkeyPatch,
    outcome: IndependentReviewResult | dict[str, object] | Exception,
) -> tuple[ChatNebiusReviewDouble, dict[str, object]]:
    double = ChatNebiusReviewDouble(outcome)
    constructor_options: dict[str, object] = {}

    def construct(**kwargs: object) -> ChatNebiusReviewDouble:
        constructor_options.update(kwargs)
        return double

    monkeypatch.setattr("scholarpath.agents.nebius_review.ChatOpenAI", construct)
    return double, constructor_options


def test_adapter_uses_nebius_endpoint_and_strict_schema_without_provider_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _structured_result()
    chat_model, constructor_options = _patch_chat_openai(monkeypatch, expected)

    result = NebiusReviewModelAdapter(_configuration()).review(_review_input())

    assert result == expected
    assert constructor_options["model"] == "synthetic-nebius-review-model"
    assert constructor_options["base_url"] == "https://review.example.test/v1/"
    assert constructor_options["timeout"] == 9.0
    assert constructor_options["temperature"] == 0.0
    assert constructor_options["max_retries"] == 0
    assert chat_model.structured_schema is IndependentReviewResult
    assert chat_model.structured_options == {
        "method": "json_schema",
        "include_raw": False,
        "strict": True,
    }


def test_actual_nebius_adapter_logs_only_safe_structured_provider_outcome(
    monkeypatch: pytest.MonkeyPatch,
    application_log_stream: StringIO,
) -> None:
    stream = application_log_stream
    expected = _structured_result()
    _patch_chat_openai(monkeypatch, expected)

    result = NebiusReviewModelAdapter(_configuration()).review(_review_input())

    assert result == expected
    events = [
        cast(dict[str, object], parse_json_log_line(line))
        for line in stream.getvalue().splitlines()
    ]
    assert [(event["provider"], event["outcome"]) for event in events] == [
        ("nebius", "started"),
        ("nebius", "succeeded"),
    ]
    assert events[-1] == {
        "component": "independent_review",
        "confidence": "high",
        "decision": "accept",
        "event": "provider.lifecycle",
        "level": "INFO",
        "operation": "invoke",
        "outcome": "succeeded",
        "overlooked_evidence_count": 0,
        "provider": "nebius",
        "schema_version": 1,
        "structured_result_received": True,
        "unsupported_reference_count": 0,
    }
    serialized = stream.getvalue()
    review_input = _review_input()
    for sensitive_value in (
        review_input.candidate_profile.candidate_id,
        review_input.candidate_profile.proposed_research_statement,
        review_input.verified_supervisor.full_name,
        str(review_input.verified_supervisor.profile_url),
        expected.critique,
        "not-a-real-nebius-review-key",
    ):
        assert sensitive_value not in serialized


@pytest.mark.parametrize(
    ("outcome", "expected_category", "expected_error"),
    [
        (
            ValueError("SENSITIVE-MALFORMED-OUTPUT"),
            "invalid_output",
            IndependentReviewModelOutputError,
        ),
        (
            TimeoutError("SENSITIVE-PROVIDER-TIMEOUT"),
            "model_invocation",
            IndependentReviewModelInvocationError,
        ),
    ],
)
def test_actual_nebius_adapter_logs_only_sanitized_failure_category(
    monkeypatch: pytest.MonkeyPatch,
    application_log_stream: StringIO,
    outcome: Exception,
    expected_category: str,
    expected_error: type[Exception],
) -> None:
    stream = application_log_stream
    _patch_chat_openai(monkeypatch, outcome)

    with pytest.raises(expected_error):
        NebiusReviewModelAdapter(_configuration()).review(_review_input())

    events = [
        cast(dict[str, object], parse_json_log_line(line))
        for line in stream.getvalue().splitlines()
    ]
    assert [(event["provider"], event["outcome"]) for event in events] == [
        ("nebius", "started"),
        ("nebius", "failed"),
    ]
    assert events[-1]["failure_category"] == expected_category
    assert str(outcome) not in stream.getvalue()


def test_broken_log_handler_cannot_discard_valid_nebius_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scholarpath.agents import nebius_review

    class BrokenHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            del record
            raise RuntimeError("private logging sink failure")

    logger = logging.getLogger("scholarpath-test-broken-nebius-handler")
    logger.handlers.clear()
    logger.addHandler(BrokenHandler())
    logger.setLevel(logging.INFO)
    logger.propagate = False
    expected = _structured_result()
    _patch_chat_openai(monkeypatch, expected)
    monkeypatch.setattr(nebius_review, "_LOGGER", logger)

    result = NebiusReviewModelAdapter(_configuration()).review(_review_input())

    assert result == expected


def test_provider_schema_requires_every_review_field() -> None:
    schema = IndependentReviewResult.model_json_schema()

    assert set(schema["required"]) == {
        "decision",
        "recommended_score",
        "unsupported_claim_ids",
        "overlooked_evidence_ids",
        "confidence",
        "critique",
    }


def test_adapter_trace_metadata_excludes_candidate_and_secret_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_secret = "not-a-real-nebius-review-key"
    candidate = make_candidate_profile()
    chat_model, constructor_options = _patch_chat_openai(
        monkeypatch,
        _structured_result(),
    )

    NebiusReviewModelAdapter(_configuration()).review(_review_input())

    runnable_config = chat_model.runnable_configs[0]
    metadata = runnable_config.get("metadata", {})
    assert metadata == {
        "component": "independent_review_agent",
        "provider": "nebius",
        "prompt_version": INDEPENDENT_REVIEW_PROMPT_VERSION,
    }
    assert set(runnable_config.get("tags", ())) == {
        "component:independent-review-agent",
        "provider:nebius",
        f"prompt-version:{INDEPENDENT_REVIEW_PROMPT_VERSION}",
    }
    serialized_metadata = json.dumps(metadata, default=str)
    serialized_constructor = json.dumps(constructor_options, default=str)
    for sensitive_value in (
        candidate.candidate_id,
        candidate.proposed_research_statement,
        raw_secret,
    ):
        assert sensitive_value not in serialized_metadata
        assert sensitive_value not in serialized_constructor


def test_adapter_wraps_malformed_structured_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_chat_openai(monkeypatch, {"unexpected": "shape"})

    with pytest.raises(IndependentReviewModelOutputError, match="invalid structured"):
        NebiusReviewModelAdapter(_configuration()).review(_review_input())


def test_adapter_classifies_parser_value_errors_as_output_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "invalid output containing Candidate research and a secret"
    _patch_chat_openai(monkeypatch, ValueError(sensitive_message))

    with pytest.raises(IndependentReviewModelOutputError) as captured:
        NebiusReviewModelAdapter(_configuration()).review(_review_input())

    assert sensitive_message not in str(captured.value)


def test_adapter_maps_timeout_to_sanitized_invocation_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "timeout containing Candidate content and provider key"
    _patch_chat_openai(monkeypatch, TimeoutError(sensitive_message))

    with pytest.raises(IndependentReviewModelInvocationError) as captured:
        NebiusReviewModelAdapter(_configuration()).review(_review_input())

    assert sensitive_message not in str(captured.value)
