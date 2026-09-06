"""Offline regression execution and explicitly gated LangSmith experiments."""

from __future__ import annotations

from collections import Counter, defaultdict
from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Annotated, Final, Literal
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
from ..observability import GRAPH_VERSION, langsmith_retry_config, langsmith_timeout_ms
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

LOCAL_BASELINE_NAME: Final = "scholarpath-m13-fake-baseline-2026-08-30"
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


class EvaluationFailure(BaseModel):
    """A failed check linked to a public case, without evaluated content or exceptions."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str = Field(min_length=1)
    target: EvaluationTargetKind | None
    key: str = Field(min_length=1)
    category: Literal["metric_failed", "target_error", "evaluator_error", "missing_result"]
    score: bool | int | float | None = None
    run_id: UUID | None = None


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
    failures: tuple[EvaluationFailure, ...] = ()

    @property
    def passed(self) -> bool:
        """Return whether every selected scenario met every applicable hard gate."""
        return self.scenario_count > 0 and self.scenario_count == self.passed_scenario_count


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
    failures: tuple[EvaluationFailure, ...] = ()

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
    recorded_on: date = date(2026, 8, 30),
) -> LocalEvaluationReport:
    """Execute fake targets and deterministic evaluators with no LangSmith client."""
    if target is EvaluationTargetKind.GRAPH_LIVE:
        raise ValueError("The offline baseline cannot execute the live graph target")
    records: list[LocalScenarioRecord] = []
    failures: list[EvaluationFailure] = []
    metric_values: dict[str, list[LocalMetricRecord]] = defaultdict(list)
    for scenario in _selected_scenarios(scenarios, target):
        inputs = evaluation_dataset_inputs(scenario)
        reference_outputs = evaluation_dataset_reference_outputs(scenario)
        case_failures: list[EvaluationFailure] = []
        observations_list: list[LocalMetricRecord] = []
        try:
            outputs = dispatch_evaluation_target(inputs)
        except Exception:
            case_failures.append(
                EvaluationFailure(
                    scenario_id=scenario.scenario_id,
                    target=scenario.target,
                    key="target_execution",
                    category="target_error",
                )
            )
        else:
            for evaluator in evaluators:
                category: Literal["metric_failed", "evaluator_error"]
                try:
                    observation = _metric_record(evaluator(outputs, reference_outputs))
                except Exception:
                    observation = LocalMetricRecord(
                        key=evaluator.__name__, applicable=True, passed=False
                    )
                    category = "evaluator_error"
                else:
                    category = "metric_failed"
                observations_list.append(observation)
                if not observation.passed:
                    case_failures.append(
                        EvaluationFailure(
                            scenario_id=scenario.scenario_id,
                            target=scenario.target,
                            key=observation.key,
                            category=category,
                            score=observation.score,
                        )
                    )
        observations = tuple(observations_list)
        failures.extend(case_failures)
        for observation in observations:
            metric_values[observation.key].append(observation)
        records.append(
            LocalScenarioRecord(
                scenario_id=scenario.scenario_id,
                target=scenario.target,
                passed=not case_failures,
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
        failures=tuple(failures),
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
        timeout_ms=langsmith_timeout_ms(settings),
        retry_config=langsmith_retry_config(settings),
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
                "ScholarPath M12 synthetic regression scenarios replayed against the M13 "
                "release graph for planning, verification, Research Fit, resilience, review, "
                "and Candidate approval enforcement."
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
        description="ScholarPath M13 release regression over the M12 synthetic dataset.",
        max_concurrency=1 if live else 0,
        blocking=True,
        upload_results=True,
        error_handling="log",
    )
    rows = tuple(result)
    cases_by_example_id = {example.id: _scenario_from_example(example) for example in examples}
    row_failures = tuple(
        _uploaded_row_failures(row, cases_by_example_id, row_number=index)
        for index, row in enumerate(rows, start=1)
    )
    returned_ids = {
        getattr(row.get("example"), "id", None) for row in rows if isinstance(row, Mapping)
    }
    missing_count = max(0, len(examples) - len(rows))
    missing_cases = [
        scenario
        for example_id, scenario in cases_by_example_id.items()
        if example_id not in returned_ids
    ][:missing_count]
    missing_failures = tuple(
        EvaluationFailure(
            scenario_id=scenario.scenario_id,
            target=scenario.target,
            key="evaluation_results",
            category="missing_result",
        )
        for scenario in missing_cases
    )
    return UploadedExperimentReport(
        experiment_name=result.experiment_name,
        example_count=max(len(examples), len(rows)),
        failed_example_count=sum(bool(failures) for failures in row_failures) + missing_count,
        failures=tuple(failure for failures in row_failures for failure in failures)
        + missing_failures,
    )


def _uploaded_row_failures(
    row: object,
    cases_by_example_id: Mapping[UUID, EvaluationScenario],
    *,
    row_number: int,
) -> tuple[EvaluationFailure, ...]:
    """Describe failures using known case IDs; never trust free-text SDK error content."""
    values = row if isinstance(row, Mapping) else {}
    run = values.get("run")
    example_id = getattr(values.get("example"), "id", None)
    scenario = cases_by_example_id.get(example_id) if isinstance(example_id, UUID) else None
    run_id = getattr(run, "id", None)

    def failure(
        key: str,
        category: Literal["metric_failed", "target_error", "evaluator_error", "missing_result"],
        score: bool | int | float | None = None,
    ) -> EvaluationFailure:
        return EvaluationFailure(
            scenario_id=scenario.scenario_id if scenario else f"unidentified-example-{row_number}",
            target=scenario.target if scenario else None,
            key=key,
            category=category,
            score=score,
            run_id=run_id if isinstance(run_id, UUID) else None,
        )

    if run is None or bool(getattr(run, "error", None)):
        return (failure("target_execution", "target_error"),)
    if scenario is None:
        return (failure("case_identity", "missing_result"),)
    raw_evaluations = values.get("evaluation_results")
    if not isinstance(raw_evaluations, Mapping):
        return (failure("evaluation_results", "missing_result"),)
    raw_results = raw_evaluations.get("results")
    if not isinstance(raw_results, Sequence) or isinstance(raw_results, (str, bytes)):
        return (failure("evaluation_results", "missing_result"),)
    results = tuple(item for item in raw_results if isinstance(item, EvaluationResult))
    hard_gate_keys = {evaluator.__name__ for evaluator in DETERMINISTIC_EVALUATORS}
    hard_gate_results = tuple(item for item in results if item.key in hard_gate_keys)
    failures = [
        failure(key, "missing_result")
        for key in sorted(hard_gate_keys - {item.key for item in hard_gate_results})
    ]
    for item in hard_gate_results:
        if (item.metadata or {}).get("error") is True:
            failures.append(failure(item.key, "evaluator_error"))
        elif not _metric_passed(item)[1]:
            failures.append(failure(item.key, "metric_failed", _metric_record(item).score))
    return tuple(failures)


_FAILURE_GUIDANCE: Final = {
    "schema_validity": "Expected a valid typed output; inspect the target response contract.",
    "canonical_terminology": "Expected canonical role labels; inspect generated terminology.",
    "evidence_id_validity": "Expected owned evidence IDs; inspect citation references.",
    "source_url_presence": "Expected source URLs on claims; inspect evidence provenance.",
    "score_range_and_component_totals": "Expected bounded, summed scores; inspect the rubric.",
    "no_unsupported_availability_claim": "Expected source-backed availability; inspect claims.",
    "no_admission_probability": "Expected no admission prediction; inspect assessment wording.",
    "correct_fallback_route": "Expected the labeled retry/fallback route; inspect search attempts.",
    "duplicate_supervisor_rate": "Expected the duplicate-rate limit; inspect deduplication.",
    "human_approval_enforcement": "Expected approval before persistence; inspect the review gate.",
}


def format_failure_summary(report: LocalEvaluationReport | UploadedExperimentReport) -> str:
    """Render deterministic case-level failures and counts without free-text payloads."""
    if isinstance(report, LocalEvaluationReport):
        total = report.scenario_count
        failed = total - report.passed_scenario_count
    else:
        total, failed = report.example_count, report.failed_example_count
    if total == 0:
        return "Failure summary: no evaluation cases ran. Check the dataset and target selection."
    if failed == 0:
        return "Failure summary: no failed cases. Expected fallback or rejection is not a failure."
    lines = [f"Failure summary: {failed}/{total} cases failed."]
    if not report.failures:
        return "\n".join((*lines, "Case details unavailable; inspect the experiment results."))
    counts = Counter((item.category, item.key) for item in report.failures)
    lines.append("Failed checks by frequency (a case can fail more than one check):")
    for (category, key), count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        lines.append(f"- {key} [{category}]: {count}")
    lines.append("Failed cases:")
    for item in sorted(
        report.failures, key=lambda item: (item.scenario_id, item.key, item.category)
    ):
        target = item.target.value if item.target else "unknown target"
        score = "not produced" if item.score is None else str(item.score)
        if item.category == "target_error":
            guidance = (
                "Target raised an error; inspect that case's execution. Other cases run separately."
            )
        elif item.category == "evaluator_error":
            guidance = "Evaluator raised an error; inspect the check before trusting its score."
        elif item.category == "missing_result":
            guidance = "Required evaluation result missing; inspect evaluator completion."
        else:
            guidance = _FAILURE_GUIDANCE.get(item.key, "Inspect the evaluator's declared pass bar.")
        lines.append(
            f"- {item.scenario_id} [{target}]: {item.key}; "
            f"{item.category}; score={score}. {guidance}"
        )
        if item.run_id:
            lines.append(f"  LangSmith run ID: {item.run_id}")
    return "\n".join(lines)


__all__ = [
    "LOCAL_BASELINE_NAME",
    "DatasetSyncResult",
    "EvaluationFailure",
    "LocalEvaluationReport",
    "LocalMetricRecord",
    "LocalMetricSummary",
    "LocalScenarioRecord",
    "UploadedExperimentReport",
    "build_openai_judge_evaluators",
    "create_langsmith_evaluation_client",
    "dispatch_evaluation_target",
    "evaluation_example",
    "format_failure_summary",
    "run_local_baseline",
    "run_uploaded_experiment",
    "stable_example_id",
    "sync_evaluation_dataset",
]
