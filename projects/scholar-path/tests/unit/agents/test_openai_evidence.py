"""Offline contract tests for the OpenAI evidence structured-output adapter."""

import json

import pytest
from langchain_core.runnables import RunnableConfig, RunnableLambda
from pydantic import HttpUrl, SecretStr

from scholarpath.agents.evidence_verification import (
    EvidenceExtractionInput,
    EvidenceModelInvocationError,
    EvidenceModelOutputError,
    StructuredEvidenceExtractionResult,
)
from scholarpath.agents.openai_evidence import OpenAIEvidenceVerificationModelAdapter
from scholarpath.agents.prompts import EVIDENCE_VERIFICATION_PROMPT_VERSION
from scholarpath.config import OpenAIEvidenceConfiguration
from scholarpath.domain import SourceKind
from tests.fakes import make_complete_evidence_response
from tests.fixtures import COMPLETE_PROFILE_URL, read_evidence_page


def _extraction_input() -> EvidenceExtractionInput:
    return EvidenceExtractionInput(
        expected_name="Dr Amara Ndlovu",
        expected_institution="Southern Cape Institute of Technology",
        expected_department="Department of Information Systems",
        source_url=HttpUrl(COMPLETE_PROFILE_URL),
        source_kind=SourceKind.UNIVERSITY_PROFILE,
        page_content=read_evidence_page("complete_official_profile.md"),
    )


def _configuration() -> OpenAIEvidenceConfiguration:
    return OpenAIEvidenceConfiguration(
        api_key=SecretStr("not-a-real-openai-evidence-key"),
        model="synthetic-evidence-structured-output-model",
        timeout_seconds=7.5,
    )


class ChatOpenAIEvidenceDouble:
    """Minimal ChatOpenAI double that records schema options and runnable config."""

    def __init__(
        self,
        outcome: StructuredEvidenceExtractionResult | dict[str, object] | Exception,
    ) -> None:
        self.outcome = outcome
        self.structured_schema: type[StructuredEvidenceExtractionResult] | None = None
        self.structured_options: dict[str, object] = {}
        self.runnable_configs: list[RunnableConfig] = []

    def with_structured_output(
        self,
        schema: type[StructuredEvidenceExtractionResult],
        **kwargs: object,
    ) -> RunnableLambda[object, object]:
        self.structured_schema = schema
        self.structured_options = kwargs

        def invoke(_input: object, config: RunnableConfig) -> object:
            self.runnable_configs.append(config)
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

        return RunnableLambda(invoke)


def _patch_chat_openai(
    monkeypatch: pytest.MonkeyPatch,
    outcome: StructuredEvidenceExtractionResult | dict[str, object] | Exception,
) -> tuple[ChatOpenAIEvidenceDouble, dict[str, object]]:
    double = ChatOpenAIEvidenceDouble(outcome)
    constructor_options: dict[str, object] = {}

    def construct(**kwargs: object) -> ChatOpenAIEvidenceDouble:
        constructor_options.update(kwargs)
        return double

    monkeypatch.setattr("scholarpath.agents.openai_evidence.ChatOpenAI", construct)
    return double, constructor_options


def test_adapter_uses_native_strict_json_schema_without_provider_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = make_complete_evidence_response()
    chat_model, constructor_options = _patch_chat_openai(monkeypatch, expected)

    result = OpenAIEvidenceVerificationModelAdapter(_configuration()).extract(_extraction_input())

    assert result == expected
    assert constructor_options["max_retries"] == 0
    assert constructor_options["model"] == "synthetic-evidence-structured-output-model"
    assert constructor_options["timeout"] == 7.5
    assert chat_model.structured_schema is StructuredEvidenceExtractionResult
    assert chat_model.structured_options == {
        "method": "json_schema",
        "include_raw": False,
        "strict": True,
    }


def test_adapter_trace_metadata_excludes_page_candidate_and_secret_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_secret = "not-a-real-openai-evidence-key"
    candidate_name = "Ada Synthetic Candidate"
    candidate_email = "ada.synthetic@example.test"
    extraction_input = _extraction_input()
    chat_model, constructor_options = _patch_chat_openai(
        monkeypatch, make_complete_evidence_response()
    )

    OpenAIEvidenceVerificationModelAdapter(_configuration()).extract(extraction_input)

    assert EVIDENCE_VERIFICATION_PROMPT_VERSION == "evidence-verification-v4"
    assert len(chat_model.runnable_configs) == 1
    runnable_config = chat_model.runnable_configs[0]
    metadata = runnable_config.get("metadata", {})
    assert metadata == {
        "component": "evidence_verification_agent",
        "prompt_version": EVIDENCE_VERIFICATION_PROMPT_VERSION,
    }
    assert set(runnable_config.get("tags", ())) == {
        "component:evidence-verification-agent",
        f"prompt-version:{EVIDENCE_VERIFICATION_PROMPT_VERSION}",
    }
    serialized_metadata = json.dumps(metadata, default=str)
    serialized_constructor = json.dumps(constructor_options, default=str)
    for sensitive_value in (
        extraction_input.page_content,
        candidate_name,
        candidate_email,
        raw_secret,
    ):
        assert sensitive_value not in serialized_metadata
        assert sensitive_value not in serialized_constructor


def test_adapter_wraps_invalid_structured_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_chat_openai(monkeypatch, {"unexpected": "shape"})
    adapter = OpenAIEvidenceVerificationModelAdapter(_configuration())

    with pytest.raises(EvidenceModelOutputError, match="invalid structured evidence output"):
        adapter.extract(_extraction_input())


def test_adapter_classifies_structured_parser_value_errors_as_output_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "invalid parsed evidence containing retrieved full page content"
    _patch_chat_openai(monkeypatch, ValueError(sensitive_message))
    adapter = OpenAIEvidenceVerificationModelAdapter(_configuration())

    with pytest.raises(EvidenceModelOutputError) as captured:
        adapter.extract(_extraction_input())

    assert sensitive_message not in str(captured.value)


def test_adapter_sanitizes_model_invocation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "provider failure containing Candidate data and secret-key"
    _patch_chat_openai(monkeypatch, RuntimeError(sensitive_message))
    adapter = OpenAIEvidenceVerificationModelAdapter(_configuration())

    with pytest.raises(EvidenceModelInvocationError) as captured:
        adapter.extract(_extraction_input())

    assert sensitive_message not in str(captured.value)
