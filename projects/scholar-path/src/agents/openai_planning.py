"""OpenAI adapter for the ScholarPath Research Planning Agent."""

from typing import cast

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from ..config import OpenAIPlanningConfiguration
from .prompts import RESEARCH_PLANNING_PROMPT_VERSION, RESEARCH_PLANNING_SYSTEM_PROMPT_V1
from .research_planning import (
    PlanningInput,
    PlanningModelInvocationError,
    PlanningModelOutputError,
    StructuredSearchPlanResponse,
)


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
                ("system", RESEARCH_PLANNING_SYSTEM_PROMPT_V1),
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
        try:
            result = self._chain.invoke(
                {"planning_input": planning_input.model_dump_json()},
                config=runnable_config,
            )
        except (OutputParserException, ValidationError, ValueError) as error:
            raise PlanningModelOutputError("OpenAI returned invalid structured output.") from error
        except Exception as error:
            raise PlanningModelInvocationError("The OpenAI planning request failed.") from error

        try:
            return StructuredSearchPlanResponse.model_validate(result)
        except ValidationError as error:
            raise PlanningModelOutputError("OpenAI returned invalid structured output.") from error
