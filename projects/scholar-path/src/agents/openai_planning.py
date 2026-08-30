"""OpenAI adapter for the ScholarPath Research Planning Agent."""

import logging
from typing import cast

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from openai import (
    APIConnectionError,
    APITimeoutError,
    AuthenticationError,
    InternalServerError,
    PermissionDeniedError,
    RateLimitError,
)
from pydantic import ValidationError

from ..config import OpenAIPlanningConfiguration
from ..observability import emit_provider_event
from .prompts import RESEARCH_PLANNING_PROMPT_VERSION, RESEARCH_PLANNING_SYSTEM_PROMPT_V4
from .research_planning import (
    PlanningInput,
    PlanningModelInvocationError,
    PlanningModelOutputError,
    StructuredSearchPlanResponse,
)

_LOGGER = logging.getLogger("scholarpath.providers.openai.planning")


def _invocation_failure_policy(error: Exception) -> tuple[bool, str]:
    """Classify retryability without exposing provider messages or request content."""
    if isinstance(error, APITimeoutError | TimeoutError):
        return True, "timeout"
    if isinstance(error, RateLimitError):
        return True, "rate_limit"
    if isinstance(error, APIConnectionError | ConnectionError):
        return True, "transport"
    if isinstance(error, InternalServerError):
        return True, "provider"
    if isinstance(error, AuthenticationError | PermissionDeniedError):
        return False, "authentication"
    return False, "model_invocation"


class OpenAIPlanningModelAdapter:
    """Generate native structured output through ChatOpenAI without tools or browsing."""

    def __init__(self, configuration: OpenAIPlanningConfiguration) -> None:
        chat_model = ChatOpenAI(
            api_key=configuration.api_key,
            model=configuration.model,
            timeout=configuration.timeout_seconds,
            max_retries=0,
        )
        structured_model = chat_model.with_structured_output(
            StructuredSearchPlanResponse,
            method="json_schema",
            include_raw=False,
            strict=True,
        )
        prompt = ChatPromptTemplate.from_messages(
            (
                ("system", RESEARCH_PLANNING_SYSTEM_PROMPT_V4),
                ("human", "Candidate research planning input:\n{planning_input}"),
            )
        )
        self._chain = cast(
            Runnable[dict[str, str], StructuredSearchPlanResponse],
            prompt | structured_model,
        )

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        """Invoke OpenAI once and return a Pydantic response without prose parsing."""
        runnable_config: RunnableConfig = {
            "run_name": "openai_research_planning_structured_output",
            "tags": [
                "component:research-planning-agent",
                f"prompt-version:{RESEARCH_PLANNING_PROMPT_VERSION}",
            ],
            "metadata": {
                "component": "research_planning_agent",
                "prompt_version": RESEARCH_PLANNING_PROMPT_VERSION,
            },
        }
        emit_provider_event(
            _LOGGER,
            provider="openai",
            component="research_planning",
            operation="invoke",
            outcome="started",
        )
        try:
            result = self._chain.invoke(
                {"planning_input": planning_input.model_dump_json()},
                config=runnable_config,
            )
        except (OutputParserException, ValidationError, ValueError) as error:
            emit_provider_event(
                _LOGGER,
                provider="openai",
                component="research_planning",
                operation="invoke",
                outcome="failed",
                metadata={"failure_category": "invalid_output", "retryable": True},
            )
            raise PlanningModelOutputError("OpenAI returned invalid structured output.") from error
        except Exception as error:
            retryable, failure_category = _invocation_failure_policy(error)
            emit_provider_event(
                _LOGGER,
                provider="openai",
                component="research_planning",
                operation="invoke",
                outcome="failed",
                metadata={
                    "failure_category": failure_category,
                    "retryable": retryable,
                },
            )
            raise PlanningModelInvocationError(
                "The OpenAI planning request failed.",
                retryable=retryable,
            ) from error

        try:
            validated_result = StructuredSearchPlanResponse.model_validate(result)
        except ValidationError as error:
            emit_provider_event(
                _LOGGER,
                provider="openai",
                component="research_planning",
                operation="invoke",
                outcome="failed",
                metadata={"failure_category": "invalid_output", "retryable": True},
            )
            raise PlanningModelOutputError("OpenAI returned invalid structured output.") from error
        emit_provider_event(
            _LOGGER,
            provider="openai",
            component="research_planning",
            operation="invoke",
            outcome="succeeded",
            metadata={"structured_result_received": True},
        )
        return validated_result
