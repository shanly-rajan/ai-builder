"""Typed, narrowly scoped LLM-as-judge evaluators for qualitative M12 metrics."""

from __future__ import annotations

import json
from enum import StrEnum
from typing import Annotated, Final, Protocol, cast

from langchain_core.exceptions import OutputParserException
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_openai import ChatOpenAI
from langsmith.evaluation import EvaluationResult
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
)

from .models import (
    CandidatePreferenceProjection,
    EvaluationTargetOutput,
    GraphTargetOutput,
    ResearchFitTargetOutput,
    SearchPlanningTargetOutput,
    parse_evaluation_target_output,
)

JUDGE_PROMPT_VERSION: Final = "scholarpath-evaluation-judge-v1"

JUDGE_SYSTEM_PROMPT_V1: Final = """
You are a narrowly scoped ScholarPath evaluation judge. Evaluate only the qualitative
criterion named in the input, using the supplied synthetic Candidate preference
projection and bounded ScholarPath artifact. Do not browse, call tools, add facts, infer
Supervisor availability, estimate admission probability, recalculate scores, validate
URLs, or audit graph routing. Deterministic evaluators handle those facts.

Use this scale: 0 = unusable, 1 = weak, 2 = adequate, 3 = strong, 4 = excellent.
Return one score and a concise explanation of no more than 80 words. For evidence
grounding, assess whether the explanation connects to the supplied claim summaries and
evidence IDs; do not independently decide whether a source is true. For shortlist
usefulness, assess whether the proposal makes strengths, concerns, confidence, and
limitations useful to the Candidate without making an approval decision.
""".strip()

NonEmptyJudgeString = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=600),
]


class JudgeCriterion(StrEnum):
    """Qualitative questions that are inappropriate for deterministic arithmetic."""

    RESEARCH_FIT_RELEVANCE = "research_fit_relevance"
    EXPLANATION_USEFULNESS = "explanation_usefulness"
    EVIDENCE_GROUNDED_RATIONALE = "evidence_grounded_rationale"
    SHORTLIST_USEFULNESS = "shortlist_usefulness"


class JudgeInput(BaseModel):
    """Privacy-safe input supplied to an evaluation judge."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    criterion: JudgeCriterion
    candidate_preferences: CandidatePreferenceProjection
    artifact: dict[str, JsonValue]
    rubric_version: NonEmptyJudgeString = JUDGE_PROMPT_VERSION


class StructuredJudgeResult(BaseModel):
    """Strict structured qualitative score returned by the judge model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    score: Annotated[int, Field(strict=True, ge=0, le=4)]
    rationale: NonEmptyJudgeString

    @field_validator("rationale")
    @classmethod
    def rationale_must_be_concise(cls, value: str) -> str:
        """Keep qualitative feedback readable and bounded in trace feedback."""
        if len(value.split()) > 80:
            raise ValueError("Evaluation judge rationale must not exceed 80 words")
        return value


class EvaluationJudgePort(Protocol):
    """Provider-neutral judge boundary implemented by OpenAI and offline fakes."""

    def judge(self, judge_input: JudgeInput) -> StructuredJudgeResult:
        """Return one typed qualitative assessment."""
        ...


class EvaluationJudgeConfiguration(BaseModel):
    """Credential boundary instantiated only for an explicitly enabled live judge."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: SecretStr
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(gt=0)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject an empty credential only when the live judge is instantiated."""
        if not value.get_secret_value().strip():
            raise ValueError("OpenAI evaluation judge API key must not be blank")
        return value


class EvaluationJudgeModelError(RuntimeError):
    """Base sanitized error raised at the qualitative judge boundary."""


class EvaluationJudgeInvocationError(EvaluationJudgeModelError):
    """The provider failed before returning structured judge output."""


class EvaluationJudgeOutputError(EvaluationJudgeModelError):
    """The provider response violated the structured judge schema."""


class OpenAIEvaluationJudgeAdapter:
    """OpenAI adapter using native strict structured output for one judge criterion."""

    def __init__(self, configuration: EvaluationJudgeConfiguration) -> None:
        chat_model = ChatOpenAI(
            api_key=configuration.api_key,
            model=configuration.model,
            timeout=configuration.timeout_seconds,
            max_retries=0,
        )
        structured_model = chat_model.with_structured_output(
            StructuredJudgeResult,
            method="json_schema",
            include_raw=False,
            strict=True,
        )
        prompt = ChatPromptTemplate.from_messages(
            (
                ("system", JUDGE_SYSTEM_PROMPT_V1),
                ("human", "Evaluation input:\n{judge_context}"),
            )
        )
        self._chain = cast(
            Runnable[dict[str, str], StructuredJudgeResult],
            prompt | structured_model,
        )

    def judge(self, judge_input: JudgeInput) -> StructuredJudgeResult:
        """Invoke OpenAI once and validate its qualitative structured result."""
        runnable_config: RunnableConfig = {
            "run_name": "openai_scholarpath_evaluation_judge",
            "tags": [
                "component:evaluation-judge",
                "provider:openai",
                f"prompt-version:{JUDGE_PROMPT_VERSION}",
                f"judge-criterion:{judge_input.criterion.value}",
            ],
            "metadata": {
                "component": "evaluation_judge",
                "provider": "openai",
                "prompt_version": JUDGE_PROMPT_VERSION,
                "judge_criterion": judge_input.criterion.value,
            },
        }
        try:
            result = self._chain.invoke(
                {
                    "judge_context": json.dumps(
                        judge_input.model_dump(mode="json"),
                        separators=(",", ":"),
                    )
                },
                config=runnable_config,
            )
        except (OutputParserException, ValidationError, ValueError) as error:
            raise EvaluationJudgeOutputError(
                "OpenAI returned invalid structured evaluation-judge output."
            ) from error
        except Exception as error:
            raise EvaluationJudgeInvocationError(
                "The OpenAI evaluation-judge request failed."
            ) from error

        try:
            return StructuredJudgeResult.model_validate(result)
        except ValidationError as error:
            raise EvaluationJudgeOutputError(
                "OpenAI returned invalid structured evaluation-judge output."
            ) from error


def _candidate_preferences(
    inputs: dict[str, object],
    output: EvaluationTargetOutput,
) -> CandidatePreferenceProjection | None:
    """Resolve only the bounded preference projection, never a full Candidate profile."""
    if isinstance(output, ResearchFitTargetOutput | GraphTargetOutput):
        return output.candidate_preferences
    raw: object = inputs.get("candidate_preferences")
    if raw is None:
        scenario = inputs.get("scenario")
        if isinstance(scenario, dict):
            raw = scenario.get("candidate_preferences")
    if raw is None:
        return None
    try:
        return CandidatePreferenceProjection.model_validate(raw)
    except (ValidationError, TypeError, ValueError):
        return None


def _artifact_for_criterion(
    criterion: JudgeCriterion,
    output: EvaluationTargetOutput,
) -> dict[str, JsonValue] | None:
    """Project only fields relevant to one qualitative question."""
    if criterion is JudgeCriterion.SHORTLIST_USEFULNESS:
        if not isinstance(output, GraphTargetOutput) or not output.shortlist_recommendations:
            return None
        return {
            "recommendations": [
                item.model_dump(mode="json") for item in output.shortlist_recommendations
            ]
        }
    if criterion is JudgeCriterion.EXPLANATION_USEFULNESS and isinstance(
        output, SearchPlanningTargetOutput
    ):
        return {"search_plan": output.search_plan.model_dump(mode="json")}
    if not isinstance(output, ResearchFitTargetOutput | GraphTargetOutput):
        return None
    if not output.assessments:
        return None
    return {
        "assessments": [item.model_dump(mode="json") for item in output.assessments],
        "independent_reviews": (
            [item.model_dump(mode="json") for item in output.independent_reviews]
            if isinstance(output, GraphTargetOutput)
            else []
        ),
    }


class JudgeEvaluator:
    """LangSmith-compatible callable backed by an injected typed judge port."""

    def __init__(self, criterion: JudgeCriterion, judge: EvaluationJudgePort) -> None:
        self._criterion = criterion
        self._judge = judge

    def __call__(
        self,
        inputs: dict[str, object],
        outputs: dict[str, object],
        reference_outputs: dict[str, object] | None = None,
    ) -> EvaluationResult:
        """Judge one applicable output, returning unavailable rather than crashing."""
        del reference_outputs
        try:
            output = parse_evaluation_target_output(outputs)
        except (ValidationError, TypeError, ValueError):
            return EvaluationResult(
                key=f"llm_{self._criterion.value}",
                score=None,
                value="invalid_output",
                comment="The target output did not satisfy the typed evaluation contract.",
            )
        preferences = _candidate_preferences(inputs, output)
        artifact = _artifact_for_criterion(self._criterion, output)
        if preferences is None or artifact is None:
            return EvaluationResult(
                key=f"llm_{self._criterion.value}",
                score=None,
                value="not_applicable",
            )
        try:
            result = self._judge.judge(
                JudgeInput(
                    criterion=self._criterion,
                    candidate_preferences=preferences,
                    artifact=artifact,
                )
            )
        except Exception:
            return EvaluationResult(
                key=f"llm_{self._criterion.value}",
                score=None,
                value="judge_unavailable",
                comment="The qualitative evaluation judge was unavailable.",
            )
        return EvaluationResult(
            key=f"llm_{self._criterion.value}",
            score=result.score / 4,
            value=result.score,
            comment=result.rationale,
            metadata={
                "criterion": self._criterion.value,
                "rubric_version": JUDGE_PROMPT_VERSION,
                "scale_maximum": 4,
            },
        )


def research_fit_relevance_judge(judge: EvaluationJudgePort) -> JudgeEvaluator:
    """Build the scoped Research Fit relevance evaluator."""
    return JudgeEvaluator(JudgeCriterion.RESEARCH_FIT_RELEVANCE, judge)


def explanation_usefulness_judge(judge: EvaluationJudgePort) -> JudgeEvaluator:
    """Build the scoped explanation-usefulness evaluator."""
    return JudgeEvaluator(JudgeCriterion.EXPLANATION_USEFULNESS, judge)


def evidence_grounded_rationale_judge(judge: EvaluationJudgePort) -> JudgeEvaluator:
    """Build the scoped evidence-grounding evaluator."""
    return JudgeEvaluator(JudgeCriterion.EVIDENCE_GROUNDED_RATIONALE, judge)


def shortlist_usefulness_judge(judge: EvaluationJudgePort) -> JudgeEvaluator:
    """Build the scoped shortlist-usefulness evaluator."""
    return JudgeEvaluator(JudgeCriterion.SHORTLIST_USEFULNESS, judge)


def make_judge_evaluators(judge: EvaluationJudgePort) -> tuple[JudgeEvaluator, ...]:
    """Return the four stable qualitative evaluators for an explicit live run."""
    return (
        research_fit_relevance_judge(judge),
        explanation_usefulness_judge(judge),
        evidence_grounded_rationale_judge(judge),
        shortlist_usefulness_judge(judge),
    )
