"""Offline regression execution and explicitly gated LangSmith experiments."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Annotated, Final
from uuid import UUID, uuid5

from langsmith import Client
from langsmith.evaluation import EvaluationResult
from langsmith.schemas import Example, ExampleCreate
from pydantic import BaseModel, ConfigDict, Field

from ..agents import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    RESEARCH_PLANNING_PROMPT_VERSION,
)
from ..config import (
    Environment,
    EvaluationSettings,
    LangSmithSettings,
    OpenAIPlanningSettings,
    ProviderConfigurationError,
)
from ..observability import GRAPH_VERSION
from .evaluators import DETERMINISTIC_EVALUATORS
from .judges import (
    EvaluationJudgeConfiguration,
    JudgeEvaluator,
    OpenAIEvaluationJudgeAdapter,
    make_judge_evaluators,
)
from .models import EvaluationScenario, EvaluationTargetKind
from .scenarios import (
    EVALUATION_DATASET_NAME,
    EVALUATION_SCENARIO_VERSION,
    EVALUATION_SCENARIOS,
    evaluation_dataset_inputs,
    evaluation_dataset_reference_outputs,
)
from .targets import (
    EvaluationTarget,
    evidence_verification_target,
    fake_end_to_end_target,
    live_end_to_end_target,
    research_fit_target,
    search_planning_target,
)
from .tracing import EVALUATION_APPLICATION, sanitize_evaluation_trace_metadata

LOCAL_BASELINE_NAME: Final = "scholarpath-m12-1-fake-baseline-2026-08-29"
_EVALUATION_EXAMPLE_NAMESPACE: Final = UUID("1c83477e-5985-49fc-bffd-1edb8cfbf5cc")
_PROMPT_VERSIONS: Final = (
    RESEARCH_PLANNING_PROMPT_VERSION,
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    INDEPENDENT_REVIEW_PROMPT_VERSION,
)

type EvaluationCallable = Callable[
    [dict[str, object], dict[str, object] | None],
    EvaluationResult,
]


class LocalMetricRecord(BaseModel):
    """One privacy-safe deterministic observation from the offline baseline."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    applicable: bool
    passed: bool
    score: bool | int | float | None = None


class LocalScenarioRecord(BaseModel):
    """Offline results for one curated synthetic scenario."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(min_length=1)
    target: EvaluationTargetKind
    passed: bool
    metrics: tuple[LocalMetricRecord, ...]


class LocalMetricSummary(BaseModel):
    """Aggregate one metric without mixing non-applicable observations."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    key: str = Field(min_length=1)
    applicable_count: Annotated[int, Field(ge=0)]
    passed_count: Annotated[int, Field(ge=0)]
    observed_mean: float | None


class LocalEvaluationReport(BaseModel):
    """Serializable offline baseline report containing no target payloads."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    baseline_name: str = Field(min_length=1)
    recorded_on: date
    dataset_name: str = Field(min_length=1)
    graph_version: str = Field(min_length=1)
    scenario_count: Annotated[int, Field(ge=0)]
    passed_scenario_count: Annotated[int, Field(ge=0)]
    metric_summaries: tuple[LocalMetricSummary, ...]
    scenarios: tuple[LocalScenarioRecord, ...]

    @property
    def passed(self) -> bool:
        """Return whether every selected scenario met every applicable hard gate."""
        return self.scenario_count == self.passed_scenario_count


class DatasetSyncResult(BaseModel):
    """Bounded result of one explicitly requested LangSmith dataset sync."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_name: str = Field(min_length=1)
    dataset_created: bool
    example_count: Annotated[int, Field(ge=0)]


class UploadedExperimentReport(BaseModel):
    """Privacy-safe completion status for one uploaded LangSmith experiment."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    experiment_name: str = Field(min_length=1)
    example_count: Annotated[int, Field(ge=0)]
    failed_example_count: Annotated[int, Field(ge=0)]

    @property
    def passed(self) -> bool:
        """Return whether every target and deterministic hard gate passed."""
        return self.example_count > 0 and self.failed_example_count == 0


def _target_for_scenario(scenario: EvaluationScenario, *, live: bool = False) -> EvaluationTarget:
    if live:
        if scenario.target is not EvaluationTargetKind.GRAPH_FAKE:
            raise ValueError("Live end-to-end evaluation accepts only a graph scenario")
        return live_end_to_end_target
    targets: dict[EvaluationTargetKind, EvaluationTarget] = {
        EvaluationTargetKind.SEARCH_PLANNING: search_planning_target,
        EvaluationTargetKind.EVIDENCE_VERIFICATION: evidence_verification_target,
        EvaluationTargetKind.RESEARCH_FIT: research_fit_target,
        EvaluationTargetKind.GRAPH_FAKE: fake_end_to_end_target,
    }
    try:
        return targets[scenario.target]
    except KeyError as error:
        raise ValueError(f"No offline target for {scenario.target.value}") from error


def dispatch_evaluation_target(
    inputs: dict[str, object],
    *,
    live: bool = False,
) -> dict[str, object]:
    """Route one dataset envelope to its typed component or graph target."""
    raw_scenario = inputs.get("scenario", inputs)
    scenario = EvaluationScenario.model_validate(raw_scenario)
    return _target_for_scenario(scenario, live=live)(inputs)


def _metric_passed(result: EvaluationResult) -> tuple[bool, bool]:
    if result.score is None:
        return False, True
    metadata = result.metadata or {}
    if metadata.get("lower_is_better") is True:
        return True, metadata.get("threshold_passed") is True
    return True, bool(result.score)


def _metric_record(result: EvaluationResult) -> LocalMetricRecord:
    applicable, passed = _metric_passed(result)
    score = result.score
    if score is not None and not isinstance(score, (bool, int, float)):
        raise TypeError("Evaluation scores must be Boolean or numeric")
    return LocalMetricRecord(
        key=result.key,
        applicable=applicable,
        passed=passed,
        score=score,
    )


def _selected_scenarios(
    scenarios: Sequence[EvaluationScenario],
    target: EvaluationTargetKind | None,
) -> tuple[EvaluationScenario, ...]:
    if target is None:
        return tuple(scenarios)
    if target is EvaluationTargetKind.GRAPH_LIVE:
        return tuple(
            scenario
            for scenario in scenarios
            if "graph-live" in scenario.splits
            and scenario.target is EvaluationTargetKind.GRAPH_FAKE
        )
    return tuple(scenario for scenario in scenarios if scenario.target is target)


def run_local_baseline(
    *,
    scenarios: Sequence[EvaluationScenario] = EVALUATION_SCENARIOS,
    target: EvaluationTargetKind | None = None,
    evaluators: Sequence[EvaluationCallable] = DETERMINISTIC_EVALUATORS,
    recorded_on: date = date(2026, 8, 29),
) -> LocalEvaluationReport:
    """Execute fake targets and deterministic evaluators with no LangSmith client."""
    if target is EvaluationTargetKind.GRAPH_LIVE:
        raise ValueError("The offline baseline cannot execute the live graph target")
    records: list[LocalScenarioRecord] = []
    metric_values: dict[str, list[LocalMetricRecord]] = defaultdict(list)
    for scenario in _selected_scenarios(scenarios, target):
        inputs = evaluation_dataset_inputs(scenario)
        outputs = dispatch_evaluation_target(inputs)
        reference_outputs = evaluation_dataset_reference_outputs(scenario)
        observations = tuple(
            _metric_record(evaluator(outputs, reference_outputs)) for evaluator in evaluators
        )
        for observation in observations:
            metric_values[observation.key].append(observation)
        records.append(
            LocalScenarioRecord(
                scenario_id=scenario.scenario_id,
                target=scenario.target,
                passed=all(item.passed for item in observations),
                metrics=observations,
            )
        )

    summaries: list[LocalMetricSummary] = []
    for evaluator in evaluators:
        key = evaluator.__name__
        values = metric_values.get(key, [])
        applicable = [item for item in values if item.applicable]
        numeric_scores = [float(item.score) for item in applicable if item.score is not None]
        summaries.append(
            LocalMetricSummary(
                key=key,
                applicable_count=len(applicable),
                passed_count=sum(item.passed for item in applicable),
                observed_mean=(
                    sum(numeric_scores) / len(numeric_scores) if numeric_scores else None
                ),
            )
        )
    return LocalEvaluationReport(
        baseline_name=LOCAL_BASELINE_NAME,
        recorded_on=recorded_on,
        dataset_name=EVALUATION_DATASET_NAME,
        graph_version=GRAPH_VERSION,
        scenario_count=len(records),
        passed_scenario_count=sum(record.passed for record in records),
        metric_summaries=tuple(summaries),
        scenarios=tuple(records),
    )


def stable_example_id(dataset_name: str, scenario_id: str) -> UUID:
    """Derive an idempotent example identifier from stable public labels."""
    return uuid5(_EVALUATION_EXAMPLE_NAMESPACE, f"{dataset_name}:{scenario_id}")


def evaluation_example(scenario: EvaluationScenario, dataset_name: str) -> ExampleCreate:
    """Build one synthetic LangSmith example with bounded metadata."""
    return ExampleCreate(  # type: ignore[no-untyped-call]
        id=stable_example_id(dataset_name, scenario.scenario_id),
        inputs=evaluation_dataset_inputs(scenario),
        outputs=evaluation_dataset_reference_outputs(scenario),
        metadata={
            "application": EVALUATION_APPLICATION,
            "evaluation_scenario_id": scenario.scenario_id,
            "evaluation_target": scenario.target.value,
            "scenario_version": EVALUATION_SCENARIO_VERSION,
            "graph_version": GRAPH_VERSION,
            "synthetic_data": True,
        },
        split=list(scenario.splits),
    )


def create_langsmith_evaluation_client(settings: LangSmithSettings) -> Client:
    """Create a privacy-hardened client only after explicit credential validation."""
    api_key = settings.require_evaluation_api_key().get_secret_value()
    return Client(
        api_url=str(settings.endpoint),
        api_key=api_key,
        workspace_id=settings.workspace_id,
        hide_inputs=True,
        hide_outputs=True,
        hide_metadata=sanitize_evaluation_trace_metadata,
        omit_traced_runtime_info=True,
    )


def sync_evaluation_dataset(
    client: Client,
    *,
    dataset_name: str = EVALUATION_DATASET_NAME,
    scenarios: Sequence[EvaluationScenario] = EVALUATION_SCENARIOS,
) -> DatasetSyncResult:
    """Create or idempotently upsert the versioned synthetic evaluation dataset."""
    created = not client.has_dataset(dataset_name=dataset_name)
    if created:
        client.create_dataset(
            dataset_name,
            description=(
                "ScholarPath M12 synthetic regression scenarios for planning, verification, "
                "Research Fit, resilience, review, and Candidate approval enforcement."
            ),
            metadata={
                "application": EVALUATION_APPLICATION,
                "scenario_version": EVALUATION_SCENARIO_VERSION,
                "graph_version": GRAPH_VERSION,
                "synthetic_data": True,
            },
        )
    client.create_examples(
        dataset_name=dataset_name,
        examples=[evaluation_example(scenario, dataset_name) for scenario in scenarios],
    )
    return DatasetSyncResult(
        dataset_name=dataset_name,
        dataset_created=created,
        example_count=len(scenarios),
    )


def _scenario_from_example(example: Example) -> EvaluationScenario:
    inputs = example.inputs or {}
    return EvaluationScenario.model_validate(inputs.get("scenario", inputs))


def _experiment_metadata(*, live: bool, judges: bool) -> dict[str, object]:
    return {
        "application": EVALUATION_APPLICATION,
        "environment": Environment.TEST.value,
        "graph_version": GRAPH_VERSION,
        "prompt_version": "multiple",
        "model_provider": "multiple" if live else "fake",
        "evaluation_target": EvaluationTargetKind.GRAPH_LIVE.value if live else "mixed",
        "llm_judges_enabled": judges,
    }


def build_openai_judge_evaluators(
    settings: OpenAIPlanningSettings,
    evaluation_settings: EvaluationSettings,
) -> tuple[JudgeEvaluator, ...]:
    """Instantiate the optional judge only after its own explicit CLI selection."""
    if settings.api_key is None or not settings.api_key.get_secret_value().strip():
        raise ProviderConfigurationError(
            "Missing API key for provider 'openai' while LLM judges are enabled."
        )
    judge = OpenAIEvaluationJudgeAdapter(
        EvaluationJudgeConfiguration(
            api_key=settings.api_key,
            model=evaluation_settings.evaluation_judge_model,
            timeout_seconds=evaluation_settings.evaluation_judge_timeout_seconds,
        )
    )
    return make_judge_evaluators(judge)


def run_uploaded_experiment(
    client: Client,
    *,
    evaluation_settings: EvaluationSettings,
    dataset_name: str = EVALUATION_DATASET_NAME,
    target: EvaluationTargetKind | None = None,
    judge_evaluators: Sequence[JudgeEvaluator] = (),
    live: bool = False,
) -> UploadedExperimentReport:
    """Run one uploaded experiment after all environment and CLI gates are satisfied."""
    if not evaluation_settings.run_langsmith_evals:
        raise ProviderConfigurationError(
            "LangSmith evaluation upload is disabled. Set "
            "SCHOLARPATH_RUN_LANGSMITH_EVALS=true to opt in."
        )
    if live and not evaluation_settings.run_live_e2e_evals:
        raise ProviderConfigurationError(
            "Live end-to-end evaluation is disabled. Set "
            "SCHOLARPATH_RUN_LIVE_E2E_EVALS=true to opt in."
        )
    selected_target = EvaluationTargetKind.GRAPH_LIVE if live else target
    selected_ids = {
        scenario.scenario_id
        for scenario in _selected_scenarios(EVALUATION_SCENARIOS, selected_target)
    }
    examples = tuple(
        example
        for example in client.list_examples(dataset_name=dataset_name)
        if _scenario_from_example(example).scenario_id in selected_ids
    )
    if not examples:
        raise ValueError("No evaluation examples matched the selected target")

    def target_function(inputs: dict[str, object]) -> dict[str, object]:
        return dispatch_evaluation_target(inputs, live=live)

    evaluators: list[Callable[..., EvaluationResult]] = [
        *DETERMINISTIC_EVALUATORS,
        *judge_evaluators,
    ]
    result = client.evaluate(
        target_function,
        data=examples,
        evaluators=evaluators,
        metadata=_experiment_metadata(live=live, judges=bool(judge_evaluators)),
        experiment_prefix=f"{evaluation_settings.evaluation_experiment_prefix}-{GRAPH_VERSION}",
        description="ScholarPath M12 synthetic regression evaluation.",
        max_concurrency=1 if live else 0,
        blocking=True,
        upload_results=True,
        error_handling="log",
    )
    rows = tuple(result)
    return UploadedExperimentReport(
        experiment_name=result.experiment_name,
        example_count=len(rows),
        failed_example_count=sum(_uploaded_row_failed(row) for row in rows),
    )


def _uploaded_row_failed(row: object) -> bool:
    """Detect target errors or deterministic hard-gate failures in one result row."""
    if not isinstance(row, Mapping):
        return True
    run = row.get("run")
    if run is None or bool(getattr(run, "error", None)):
        return True
    raw_evaluations = row.get("evaluation_results")
    if not isinstance(raw_evaluations, Mapping):
        return True
    raw_results = raw_evaluations.get("results")
    if not isinstance(raw_results, Sequence) or isinstance(raw_results, (str, bytes)):
        return True
    results = tuple(item for item in raw_results if isinstance(item, EvaluationResult))
    hard_gate_keys = {evaluator.__name__ for evaluator in DETERMINISTIC_EVALUATORS}
    hard_gate_results = tuple(item for item in results if item.key in hard_gate_keys)
    if {item.key for item in hard_gate_results} != hard_gate_keys:
        return True
    return any(not _metric_passed(item)[1] for item in hard_gate_results)


__all__ = [
    "LOCAL_BASELINE_NAME",
    "DatasetSyncResult",
    "LocalEvaluationReport",
    "LocalMetricRecord",
    "LocalMetricSummary",
    "LocalScenarioRecord",
    "UploadedExperimentReport",
    "build_openai_judge_evaluators",
    "create_langsmith_evaluation_client",
    "dispatch_evaluation_target",
    "evaluation_example",
    "run_local_baseline",
    "run_uploaded_experiment",
    "stable_example_id",
    "sync_evaluation_dataset",
]
