"""Offline contracts for the OpenAI Research Fit structured-output adapter."""

import json

import pytest
from langchain_core.runnables import RunnableConfig, RunnableLambda
from pydantic import SecretStr

from scholarpath.agents.openai_research_fit import OpenAIResearchFitAdapter
from scholarpath.agents.prompts import RESEARCH_FIT_PROMPT_VERSION
from scholarpath.agents.research_fit import (
    ResearchFitInput,
    ResearchFitModelInvocationError,
    ResearchFitModelOutputError,
    StructuredResearchFitComponent,
    StructuredResearchFitResult,
)
from scholarpath.config import OpenAIResearchFitConfiguration
from scholarpath.domain import EvidenceConfidence, ResearchFitRubric
from tests.fixtures import make_candidate_profile, make_verified_supervisor


def _component(score: int = 0) -> StructuredResearchFitComponent:
    return StructuredResearchFitComponent(
        score=score,
        rationale="No direct component evidence was supplied.",
        supporting_evidence_ids=[],
        confidence=EvidenceConfidence.LOW,
        evidence_gap="Direct evidence is missing for this component.",
    )


def _structured_result() -> StructuredResearchFitResult:
    return StructuredResearchFitResult(
        topic_alignment=_component(),
        methodological_alignment=_component(),
        research_orientation_alignment=_component(),
        recent_research_alignment=_component(),
        practical_constraint_alignment=_component(),
        overall_rationale="The evidence does not establish Research Fit.",
        concerns=["All components require stronger direct evidence."],
    )


def _fit_input() -> ResearchFitInput:
    return ResearchFitInput.from_domain(
        make_candidate_profile(),
        make_verified_supervisor(1),
    )


def _configuration() -> OpenAIResearchFitConfiguration:
    return OpenAIResearchFitConfiguration(
        api_key=SecretStr("not-a-real-openai-research-fit-key"),
        model="synthetic-research-fit-structured-output-model",
        timeout_seconds=8.0,
    )


class ChatOpenAIResearchFitDouble:
    """Minimal ChatOpenAI double recording schema and trace configuration."""

    def __init__(
        self,
        outcome: StructuredResearchFitResult | dict[str, object] | Exception,
    ) -> None:
        self.outcome = outcome
        self.structured_schema: type[StructuredResearchFitResult] | None = None
        self.structured_options: dict[str, object] = {}
        self.runnable_configs: list[RunnableConfig] = []
        self.inputs: list[object] = []

    def with_structured_output(
        self,
        schema: type[StructuredResearchFitResult],
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
    outcome: StructuredResearchFitResult | dict[str, object] | Exception,
) -> tuple[ChatOpenAIResearchFitDouble, dict[str, object]]:
    double = ChatOpenAIResearchFitDouble(outcome)
    constructor_options: dict[str, object] = {}

    def construct(**kwargs: object) -> ChatOpenAIResearchFitDouble:
        constructor_options.update(kwargs)
        return double

    monkeypatch.setattr("scholarpath.agents.openai_research_fit.ChatOpenAI", construct)
    return double, constructor_options


def test_adapter_uses_current_strict_json_schema_without_provider_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = _structured_result()
    chat_model, constructor_options = _patch_chat_openai(monkeypatch, expected)

    result = OpenAIResearchFitAdapter(_configuration()).evaluate(
        _fit_input(),
        ResearchFitRubric(),
    )

    assert result == expected
    assert constructor_options["max_retries"] == 0
    assert constructor_options["model"] == "synthetic-research-fit-structured-output-model"
    assert constructor_options["timeout"] == 8.0
    assert chat_model.structured_schema is StructuredResearchFitResult
    assert chat_model.structured_options == {
        "method": "json_schema",
        "include_raw": False,
        "strict": True,
    }


def test_provider_schema_keeps_all_fields_required_without_numeric_constraints() -> None:
    schema = StructuredResearchFitResult.model_json_schema()
    component_schema = schema["$defs"]["StructuredResearchFitComponent"]

    assert set(component_schema["required"]) == {
        "score",
        "rationale",
        "supporting_evidence_ids",
        "confidence",
        "evidence_gap",
    }
    assert "minimum" not in component_schema["properties"]["score"]
    assert "maximum" not in component_schema["properties"]["score"]
    assert set(schema["required"]) == {
        "topic_alignment",
        "methodological_alignment",
        "research_orientation_alignment",
        "recent_research_alignment",
        "practical_constraint_alignment",
        "overall_rationale",
        "concerns",
    }


def test_adapter_trace_metadata_excludes_candidate_and_secret_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw_secret = "not-a-real-openai-research-fit-key"
    candidate_name = "Ada Synthetic Candidate"
    candidate_email = "ada.synthetic@example.test"
    full_statement = make_candidate_profile().proposed_research_statement
    chat_model, constructor_options = _patch_chat_openai(
        monkeypatch,
        _structured_result(),
    )

    OpenAIResearchFitAdapter(_configuration()).evaluate(_fit_input(), ResearchFitRubric())

    runnable_config = chat_model.runnable_configs[0]
    metadata = runnable_config.get("metadata", {})
    assert metadata == {
        "component": "research_fit_evaluation_agent",
        "prompt_version": RESEARCH_FIT_PROMPT_VERSION,
        "rubric_version": "research-fit-rubric-v1",
    }
    assert set(runnable_config.get("tags", ())) == {
        "component:research-fit-evaluation-agent",
        f"prompt-version:{RESEARCH_FIT_PROMPT_VERSION}",
        "rubric-version:research-fit-rubric-v1",
    }
    serialized_metadata = json.dumps(metadata, default=str)
    serialized_constructor = json.dumps(constructor_options, default=str)
    for sensitive_value in (
        candidate_name,
        candidate_email,
        full_statement,
        raw_secret,
    ):
        assert sensitive_value not in serialized_metadata
        assert sensitive_value not in serialized_constructor


def test_adapter_wraps_invalid_structured_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_chat_openai(monkeypatch, {"unexpected": "shape"})

    with pytest.raises(ResearchFitModelOutputError, match="invalid structured Research Fit"):
        OpenAIResearchFitAdapter(_configuration()).evaluate(
            _fit_input(),
            ResearchFitRubric(),
        )


def test_adapter_classifies_parser_value_errors_as_output_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "invalid output containing a sensitive Candidate statement"
    _patch_chat_openai(monkeypatch, ValueError(sensitive_message))

    with pytest.raises(ResearchFitModelOutputError) as captured:
        OpenAIResearchFitAdapter(_configuration()).evaluate(
            _fit_input(),
            ResearchFitRubric(),
        )

    assert sensitive_message not in str(captured.value)


def test_adapter_sanitizes_model_invocation_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sensitive_message = "provider failure containing Candidate data and secret-key"
    _patch_chat_openai(monkeypatch, RuntimeError(sensitive_message))

    with pytest.raises(ResearchFitModelInvocationError) as captured:
        OpenAIResearchFitAdapter(_configuration()).evaluate(
            _fit_input(),
            ResearchFitRubric(),
        )

    assert sensitive_message not in str(captured.value)
