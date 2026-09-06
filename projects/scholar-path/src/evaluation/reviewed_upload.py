"""Opt-in, fake-only LangSmith baseline for the frozen reviewed thirty-case cohort."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Iterator, Sequence
from contextlib import redirect_stdout
from dataclasses import dataclass
from datetime import UTC, date, datetime
from functools import wraps
from io import StringIO
from time import sleep
from typing import Literal, Protocol
from uuid import UUID

from langsmith import Client, tracing_context
from langsmith.evaluation import EvaluationResult
from langsmith.evaluation._runner import ExperimentResultRow
from langsmith.run_helpers import get_current_run_tree
from langsmith.schemas import Example, ExampleCreate, Feedback, Run
from pydantic import Field

from ..config import (
    EvaluationSettings,
    ProviderConfigurationError,
    load_evaluation_settings,
    load_langsmith_settings,
)
from ..observability import GRAPH_VERSION
from .evaluators import DETERMINISTIC_EVALUATORS
from .measurements import RuntimeBudget, runtime_budgets_passed, summarize_runtime
from .models import EvaluationModel, EvaluationScenario, EvaluationTargetKind
from .reviewed_manifest import ReviewedEvaluationManifest, build_reviewed_manifest
from .reviewed_tracing import create_reviewed_trace_client
from .runner import (
    EvaluationCallable,
    EvaluationFailure,
    LocalMetricRecord,
    UploadedExperimentReport,
    _metric_record,
    _uploaded_row_failures,
    _uploaded_run_references,
    _uploaded_runtime_cases,
    dispatch_evaluation_target,
    stable_example_id,
)
from .scenarios import evaluation_dataset_inputs, evaluation_dataset_reference_outputs
from .synthetic_tracing import (
    SYNTHETIC_EVALUATION_TRACE_TAG,
    SyntheticEvaluationObservability,
)
from .targets import fake_end_to_end_target


class ReviewedUploadError(RuntimeError):
    """A bounded upload/readback failed without exposing a provider response."""


class ReviewedDatasetSnapshot(EvaluationModel):
    """Server examples pinned to one validated dataset snapshot."""

    dataset_id: UUID
    dataset_name: str
    dataset_url: str | None
    snapshot_as_of: datetime
    examples: tuple[Example, ...]
    dataset_created: bool


class ReviewedCaseObservation(EvaluationModel):
    """One public synthetic case and observed deterministic feedback with provenance."""

    scenario_id: str
    example_id: UUID
    run_id: UUID
    trace_id: UUID
    run_url: str | None
    persisted: bool
    graph_child_visible: bool | None
    feedback_persisted: bool
    metrics: tuple[LocalMetricRecord, ...]
    duplicate_rate_semantics_source: Literal[
        "evaluation_result",
        "feedback_metadata",
        "graph_expected_behavior",
        "not_applicable",
        "unavailable",
    ] = "evaluation_result"


class ReviewedUploadedReport(UploadedExperimentReport):
    """Actual authenticated links and measurements; never a live-quality claim."""

    recorded_on: date
    observation_source: Literal["upload", "readback"] = "upload"
    graph_version: str
    dataset_name: str
    dataset_id: UUID
    dataset_url: str | None
    snapshot_as_of: datetime
    dataset_created: bool
    reviewed_version: str
    content_digest: str
    source_draft_digest: str
    approval_scope: Literal["expected_behaviors"] = "expected_behaviors"
    execution_mode: Literal["fake_only"] = "fake_only"
    experiment_id: UUID
    experiment_url: str | None
    cases: tuple[ReviewedCaseObservation, ...] = Field(min_length=30, max_length=30)
    readback_complete: bool
    provisional_runtime_budgets_passed: bool | None


def reviewed_metadata(manifest: ReviewedEvaluationManifest) -> dict[str, object]:
    """Only public cohort identity and fixed execution dimensions, not review quotations."""
    return {
        "application": "scholarpath",
        "environment": "test",
        "graph_version": GRAPH_VERSION,
        "dataset_name": manifest.dataset_name,
        "reviewed_version": manifest.reviewed_version,
        "content_digest": manifest.content_digest,
        "source_draft_digest": manifest.source_draft_digest,
        "approval_scope": manifest.approval_scope,
        "synthetic_data": True,
        "model_provider": "fake",
    }


def _frozen_examples(manifest: ReviewedEvaluationManifest) -> tuple[ExampleCreate, ...]:
    return tuple(
        ExampleCreate(  # type: ignore[no-untyped-call]
            id=stable_example_id(manifest.dataset_name, case.scenario.scenario_id),
            inputs=evaluation_dataset_inputs(case.scenario),
            outputs=evaluation_dataset_reference_outputs(case.scenario),
            metadata={
                **reviewed_metadata(manifest),
                "evaluation_scenario_id": case.scenario.scenario_id,
                "evaluation_target": case.scenario.target.value,
                "scenario_version": case.source_version,
                "dataset_split": list(case.scenario.splits),
            },
            split=list(case.scenario.splits),
        )
        for case in manifest.source_draft.cases
    )


def sync_reviewed_dataset(
    client: Client, manifest: ReviewedEvaluationManifest, *, create_if_missing: bool = True
) -> ReviewedDatasetSnapshot:
    """Create once or validate existing data, never upsert over reviewed expectations."""
    manifest = ReviewedEvaluationManifest.model_validate(manifest.model_dump())
    expected = _frozen_examples(manifest)
    dataset_metadata = {**reviewed_metadata(manifest), "runtime": {}}
    try:
        created = not client.has_dataset(dataset_name=manifest.dataset_name)
        if created and not create_if_missing:
            raise ReviewedUploadError(
                "Reviewed dataset is absent; read-only inspection cannot create it."
            )
        if created:
            dataset = client.create_dataset(
                manifest.dataset_name,
                description="Thirty synthetic cases with explicitly approved expected behaviors.",
                metadata=dataset_metadata,
            )
            client.create_examples(dataset_id=dataset.id, examples=expected, max_concurrency=1)
        else:
            dataset = client.read_dataset(dataset_name=manifest.dataset_name)
        if dataset.metadata != dataset_metadata:
            raise ReviewedUploadError("Reviewed dataset metadata differs; nothing was overwritten.")
        version = client.read_dataset_version(dataset_id=dataset.id, tag="latest")
        examples = tuple(
            client.list_examples(
                dataset_id=dataset.id, as_of=version.as_of, limit=31, include_attachments=False
            )
        )
        by_id = {example.id: example for example in examples}
        if len(examples) != 30 or set(by_id) != {example.id for example in expected}:
            raise ReviewedUploadError("Reviewed dataset case IDs differ; nothing was overwritten.")
        ordered: list[Example] = []
        for wanted in expected:
            assert wanted.id is not None
            actual = by_id[wanted.id]
            if (
                actual.dataset_id != dataset.id
                or actual.inputs != wanted.inputs
                or actual.outputs != wanted.outputs
                or actual.metadata != wanted.metadata
                or actual.modified_at is None
            ):
                raise ReviewedUploadError(
                    "Reviewed example content or version differs; nothing was overwritten."
                )
            ordered.append(actual)
        return ReviewedDatasetSnapshot(
            dataset_id=dataset.id,
            dataset_name=manifest.dataset_name,
            dataset_url=dataset.url,
            snapshot_as_of=version.as_of,
            examples=tuple(ordered),
            dataset_created=created,
        )
    except ReviewedUploadError:
        raise
    except Exception as error:
        raise ReviewedUploadError(
            "LangSmith dataset upload or snapshot readback failed."
        ) from error


def _target(manifest: ReviewedEvaluationManifest, inputs: dict[str, object]) -> dict[str, object]:
    # Never execute arbitrary instructions/configurations received from a remote dataset.
    scenario = next(
        (
            case.scenario
            for case in manifest.source_draft.cases
            if inputs == evaluation_dataset_inputs(case.scenario)
        ),
        None,
    )
    if scenario is None:
        raise ReviewedUploadError("Evaluation input does not match a frozen reviewed case.")
    parent = get_current_run_tree()
    if parent is not None:
        parent.add_tags([SYNTHETIC_EVALUATION_TRACE_TAG, "model-provider:fake"])
        parent.add_metadata(reviewed_metadata(manifest))
    if scenario.target is EvaluationTargetKind.GRAPH_FAKE:
        return fake_end_to_end_target(inputs, observability=SyntheticEvaluationObservability())
    return dispatch_evaluation_target(inputs, live=False)


def _readback(
    client: Client, project_id: UUID, run_ids: Sequence[UUID]
) -> tuple[dict[UUID, Run], dict[UUID, dict[str, tuple[object, object]]]]:
    """Poll persisted roots and feedback at most three times, never rerun the experiment."""
    roots: dict[UUID, Run] = {}
    feedback: dict[UUID, dict[str, tuple[object, object]]] = {}
    keys = {item.__name__ for item in DETERMINISTIC_EVALUATORS}
    for attempt in range(3):
        roots = {
            run.id: run
            for run in client.list_runs(project_id=project_id, run_ids=run_ids, limit=31)
        }
        feedback = {}
        for item in _feedback_for_runs(client, run_ids):
            if item.run_id is not None:
                values = feedback.setdefault(item.run_id, {})
                if item.key in values:
                    raise ReviewedUploadError("Duplicate deterministic feedback in readback.")
                values[item.key] = (item.score, item.value)
        if set(roots) == set(run_ids) and all(
            set(feedback.get(run_id, {})) == keys for run_id in run_ids
        ):
            break
        if attempt < 2:
            sleep(0.5)
    return roots, feedback


def _uploaded_evaluator(evaluator: EvaluationCallable) -> EvaluationCallable:
    """Preserve deterministic scoring; persist the rate metric's interpretation too."""

    @wraps(evaluator)
    def evaluate(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None = None
    ) -> EvaluationResult:
        result = evaluator(outputs, reference_outputs)
        if result.key == "duplicate_supervisor_rate" and result.metadata:
            return result.model_copy(
                update={
                    "extra": dict(result.metadata),
                    "evaluator_info": dict(result.metadata),
                }
            )
        return result

    return evaluate


def _graph_child_visible(client: Client, project_id: UUID, root: Run) -> bool:
    for attempt in range(3):
        if any(
            run.name == "scholarpath_graph"
            and run.trace_id == root.trace_id
            and run.parent_run_id == root.id
            for run in client.list_runs(project_id=project_id, parent_run_id=root.id, limit=3)
        ):
            return True
        if attempt < 2:
            sleep(0.5)
    return False


def run_reviewed_upload(
    client: Client,
    manifest: ReviewedEvaluationManifest,
    *,
    evaluation_settings: EvaluationSettings,
    flush_timeout_seconds: float = 10,
) -> ReviewedUploadedReport:
    """One complete, opt-in experiment; only LangSmith is live, all targets use fakes."""
    if not evaluation_settings.run_langsmith_evals:
        raise ProviderConfigurationError(
            "Set SCHOLARPATH_RUN_LANGSMITH_EVALS=true to allow the reviewed LangSmith upload."
        )
    if not 0 < flush_timeout_seconds <= 30:
        raise ValueError("Flush timeout must be greater than zero and at most thirty seconds")
    manifest = ReviewedEvaluationManifest.model_validate(manifest.model_dump())
    snapshot = sync_reviewed_dataset(client, manifest)

    def target_function(inputs: dict[str, object]) -> dict[str, object]:
        return _target(manifest, inputs)

    try:
        # SDK progress text must not corrupt the machine-readable report on stdout.
        with redirect_stdout(StringIO()), tracing_context(enabled=True, client=client):
            result = client.evaluate(
                target_function,
                data=snapshot.examples,
                evaluators=[_uploaded_evaluator(item) for item in DETERMINISTIC_EVALUATORS],
                metadata={
                    **reviewed_metadata(manifest),
                    "snapshot_as_of": snapshot.snapshot_as_of.isoformat(),
                },
                experiment_prefix=f"scholarpath-week4-reviewed-upload-{GRAPH_VERSION}",
                description="Approved thirty-case baseline: fake tools, deterministic evaluators.",
                max_concurrency=0,
                num_repetitions=1,
                blocking=True,
                upload_results=True,
                error_handling="log",
            )
        client.flush(timeout=flush_timeout_seconds)
        return _assemble_report(client, manifest, snapshot, result)
    except ReviewedUploadError:
        raise
    except Exception as error:
        raise ReviewedUploadError(
            "LangSmith experiment execution or bounded readback failed."
        ) from error


class ReviewedResultPort(Protocol):
    """The result coordinates needed from the SDK or read-only reconstruction."""

    @property
    def experiment_name(self) -> str: ...

    @property
    def experiment_id(self) -> UUID: ...

    @property
    def url(self) -> str | None: ...

    def __iter__(self) -> Iterator[ExperimentResultRow]: ...


@dataclass(frozen=True)
class _SavedRows:
    experiment_name: str
    experiment_id: UUID
    url: str | None
    rows: tuple[ExperimentResultRow, ...]

    def __iter__(self) -> Iterator[ExperimentResultRow]:
        return iter(self.rows)


def _feedback_for_runs(client: Client, run_ids: Sequence[UUID]) -> tuple[Feedback, ...]:
    """Keep each query below the SDK's 100-item pagination boundary."""
    keys = sorted(item.__name__ for item in DETERMINISTIC_EVALUATORS)
    feedback: list[Feedback] = []
    for offset in range(0, len(run_ids), 8):
        batch = run_ids[offset : offset + 8]
        feedback.extend(
            client.list_feedback(run_ids=batch, feedback_key=keys, limit=len(batch) * len(keys) + 1)
        )
    return tuple(feedback)


def _assemble_report(
    client: Client,
    manifest: ReviewedEvaluationManifest,
    snapshot: ReviewedDatasetSnapshot,
    result: ReviewedResultPort,
    *,
    observation_source: Literal["upload", "readback"] = "upload",
) -> ReviewedUploadedReport:
    rows = tuple(result)
    project = client.read_project(project_name=result.experiment_name)
    versions = [example.modified_at for example in snapshot.examples if example.modified_at]
    expected_metadata = {
        **reviewed_metadata(manifest),
        "snapshot_as_of": snapshot.snapshot_as_of.isoformat(),
        "dataset_version": max(versions).isoformat(),
    }
    if (
        project.reference_dataset_id != snapshot.dataset_id
        or project.id != UUID(str(result.experiment_id))
        or any(project.metadata.get(key) != value for key, value in expected_metadata.items())
    ):
        raise ReviewedUploadError("Experiment does not match the reviewed dataset snapshot.")
    scenarios = {
        example.id: case.scenario
        for example, case in zip(snapshot.examples, manifest.source_draft.cases, strict=True)
    }
    ids = [getattr(row.get("example"), "id", None) for row in rows]
    if len(rows) != 30 or len(set(ids)) != 30 or set(ids) != set(scenarios):
        raise ReviewedUploadError("Experiment returned missing, duplicate, or unknown cases.")
    references = _uploaded_run_references(rows)
    if len(references) != 30 or len({item.run_id for item in references}) != 30:
        raise ReviewedUploadError("Experiment did not return thirty distinct run references.")
    roots, feedback = _readback(client, project.id, [item.run_id for item in references])
    observations: list[ReviewedCaseObservation] = []
    for row in rows:
        example, local_run = row["example"], row["run"]
        scenario = scenarios[example.id]
        remote = roots.get(local_run.id)
        metrics = tuple(
            _metric_record(item)
            for item in row["evaluation_results"]["results"]
            if isinstance(item, EvaluationResult)
        )
        graph_child: bool | None = None
        if scenario.target is EvaluationTargetKind.GRAPH_FAKE:
            graph_child = _graph_child_visible(client, project.id, local_run)
        expected_feedback = {
            item.key: (item.score, item.value)
            for item in row["evaluation_results"]["results"]
            if isinstance(item, EvaluationResult)
        }
        observations.append(
            ReviewedCaseObservation(
                scenario_id=scenario.scenario_id,
                example_id=example.id,
                run_id=local_run.id,
                trace_id=local_run.trace_id,
                run_url=(remote.url or client.get_run_url(run=remote, project_id=project.id))
                if remote
                else None,
                persisted=remote is not None
                and remote.reference_example_id == example.id
                and remote.trace_id == local_run.trace_id,
                graph_child_visible=graph_child,
                feedback_persisted=len(metrics) == len(DETERMINISTIC_EVALUATORS)
                and feedback.get(local_run.id) == expected_feedback,
                metrics=metrics,
                duplicate_rate_semantics_source=next(
                    (item.extra or {}).get("reviewed_semantics_source", "evaluation_result")
                    for item in row["evaluation_results"]["results"]
                    if isinstance(item, EvaluationResult)
                    and item.key == "duplicate_supervisor_rate"
                ),
            )
        )
    failures = tuple(
        failure
        for index, row in enumerate(rows, 1)
        for failure in _uploaded_row_failures(row, scenarios, row_number=index)
    )
    # SDK evaluator exceptions are marked in `extra`, not the metric's metadata.
    failures += tuple(
        EvaluationFailure(
            scenario_id=scenarios[row["example"].id].scenario_id,
            target=scenarios[row["example"].id].target,
            key=item.key
            if item.key in {fn.__name__ for fn in DETERMINISTIC_EVALUATORS}
            else "evaluation_results",
            category="evaluator_error",
            run_id=row["run"].id,
        )
        for row in rows
        for item in row["evaluation_results"]["results"]
        if isinstance(item, EvaluationResult)
        and (
            bool((item.extra or {}).get("error"))
            or (item.score is None and item.value != "not_applicable")
        )
    )
    runtime_cases = _uploaded_runtime_cases(rows, scenarios, live=False)
    summaries = summarize_runtime(runtime_cases, RuntimeBudget())
    return ReviewedUploadedReport(
        experiment_name=result.experiment_name,
        experiment_id=project.id,
        experiment_url=result.url or project.url,
        example_count=len(rows),
        failed_example_count=len({item.scenario_id for item in failures}),
        failures=failures,
        runtime_cases=runtime_cases,
        runtime_summaries=summaries,
        run_references=references,
        recorded_on=project.start_time.date()
        if observation_source == "readback"
        else datetime.now(UTC).date(),
        observation_source=observation_source,
        graph_version=GRAPH_VERSION,
        dataset_name=snapshot.dataset_name,
        dataset_id=snapshot.dataset_id,
        dataset_url=snapshot.dataset_url,
        snapshot_as_of=snapshot.snapshot_as_of,
        dataset_created=snapshot.dataset_created,
        reviewed_version=manifest.reviewed_version,
        content_digest=manifest.content_digest,
        source_draft_digest=manifest.source_draft_digest,
        cases=tuple(observations),
        readback_complete=all(
            item.persisted
            and item.feedback_persisted
            and item.graph_child_visible is not False
            and item.duplicate_rate_semantics_source != "unavailable"
            for item in observations
        ),
        provisional_runtime_budgets_passed=runtime_budgets_passed(summaries),
    )


def _recovered_metrics(
    records: Sequence[Feedback], scenario: EvaluationScenario
) -> list[EvaluationResult]:
    """Restore rate interpretation from machine fields or a proven graph-gate implication."""
    expected_passed = any(item.key == "expected_behavior" and item.score == 1 for item in records)
    metrics: list[EvaluationResult] = []
    for item in records:
        metadata = item.extra
        extra = dict(item.extra or {})
        if item.key == "duplicate_supervisor_rate":
            if item.score is None and item.value == "not_applicable":
                extra["reviewed_semantics_source"] = "not_applicable"
            else:
                source = item.feedback_source
                source_metadata = getattr(source, "metadata", None)
                interpretation = dict(metadata or source_metadata or {})
                threshold = scenario.expected.maximum_duplicate_supervisor_rate
                if (
                    interpretation.get("lower_is_better") is True
                    and interpretation.get("threshold") == threshold
                    and type(interpretation.get("threshold_passed")) is bool
                ):
                    metadata = interpretation
                    extra["reviewed_semantics_source"] = "feedback_metadata"
                elif (
                    scenario.target is EvaluationTargetKind.GRAPH_FAKE
                    and expected_passed
                    and isinstance(item.score, (int, float))
                    and 0 <= item.score <= threshold
                ):
                    # _graph_behavior_matches requires duplicate/provenance threshold_passed.
                    # Its persisted true result proves this subgate; zero alone does not.
                    metadata = {
                        "lower_is_better": True,
                        "threshold": threshold,
                        "threshold_passed": True,
                    }
                    extra["reviewed_semantics_source"] = "graph_expected_behavior"
                else:
                    metadata = {"error": True}
                    extra["reviewed_semantics_source"] = "unavailable"
        metrics.append(
            EvaluationResult(
                key=item.key, score=item.score, value=item.value, metadata=metadata, extra=extra
            )
        )
    return metrics


def read_reviewed_experiment(
    client: Client,
    manifest: ReviewedEvaluationManifest,
    *,
    experiment_name: str,
    evaluation_settings: EvaluationSettings,
) -> ReviewedUploadedReport:
    """Recover saved feedback without executing targets, evaluators, or external writes."""
    if not evaluation_settings.run_langsmith_evals:
        raise ProviderConfigurationError("LangSmith evaluation access requires explicit opt-in.")
    if not experiment_name.startswith(f"scholarpath-week4-reviewed-upload-{GRAPH_VERSION}-"):
        raise ReviewedUploadError("Inspection requires a reviewed-cohort experiment.")
    manifest = ReviewedEvaluationManifest.model_validate(manifest.model_dump())
    snapshot = sync_reviewed_dataset(client, manifest, create_if_missing=False)
    try:
        project = client.read_project(project_name=experiment_name)
        if project.reference_dataset_id != snapshot.dataset_id:
            raise ReviewedUploadError("Experiment does not reference the reviewed dataset.")
        roots = tuple(client.list_runs(project_id=project.id, is_root=True, limit=31))
        examples = {item.id: item for item in snapshot.examples}
        ids = [run.reference_example_id for run in roots]
        if len(roots) != 30 or len(set(ids)) != 30 or set(ids) != set(examples):
            raise ReviewedUploadError(
                "Saved experiment does not contain exactly thirty reviewed roots."
            )
        feedback = _feedback_for_runs(client, [run.id for run in roots])
        scenarios = {
            example.id: case.scenario
            for example, case in zip(snapshot.examples, manifest.source_draft.cases, strict=True)
        }
        rows: list[ExperimentResultRow] = []
        for root in roots:
            assert root.reference_example_id is not None
            # Full target payloads were deliberately not traced. Never re-evaluate a
            # count-only projection: recover actual feedback, not newly inferred scores.
            metrics = _recovered_metrics(
                [item for item in feedback if item.run_id == root.id],
                scenarios[root.reference_example_id],
            )
            count = (root.outputs or {}).get("port_invocations")
            measurement = {"port_invocations": count} if type(count) is int and count >= 0 else {}
            rows.append(
                ExperimentResultRow(
                    run=root.model_copy(update={"outputs": {"measurements": measurement}}),
                    example=examples[root.reference_example_id],
                    evaluation_results={"results": metrics},
                )
            )
        return _assemble_report(
            client,
            manifest,
            snapshot,
            _SavedRows(experiment_name, project.id, project.url, tuple(rows)),
            observation_source="readback",
        )
    except ReviewedUploadError:
        raise
    except Exception as error:
        raise ReviewedUploadError(
            "Saved experiment readback failed; no targets were executed."
        ) from error


def main(argv: Sequence[str] | None = None) -> int:
    """Preview without credentials; upload only with both explicit opt-in gates."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--upload", action="store_true")
    mode.add_argument("--inspect", metavar="EXPERIMENT_NAME")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    manifest = build_reviewed_manifest()
    if not args.upload and not args.inspect:
        print(
            json.dumps(
                {**reviewed_metadata(manifest), "case_count": 30, "uploaded": False}, indent=2
            )
        )
        return 0
    try:
        settings = load_evaluation_settings()
        if not settings.run_langsmith_evals:
            raise ProviderConfigurationError("Set SCHOLARPATH_RUN_LANGSMITH_EVALS=true to opt in.")
        tracing_settings = load_langsmith_settings()
        tracing_settings.require_evaluation_api_key()
        client = create_reviewed_trace_client(tracing_settings, manifest)
        try:
            report = (
                read_reviewed_experiment(
                    client, manifest, experiment_name=args.inspect, evaluation_settings=settings
                )
                if args.inspect
                else run_reviewed_upload(client, manifest, evaluation_settings=settings)
            )
        finally:
            client.close(timeout=10)
        if args.format == "json":
            print(report.model_dump_json(indent=2))
        else:
            print(f"Experiment: {report.experiment_name}")
            print(f"Link: {report.experiment_url}")
            print(f"Checks: {report.example_count - report.failed_example_count}/30 cases passed")
            print(f"Readback complete: {report.readback_complete}")
            print(
                f"Provisional runtime budgets passed: {report.provisional_runtime_budgets_passed}"
            )
        return (0 if report.passed else 1) if report.readback_complete else 2
    except (ProviderConfigurationError, ReviewedUploadError, ValueError):
        print(
            "Reviewed upload unavailable: check opt-in, credentials, "
            "and frozen snapshot integrity.",
            file=sys.stderr,
        )
        return 2
