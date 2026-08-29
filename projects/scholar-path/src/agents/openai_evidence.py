"""OpenAI structured-output adapter for Supervisor evidence extraction."""

from typing import cast

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from pydantic import ValidationError

from ..config import OpenAIEvidenceConfiguration
from .evidence_verification import (
    EvidenceExtractionInput,
    EvidenceModelInvocationError,
    EvidenceModelOutputError,
    StructuredEvidenceExtractionResult,
)
from .prompts import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V3,
)


class OpenAIEvidenceVerificationModelAdapter:
    """Extract evidence using native JSON-schema output without prose parsing."""

    def __init__(self, configuration: OpenAIEvidenceConfiguration) -> None:
        chat_model = ChatOpenAI(
            api_key=configuration.api_key,
            model=configuration.model,
            timeout=configuration.timeout_seconds,
            max_retries=0,
        )
        structured_model = chat_model.with_structured_output(
            StructuredEvidenceExtractionResult,
            method="json_schema",
            include_raw=False,
            strict=True,
        )
        prompt = ChatPromptTemplate.from_messages(
            (
                ("system", EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V3),
                ("human", "Retrieved Supervisor page input:\n{extraction_input}"),
            )
        )
        self._chain = cast(
            Runnable[dict[str, str], StructuredEvidenceExtractionResult],
            prompt | structured_model,
        )

    def extract(
        self, extraction_input: EvidenceExtractionInput
    ) -> StructuredEvidenceExtractionResult:
        """Invoke OpenAI once and return a validated structured evidence response."""
        runnable_config: RunnableConfig = {
            "run_name": "openai_supervisor_evidence_structured_output",
            "tags": [
                "component:evidence-verification-agent",
                f"prompt-version:{EVIDENCE_VERIFICATION_PROMPT_VERSION}",
            ],
            "metadata": {
                "component": "evidence_verification_agent",
                "prompt_version": EVIDENCE_VERIFICATION_PROMPT_VERSION,
            },
        }
        try:
            result = self._chain.invoke(
                {"extraction_input": extraction_input.model_dump_json()},
                config=runnable_config,
            )
        except (OutputParserException, ValidationError, ValueError) as error:
            raise EvidenceModelOutputError(
                "OpenAI returned invalid structured evidence output."
            ) from error
        except Exception as error:
            raise EvidenceModelInvocationError("The OpenAI evidence request failed.") from error

        try:
            return StructuredEvidenceExtractionResult.model_validate(result)
        except ValidationError as error:
            raise EvidenceModelOutputError(
                "OpenAI returned invalid structured evidence output."
            ) from error
