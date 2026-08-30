"""Nebius strict structured-output adapter for independent Research Fit review."""

import logging
from typing import cast

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from ..config import NebiusReviewConfiguration
from ..observability import emit_provider_event
from .independent_review import (
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewModelOutputError,
    IndependentReviewResult,
)
from .prompts import (
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    INDEPENDENT_REVIEW_SYSTEM_PROMPT_V4,
)

_LOGGER = logging.getLogger("scholarpath.providers.nebius")


class NebiusReviewModelAdapter:
    """Review Research Fit through Nebius's OpenAI-compatible inference API."""

    def __init__(self, configuration: NebiusReviewConfiguration) -> None:
        chat_model = ChatOpenAI(
            api_key=configuration.api_key,
            model=configuration.model,
            base_url=str(configuration.endpoint),
            timeout=configuration.timeout_seconds,
            temperature=0.0,
            max_retries=0,
        )
        structured_model = chat_model.with_structured_output(
            IndependentReviewResult,
            method="json_schema",
            include_raw=False,
            strict=True,
        )
        prompt = ChatPromptTemplate.from_messages(
            (
                ("system", INDEPENDENT_REVIEW_SYSTEM_PROMPT_V4),
                ("human", "Independent Research Fit review input:\n{review_input}"),
            )
        )
        self._chain = cast(
            Runnable[dict[str, str], IndependentReviewResult],
            prompt | structured_model,
        )

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        """Invoke Nebius once and return a validated structured review."""
        runnable_config: RunnableConfig = {
            "run_name": "nebius_independent_review_structured_output",
            "tags": [
                "component:independent-review-agent",
                "provider:nebius",
                f"prompt-version:{INDEPENDENT_REVIEW_PROMPT_VERSION}",
            ],
            "metadata": {
                "component": "independent_review_agent",
                "provider": "nebius",
                "prompt_version": INDEPENDENT_REVIEW_PROMPT_VERSION,
            },
        }
        emit_provider_event(
            _LOGGER,
            provider="nebius",
            component="independent_review",
            operation="invoke",
            outcome="started",
        )
        try:
            result = self._chain.invoke(
                {"review_input": review_input.model_dump_json()},
                config=runnable_config,
            )
        except (OutputParserException, ValidationError, ValueError) as error:
            emit_provider_event(
                _LOGGER,
                provider="nebius",
                component="independent_review",
                operation="invoke",
                outcome="failed",
                metadata={"failure_category": "invalid_output"},
            )
            raise IndependentReviewModelOutputError(
                "Nebius returned invalid structured independent-review output."
            ) from error
        except Exception as error:
            emit_provider_event(
                _LOGGER,
                provider="nebius",
                component="independent_review",
                operation="invoke",
                outcome="failed",
                metadata={"failure_category": "model_invocation"},
            )
            raise IndependentReviewModelInvocationError(
                "The Nebius independent-review request failed."
            ) from error

        try:
            validated_result = IndependentReviewResult.model_validate(result)
        except ValidationError as error:
            emit_provider_event(
                _LOGGER,
                provider="nebius",
                component="independent_review",
                operation="invoke",
                outcome="failed",
                metadata={"failure_category": "invalid_output"},
            )
            raise IndependentReviewModelOutputError(
                "Nebius returned invalid structured independent-review output."
            ) from error
        emit_provider_event(
            _LOGGER,
            provider="nebius",
            component="independent_review",
            operation="invoke",
            outcome="succeeded",
            metadata={
                "decision": validated_result.decision,
                "confidence": validated_result.confidence,
                "unsupported_reference_count": len(validated_result.unsupported_claim_ids),
                "overlooked_evidence_count": len(validated_result.overlooked_evidence_ids),
                "structured_result_received": True,
            },
        )
        return validated_result
