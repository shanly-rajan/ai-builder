"""OpenAI strict structured-output adapter for Research Fit evaluation."""

import json
from typing import cast

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from ..config import OpenAIResearchFitConfiguration
from ..domain import ResearchFitRubric
from .prompts import RESEARCH_FIT_PROMPT_VERSION, RESEARCH_FIT_SYSTEM_PROMPT_V1
from .research_fit import (
    ResearchFitInput,
    ResearchFitModelInvocationError,
    ResearchFitModelOutputError,
    StructuredResearchFitResult,
)


class OpenAIResearchFitAdapter:
    """Evaluate Research Fit using OpenAI's native strict JSON-schema output."""

    def __init__(self, configuration: OpenAIResearchFitConfiguration) -> None:
        chat_model = ChatOpenAI(
            api_key=configuration.api_key,
            model=configuration.model,
            timeout=configuration.timeout_seconds,
            max_retries=0,
        )
        structured_model = chat_model.with_structured_output(
            StructuredResearchFitResult,
            method="json_schema",
            include_raw=False,
            strict=True,
        )
        prompt = ChatPromptTemplate.from_messages(
            (
                ("system", RESEARCH_FIT_SYSTEM_PROMPT_V1),
                (
                    "human",
                    "Research Fit input and configured rubric:\n{evaluation_context}",
                ),
            )
        )
        self._chain = cast(
            Runnable[dict[str, str], StructuredResearchFitResult],
            prompt | structured_model,
        )

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        """Invoke OpenAI once and return a validated structured component proposal."""
        runnable_config: RunnableConfig = {
            "run_name": "openai_research_fit_structured_output",
            "tags": [
                "component:research-fit-evaluation-agent",
                f"prompt-version:{RESEARCH_FIT_PROMPT_VERSION}",
                f"rubric-version:{rubric.version}",
            ],
            "metadata": {
                "component": "research_fit_evaluation_agent",
                "prompt_version": RESEARCH_FIT_PROMPT_VERSION,
                "rubric_version": rubric.version,
            },
        }
        evaluation_context = json.dumps(
            {
                "fit_input": fit_input.model_dump(mode="json"),
                "rubric": rubric.model_dump(mode="json"),
            },
            separators=(",", ":"),
        )
        try:
            result = self._chain.invoke(
                {"evaluation_context": evaluation_context},
                config=runnable_config,
            )
        except (OutputParserException, ValidationError, ValueError) as error:
            raise ResearchFitModelOutputError(
                "OpenAI returned invalid structured Research Fit output."
            ) from error
        except Exception as error:
            raise ResearchFitModelInvocationError(
                "The OpenAI Research Fit request failed."
            ) from error

        try:
            return StructuredResearchFitResult.model_validate(result)
        except ValidationError as error:
            raise ResearchFitModelOutputError(
                "OpenAI returned invalid structured Research Fit output."
            ) from error
