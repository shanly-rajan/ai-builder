"""Offline contract tests for the OpenAI structured-output adapter."""

import pytest
from langchain_core.runnables import RunnableLambda
from pydantic import SecretStr

from scholarpath.agents import (
    OpenAIPlanningModelAdapter,
    PlanningInput,
    PlanningModelInvocationError,
    PlanningModelOutputError,
    StructuredSearchPlanResponse,
)
from scholarpath.config import OpenAIPlanningConfiguration
from tests.fakes import make_valid_planning_response
from tests.fixtures import make_candidate_profile


def _planning_input() -> PlanningInput:
    profile = make_candidate_profile()
    return PlanningInput.from_candidate_profile(
        profile,
        (),
        target_regions=profile.preferred_regions,
        exclusions=profile.exclusions,
    )


def _configuration() -> OpenAIPlanningConfiguration:
    return OpenAIPlanningConfiguration(
        api_key=SecretStr("not-a-real-openai-key"),
        model="synthetic-structured-output-model",
        timeout_seconds=5.0,
    )


class ChatOpenAIDouble:
    """Minimal ChatOpenAI double returning a LangChain runnable."""

    def __init__(
        self,
        outcome: StructuredSearchPlanResponse | dict[str, object] | Exception,
    ) -> None:
        self.outcome = outcome
        self.structured_schema: type[StructuredSearchPlanResponse] | None = None
        self.structured_options: dict[str, object] = {}

    def with_structured_output(
        self,
        schema: type[StructuredSearchPlanResponse],
        **kwargs: object,
    ) -> RunnableLambda[object, object]:
        self.structured_schema = schema
        self.structured_options = kwargs

        def invoke(_input: object) -> object:
            if isinstance(self.outcome, Exception):
                raise self.outcome
            return self.outcome

        return RunnableLambda(invoke)


def _patch_chat_openai(
    monkeypatch: pytest.MonkeyPatch,
    outcome: StructuredSearchPlanResponse | dict[str, object] | Exception,
) -> tuple[ChatOpenAIDouble, dict[str, object]]:
    double = ChatOpenAIDouble(outcome)
    constructor_options: dict[str, object] = {}

    def construct(**kwargs: object) -> ChatOpenAIDouble:
        constructor_options.update(kwargs)
        return double

    monkeypatch.setattr("scholarpath.agents.openai_planning.ChatOpenAI", construct)
    return double, constructor_options


def test_adapter_uses_native_strict_json_schema_without_provider_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = make_valid_planning_response()
    chat_model, constructor_options = _patch_chat_openai(monkeypatch, expected)

    adapter = OpenAIPlanningModelAdapter(_configuration())
    result = adapter.generate(_planning_input())

    assert result == expected
    assert constructor_options["max_retries"] == 0
    assert constructor_options["model"] == "synthetic-structured-output-model"
    assert chat_model.structured_schema is StructuredSearchPlanResponse
    assert chat_model.structured_options == {
        "method": "json_schema",
        "include_raw": False,
        "strict": True,
    }


def test_adapter_wraps_invalid_structured_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_chat_openai(monkeypatch, {"unexpected": "shape"})
    adapter = OpenAIPlanningModelAdapter(_configuration())

    with pytest.raises(PlanningModelOutputError, match="invalid structured output"):
        adapter.generate(_planning_input())


def test_adapter_classifies_plain_structured_parser_value_errors_as_output_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_chat_openai(
        monkeypatch,
        ValueError("Structured output response does not have a parsed field"),
    )
    adapter = OpenAIPlanningModelAdapter(_configuration())

    with pytest.raises(PlanningModelOutputError, match="invalid structured output"):
        adapter.generate(_planning_input())


def test_adapter_sanitizes_model_invocation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "provider failure containing a sensitive Candidate statement"
    _patch_chat_openai(monkeypatch, RuntimeError(sensitive_message))
    adapter = OpenAIPlanningModelAdapter(_configuration())

    with pytest.raises(PlanningModelInvocationError) as captured:
        adapter.generate(_planning_input())

    assert sensitive_message not in str(captured.value)
