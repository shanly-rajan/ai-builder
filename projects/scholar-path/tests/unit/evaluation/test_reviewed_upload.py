"""Reviewed uploads preserve a frozen synthetic snapshot and explicit network authority."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator, Sequence
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, Never, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langsmith import Client, tracing_context
from langsmith.evaluation import EvaluationResult
from langsmith.schemas import Dataset, DatasetVersion, Example, ExampleCreate, Feedback, Run
from pydantic import SecretStr

from scholarpath.config import (
    Environment,
    EvaluationSettings,
    LangSmithSettings,
    ProviderConfigurationError,
)
from scholarpath.evaluation import evaluators, reviewed_upload, runner
from scholarpath.evaluation.evaluators import DETERMINISTIC_EVALUATORS
from scholarpath.evaluation.models import EvaluationTargetKind
from scholarpath.evaluation.reviewed_manifest import build_reviewed_manifest
from scholarpath.evaluation.reviewed_upload import (
    ReviewedUploadError,
    run_reviewed_upload,
    sync_reviewed_dataset,
)
from scholarpath.evaluation.runner import stable_example_id
from scholarpath.evaluation.scenarios import EVALUATION_DATASET_NAME, EVALUATION_SCENARIOS
from scholarpath.evaluation.synthetic_tracing import SyntheticEvaluationObservability
from scholarpath.observability import GRAPH_VERSION, LangSmithObservability

_AS_OF = datetime(2026, 9, 6, 16, 0, tzinfo=UTC)
_DATASET_ID = UUID("551b71b8-ea46-4d0e-8378-d0ab25bb7e20")
_OTHER_ID = UUID("b675ab8b-3f70-42e6-9882-d21b324fbe30")
_PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"
_EXPERIMENT_NAME = f"scholarpath-week4-reviewed-upload-{GRAPH_VERSION}-unit-test"


class _DatasetDouble:
    """SDK-shaped, in-memory dataset storage; no LangSmith client is instantiated."""

    def __init__(self) -> None:
        self.client = MagicMock(spec=Client)
        self.dataset: Dataset | None = None
        self.examples: tuple[Example, ...] = ()
        self.client.has_dataset.side_effect = lambda **kwargs: self.dataset is not None
        self.client.create_dataset.side_effect = self._create_dataset
        self.client.read_dataset.side_effect = self._read_dataset
        self.client.create_examples.side_effect = self._create_examples
        self.client.read_dataset_version.return_value = DatasetVersion(
            as_of=_AS_OF, tags=["latest"]
        )
        self.client.list_examples.side_effect = lambda **kwargs: iter(self.examples)

    def _create_dataset(self, name: str, **kwargs: object) -> Dataset:
        self.dataset = Dataset.model_validate(
            {
                "id": _DATASET_ID,
                "name": name,
                "created_at": _AS_OF,
                "modified_at": _AS_OF,
                "metadata": kwargs.get("metadata"),
                "description": kwargs.get("description"),
            }
        )
        return self.dataset

    def _read_dataset(self, **kwargs: object) -> Dataset:
        assert self.dataset is not None
        return self.dataset

    def _create_examples(self, *, examples: Sequence[ExampleCreate], **kwargs: object) -> None:
        self.examples = tuple(
            Example.model_validate(
                {
                    "id": example.id,
                    "dataset_id": _DATASET_ID,
                    "created_at": _AS_OF,
                    "modified_at": _AS_OF,
                    "inputs": example.inputs,
                    "outputs": example.outputs,
                    "metadata": {**(example.metadata or {}), "dataset_split": example.split},
                }
            )
            for example in examples
        )

    def populated(self) -> _DatasetDouble:
        sync_reviewed_dataset(cast(Client, self.client), build_reviewed_manifest())
        self.client.reset_mock()
        return self


class _ExperimentRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.experiment_name = _EXPERIMENT_NAME
        self.experiment_id = str(_OTHER_ID)
        self.url = None
        self.rows = rows

    def __iter__(self) -> Iterator[dict[str, object]]:
        return iter(self.rows)


def _evaluation_rows(
    target: Callable[[dict[str, Any]], dict[str, Any]],
    *,
    data: Sequence[Example],
    evaluators: Sequence[Callable[..., EvaluationResult]],
    **kwargs: object,
) -> _ExperimentRows:
    """Run the actual offline targets/checks, substituting only LangSmith transport."""
    rows: list[dict[str, object]] = []
    for index, example in enumerate(data, start=1):
        assert example.inputs is not None
        outputs = target(example.inputs)
        metrics = [
            evaluator(
                outputs=outputs,
                reference_outputs=example.outputs,
            )
            for evaluator in evaluators
        ]
        rows.append(
            {
                "example": example,
                "run": SimpleNamespace(
                    id=UUID(int=index),
                    trace_id=UUID(int=index),
                    error=None,
                    outputs=outputs,
                    start_time=_AS_OF,
                    end_time=_AS_OF + timedelta(milliseconds=100),
                ),
                "evaluation_results": {"results": metrics},
            }
        )
    return _ExperimentRows(rows)


class _ExperimentDouble(_DatasetDouble):
    """Transport readback mirrors saved synthetic rows and feedback, not asserted successes."""

    def __init__(self, mutate: Callable[[list[dict[str, Any]]], None] | None = None) -> None:
        super().__init__()
        self.mutate = mutate
        self.rows: list[dict[str, Any]] = []
        self.client.evaluate.side_effect = self._evaluate
        self.client.read_project.return_value = SimpleNamespace(
            id=_OTHER_ID,
            name=_EXPERIMENT_NAME,
            start_time=_AS_OF,
            reference_dataset_id=_DATASET_ID,
            url=None,
            metadata={
                **reviewed_upload.reviewed_metadata(build_reviewed_manifest()),
                "snapshot_as_of": _AS_OF.isoformat(),
                "dataset_version": _AS_OF.isoformat(),
            },
        )
        self.client.list_runs.side_effect = self._list_runs
        self.client.list_feedback.side_effect = self._list_feedback
        self.client.get_run_url.side_effect = lambda *, run, project_id: (
            f"https://example.test/runs/{run.id}"
        )

    def _evaluate(
        self, target: Callable[[dict[str, Any]], dict[str, Any]], **kwargs: Any
    ) -> _ExperimentRows:
        with tracing_context(enabled=False):
            result = _evaluation_rows(target, **kwargs)
        self.rows = result.rows
        if self.mutate is not None:
            self.mutate(self.rows)
        return result

    def _list_runs(self, **kwargs: Any) -> Iterator[SimpleNamespace]:
        if kwargs.get("parent_run_id") is not None:
            return iter(
                (
                    SimpleNamespace(
                        name="scholarpath_graph",
                        trace_id=kwargs["parent_run_id"],
                        parent_run_id=kwargs["parent_run_id"],
                    ),
                )
            )
        return iter(
            SimpleNamespace(**vars(row["run"]), reference_example_id=row["example"].id, url=None)
            for row in self.rows
        )

    def _list_feedback(self, **kwargs: Any) -> Iterator[SimpleNamespace]:
        return iter(
            SimpleNamespace(
                run_id=row["run"].id, key=metric.key, score=metric.score, value=metric.value
            )
            for row in self.rows
            if row["run"].id in kwargs["run_ids"]
            for metric in row["evaluation_results"]["results"]
        )


def _forbidden_call(*args: object, **kwargs: object) -> Never:
    raise AssertionError("This preview must not access configuration or an external service")


def _disabled_observability() -> LangSmithObservability:
    return LangSmithObservability(
        LangSmithSettings.model_construct(tracing=False), Environment.TEST
    )


class _PersistedExperimentDouble(_ExperimentDouble):
    """A previously completed remote experiment, with no execution during recovery."""

    def __init__(self) -> None:
        super().__init__()
        self.client.read_project.return_value.start_time = _AS_OF - timedelta(days=2)
        self.populated()
        with tracing_context(enabled=False):
            self.rows = cast(
                list[dict[str, Any]],
                _evaluation_rows(
                    runner.dispatch_evaluation_target,
                    data=self.examples,
                    evaluators=[
                        reviewed_upload._uploaded_evaluator(item)
                        for item in DETERMINISTIC_EVALUATORS
                    ],
                ).rows,
            )
        self.roots = tuple(
            Run.model_validate(
                {
                    **vars(row["run"]),
                    "name": "reviewed-evaluation-target",
                    "run_type": "chain",
                    "parent_run_id": None,
                    "reference_example_id": row["example"].id,
                    "inputs": {"withheld": True},
                    "outputs": {
                        "port_invocations": row["run"].outputs["measurements"]["port_invocations"],
                        "unexpected_private_content": _PRIVATE,
                    },
                }
            )
            for row in self.rows
        )
        self.feedback = tuple(
            Feedback.model_validate(
                {
                    "id": UUID(int=index),
                    "created_at": _AS_OF,
                    "modified_at": _AS_OF,
                    "run_id": row["run"].id,
                    "trace_id": row["run"].trace_id,
                    "key": metric.key,
                    "score": metric.score,
                    "value": metric.value,
                    "extra": metric.extra,
                }
            )
            for index, (row, metric) in enumerate(
                (
                    (row, metric)
                    for row in self.rows
                    for metric in row["evaluation_results"]["results"]
                ),
                start=1,
            )
        )
        self.client.list_runs.side_effect = self._persisted_runs
        self.client.list_feedback.side_effect = self._persisted_feedback
        self.client.reset_mock()
        for name in ("create_dataset", "create_examples", "evaluate", "flush"):
            getattr(self.client, name).side_effect = _forbidden_call

    def _persisted_runs(self, **kwargs: Any) -> Iterator[Run | SimpleNamespace]:
        if kwargs.get("parent_run_id") is not None:
            return self._list_runs(**kwargs)
        return iter(self.roots)

    def _persisted_feedback(self, **kwargs: Any) -> Iterator[Feedback]:
        return iter(item for item in self.feedback if item.run_id in kwargs["run_ids"])


def test_uploaded_run_requires_opt_in_before_any_client_operation() -> None:
    client = MagicMock(spec=Client)

    with pytest.raises(ProviderConfigurationError):
        run_reviewed_upload(
            cast(Client, client),
            build_reviewed_manifest(),
            evaluation_settings=EvaluationSettings.model_construct(run_langsmith_evals=False),
        )

    assert client.mock_calls == []


def test_new_reviewed_dataset_has_exact_frozen_examples_and_bounded_snapshot() -> None:
    double = _DatasetDouble()
    manifest = build_reviewed_manifest()

    snapshot = sync_reviewed_dataset(cast(Client, double.client), manifest)

    assert snapshot.dataset_created is True
    assert snapshot.dataset_id == _DATASET_ID
    assert snapshot.dataset_name == manifest.dataset_name
    assert snapshot.snapshot_as_of == _AS_OF
    assert snapshot.examples == double.examples
    assert len(snapshot.examples) == 30
    assert len({example.id for example in snapshot.examples}) == 30
    double.client.create_dataset.assert_called_once()
    double.client.create_examples.assert_called_once()
    assert double.dataset is not None
    metadata = double.dataset.metadata
    assert metadata is not None
    assert metadata["reviewed_version"] == manifest.reviewed_version
    assert metadata["content_digest"] == manifest.content_digest
    assert metadata["source_draft_digest"] == manifest.source_draft_digest
    assert metadata["approval_scope"] == "expected_behaviors"
    assert metadata["application"] == "scholarpath"
    assert metadata["synthetic_data"] is True
    assert metadata["runtime"] == {}
    assert "graph_version" in metadata
    for case, example in zip(manifest.source_draft.cases, snapshot.examples, strict=True):
        assert example.id == stable_example_id(manifest.dataset_name, case.scenario.scenario_id)
        assert example.inputs == {
            "scenario": case.scenario.model_dump(mode="json", exclude={"expected"})
        }
        assert example.outputs == {"expected": case.scenario.expected.model_dump(mode="json")}
        assert example.metadata is not None
        assert example.metadata["scenario_version"] == case.source_version
        assert example.metadata["evaluation_scenario_id"] == case.scenario.scenario_id
        assert example.metadata["evaluation_target"] == case.scenario.target.value
        assert example.metadata["content_digest"] == manifest.content_digest
        assert example.metadata["dataset_split"] == list(case.scenario.splits)
        assert "reviewer" not in example.metadata
        assert "exact_user_response" not in example.metadata
    version_request = double.client.read_dataset_version.call_args.kwargs
    assert version_request["tag"] == "latest"
    query = double.client.list_examples.call_args.kwargs
    assert query["as_of"] == _AS_OF
    assert query["limit"] == 31
    assert query["include_attachments"] is False
    assert (
        query.get("dataset_id") == _DATASET_ID or query.get("dataset_name") == manifest.dataset_name
    )


def test_exact_existing_dataset_is_read_only_and_ordered_to_manifest() -> None:
    double = _DatasetDouble().populated()
    expected_ids = tuple(item.id for item in double.examples)
    double.examples = tuple(reversed(double.examples))

    snapshot = sync_reviewed_dataset(cast(Client, double.client), build_reviewed_manifest())

    assert snapshot.dataset_created is False
    assert tuple(item.id for item in snapshot.examples) == expected_ids
    double.client.create_dataset.assert_not_called()
    double.client.create_examples.assert_not_called()
    double.client.update_dataset_tag.assert_not_called()
    double.client.update_example.assert_not_called()
    double.client.delete_dataset.assert_not_called()


@pytest.mark.parametrize(
    "drift",
    [
        "missing",
        "extra",
        "duplicate_id",
        "wrong_id",
        "wrong_dataset",
        "inputs",
        "outputs",
        "example_metadata",
        "dataset_metadata",
        "missing_modified_at",
    ],
)
def test_existing_snapshot_drift_fails_without_overwriting_anything(drift: str) -> None:
    double = _DatasetDouble().populated()
    first = double.examples[0]
    if drift == "missing":
        double.examples = double.examples[:-1]
    elif drift == "extra":
        double.examples = (*double.examples, first.model_copy(update={"id": _OTHER_ID}))
    elif drift == "duplicate_id":
        double.examples = (first, first, *double.examples[2:])
    elif drift == "dataset_metadata":
        assert double.dataset is not None
        double.dataset = double.dataset.model_copy(
            update={"metadata": {"content_digest": _PRIVATE}}
        )
    else:
        mutations: dict[str, dict[str, object]] = {
            "wrong_id": {"id": _OTHER_ID},
            "wrong_dataset": {"dataset_id": _OTHER_ID},
            "inputs": {"inputs": {"scenario": _PRIVATE}},
            "outputs": {"outputs": {"expected": _PRIVATE}},
            "example_metadata": {"metadata": {"content_digest": _PRIVATE}},
            "missing_modified_at": {"modified_at": None},
        }
        double.examples = (first.model_copy(update=mutations[drift]), *double.examples[1:])

    with pytest.raises(ReviewedUploadError) as raised:
        sync_reviewed_dataset(cast(Client, double.client), build_reviewed_manifest())

    assert _PRIVATE not in str(raised.value)
    double.client.create_dataset.assert_not_called()
    double.client.create_examples.assert_not_called()
    double.client.update_dataset_tag.assert_not_called()
    double.client.update_example.assert_not_called()
    double.client.delete_dataset.assert_not_called()


def test_tampered_local_manifest_is_rejected_before_network_access() -> None:
    client = MagicMock(spec=Client)
    corrupted = build_reviewed_manifest().model_copy(update={"dataset_name": "unapproved-dataset"})

    with pytest.raises((ValueError, ReviewedUploadError)):
        sync_reviewed_dataset(cast(Client, client), corrupted)

    assert client.mock_calls == []


@pytest.mark.parametrize("argv", [[], ["--format", "json"]])
def test_cli_preview_does_not_load_keys_or_construct_clients(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    for name in (
        "load_evaluation_settings",
        "load_langsmith_settings",
        "create_reviewed_trace_client",
    ):
        monkeypatch.setattr(reviewed_upload, name, _forbidden_call)

    assert reviewed_upload.main(argv) == 0

    captured = capsys.readouterr()
    assert build_reviewed_manifest().dataset_name in captured.out
    assert captured.err == ""
    if argv:
        assert isinstance(json.loads(captured.out), dict)


@pytest.mark.parametrize("argv", [["--live"], ["--include-llm-judges"], ["--target", "graph_live"]])
def test_cli_refuses_scope_expansion(argv: list[str], monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reviewed_upload, "load_evaluation_settings", _forbidden_call)

    with pytest.raises(SystemExit) as raised:
        reviewed_upload.main(argv)

    assert raised.value.code == 2


def test_cli_upload_requires_environment_gate_before_credentials(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        reviewed_upload,
        "load_evaluation_settings",
        lambda: EvaluationSettings.model_construct(run_langsmith_evals=False),
    )
    monkeypatch.setattr(reviewed_upload, "load_langsmith_settings", _forbidden_call)
    monkeypatch.setattr(reviewed_upload, "create_reviewed_trace_client", _forbidden_call)

    assert reviewed_upload.main(["--upload"]) == 2

    assert capsys.readouterr().err


def test_reviewed_upload_executes_only_fakes_and_truthfully_reports_known_gaps(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for flag in (
        "SCHOLARPATH_RUN_LIVE_TESTS",
        "SCHOLARPATH_RUN_LIVE_E2E_EVALS",
        "SCHOLARPATH_RUN_LIVE_CANARY",
    ):
        monkeypatch.setenv(flag, "true")
    for name in (
        "live_end_to_end_target",
        "OpenAIEvaluationJudgeAdapter",
        "build_openai_judge_evaluators",
        "create_langsmith_evaluation_client",
    ):
        monkeypatch.setattr(runner, name, _forbidden_call)
    manifest = build_reviewed_manifest()
    manifest_before = manifest.model_dump_json()
    original_scenarios = tuple(item.model_dump_json() for item in EVALUATION_SCENARIOS)
    double = _ExperimentDouble()
    monkeypatch.setattr(
        reviewed_upload,
        "SyntheticEvaluationObservability",
        _disabled_observability,
    )

    report = run_reviewed_upload(
        cast(Client, double.client),
        manifest,
        evaluation_settings=EvaluationSettings.model_construct(
            run_langsmith_evals=True,
            run_live_e2e_evals=True,
            evaluation_dataset_name="unapproved-environment-dataset",
        ),
    )

    assert report.example_count == 30
    assert report.failed_example_count == 0
    assert report.passed is True
    assert report.failures == ()
    assert report.dataset_name == manifest.dataset_name
    assert str(report.dataset_name) != EVALUATION_DATASET_NAME
    assert report.reviewed_version == manifest.reviewed_version
    assert report.content_digest == manifest.content_digest
    assert report.source_draft_digest == manifest.source_draft_digest
    assert report.approval_scope == "expected_behaviors"
    assert report.execution_mode == "fake_only"
    assert len(report.runtime_cases) == len(report.run_references) == 30
    graph_runtime = next(item for item in report.runtime_summaries if item.target == "graph_fake")
    assert graph_runtime.maximum_port_invocations == 76
    assert graph_runtime.invocation_budget == 40
    assert graph_runtime.invocation_budget_passed is False
    assert report.provisional_runtime_budgets_passed is False
    assert report.readback_complete is True
    assert len(report.cases) == 30
    assert all(item.persisted and item.feedback_persisted for item in report.cases)
    assert all(len(item.metrics) == 11 for item in report.cases)
    assert all(item.graph_child_visible is not False for item in report.cases)
    assert manifest.model_dump_json() == manifest_before
    assert tuple(item.model_dump_json() for item in EVALUATION_SCENARIOS) == original_scenarios
    call = double.client.evaluate.call_args
    assert tuple(call.kwargs["data"]) == double.examples
    assert (
        tuple(getattr(item, "__wrapped__", item) for item in call.kwargs["evaluators"])
        == DETERMINISTIC_EVALUATORS
    )
    assert call.kwargs["num_repetitions"] == 1
    assert call.kwargs["max_concurrency"] == 0
    assert call.kwargs["blocking"] is True
    assert call.kwargs["upload_results"] is True
    assert call.kwargs["metadata"]["content_digest"] == manifest.content_digest
    assert "reviewed" in call.kwargs["experiment_prefix"]
    double.client.flush.assert_called_once_with(timeout=10)
    serialized = report.model_dump_json()
    for forbidden in (
        "candidate_id",
        "proposed_research_statement",
        "supporting_excerpt",
        "api_key",
    ):
        assert f'"{forbidden}"' not in serialized
        assert f'"{forbidden}"' not in json.dumps(call.kwargs["metadata"])
    assert type(report).model_validate_json(serialized) == report


def test_cli_missing_key_stops_before_client_construction(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        reviewed_upload,
        "load_evaluation_settings",
        lambda: EvaluationSettings.model_construct(run_langsmith_evals=True),
    )
    monkeypatch.setattr(
        reviewed_upload,
        "load_langsmith_settings",
        lambda: LangSmithSettings.model_construct(api_key=None),
    )
    # The real factory validates the key before constructing its underlying client.
    monkeypatch.setattr(
        "scholarpath.evaluation.reviewed_tracing._ReviewedTraceClient", _forbidden_call
    )

    assert reviewed_upload.main(["--upload"]) == 2

    assert capsys.readouterr().err


def test_cli_provider_failure_is_sanitized_and_client_is_closed(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    client = MagicMock(spec=Client)
    monkeypatch.setattr(
        reviewed_upload,
        "load_evaluation_settings",
        lambda: EvaluationSettings.model_construct(run_langsmith_evals=True),
    )
    monkeypatch.setattr(
        reviewed_upload,
        "load_langsmith_settings",
        lambda: LangSmithSettings.model_construct(api_key=SecretStr(_PRIVATE)),
    )
    client.has_dataset.side_effect = RuntimeError(_PRIVATE)
    monkeypatch.setattr(
        reviewed_upload, "create_reviewed_trace_client", lambda settings, manifest: client
    )

    assert reviewed_upload.main(["--upload", "--format", "json"]) == 2

    output = capsys.readouterr()
    assert _PRIVATE not in output.out + output.err
    assert "Traceback" not in output.err
    assert output.err
    client.close.assert_called_once()


def test_incomplete_readback_is_bounded_without_reexecuting_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = MagicMock(spec=Client)
    client.list_runs.return_value = ()
    client.list_feedback.return_value = ()
    sleep = MagicMock()
    monkeypatch.setattr(reviewed_upload, "sleep", sleep)

    roots, feedback = reviewed_upload._readback(cast(Client, client), _DATASET_ID, [_OTHER_ID])

    assert roots == {}
    assert feedback == {}
    assert client.list_runs.call_count == client.list_feedback.call_count == 3
    assert sleep.call_count == 2
    client.list_runs.assert_called_with(project_id=_DATASET_ID, run_ids=[_OTHER_ID], limit=31)
    feedback_query = client.list_feedback.call_args.kwargs
    assert feedback_query["run_ids"] == [_OTHER_ID]
    assert feedback_query["feedback_key"] == sorted(
        item.__name__ for item in DETERMINISTIC_EVALUATORS
    )
    assert feedback_query["limit"] <= 89
    client.evaluate.assert_not_called()
    client.create_examples.assert_not_called()


def test_duplicate_readback_feedback_fails_without_overwriting_or_rerunning() -> None:
    client = MagicMock(spec=Client)
    client.list_runs.return_value = ()
    feedback = SimpleNamespace(run_id=_OTHER_ID, key="schema_validity", score=True, value=None)
    client.list_feedback.return_value = (feedback, feedback)

    with pytest.raises(ReviewedUploadError, match="Duplicate deterministic feedback"):
        reviewed_upload._readback(cast(Client, client), _DATASET_ID, [_OTHER_ID])

    client.list_feedback.assert_called_once()
    client.evaluate.assert_not_called()
    client.create_feedback.assert_not_called()
    client.update_feedback.assert_not_called()


@pytest.mark.parametrize("timeout", [0, -1, 31, float("inf"), float("nan")])
def test_invalid_flush_limit_stops_before_network_access(timeout: float) -> None:
    client = MagicMock(spec=Client)

    with pytest.raises(ValueError):
        run_reviewed_upload(
            cast(Client, client),
            build_reviewed_manifest(),
            evaluation_settings=EvaluationSettings.model_construct(run_langsmith_evals=True),
            flush_timeout_seconds=timeout,
        )

    assert client.mock_calls == []


def test_remote_input_cannot_change_frozen_target_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reviewed_upload, "dispatch_evaluation_target", _forbidden_call)
    monkeypatch.setattr(reviewed_upload, "fake_end_to_end_target", _forbidden_call)

    with pytest.raises(ReviewedUploadError) as raised:
        reviewed_upload._target(build_reviewed_manifest(), {"scenario": _PRIVATE})

    assert _PRIVATE not in str(raised.value)


def test_graph_target_receives_synthetic_observability_without_enabling_live_tools(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manifest = build_reviewed_manifest()
    scenario = next(
        case.scenario
        for case in manifest.source_draft.cases
        if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
    )
    inputs: dict[str, object] = {"scenario": scenario.model_dump(mode="json", exclude={"expected"})}
    seen: list[dict[str, object]] = []

    def fake_graph(
        data: dict[str, object], *, observability: LangSmithObservability | None = None
    ) -> dict[str, object]:
        assert isinstance(observability, SyntheticEvaluationObservability)
        seen.append(data)
        return {"synthetic_test": True}

    monkeypatch.setattr(reviewed_upload, "fake_end_to_end_target", fake_graph)
    monkeypatch.setattr(reviewed_upload, "dispatch_evaluation_target", _forbidden_call)

    assert reviewed_upload._target(manifest, inputs) == {"synthetic_test": True}
    assert seen == [inputs]


@pytest.mark.parametrize(
    ("output_format", "complete", "inject_failure", "exit_code"),
    [
        ("text", True, False, 0),
        ("json", True, False, 0),
        ("text", True, True, 1),
        ("json", True, True, 1),
        ("json", False, False, 2),
    ],
)
def test_cli_distinguishes_current_success_injected_failure_and_incomplete_readback(
    output_format: str,
    complete: bool,
    inject_failure: bool,
    exit_code: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_one_metric(rows: list[dict[str, Any]]) -> None:
        # Deliberate transport-double fault, not a change to any frozen expected label.
        for row in rows:
            if row["example"].inputs["scenario"]["scenario_id"] == (
                "draft-evidence-heading-bound-research"
            ):
                row["evaluation_results"]["results"] = [
                    EvaluationResult(key=metric.key, score=False)
                    if metric.key == "expected_behavior"
                    else metric
                    for metric in row["evaluation_results"]["results"]
                ]

    double = _ExperimentDouble(mutate=fail_one_metric if inject_failure else None)
    settings = EvaluationSettings.model_construct(run_langsmith_evals=True)
    monkeypatch.setattr(
        reviewed_upload, "SyntheticEvaluationObservability", _disabled_observability
    )
    report = run_reviewed_upload(
        cast(Client, double.client), build_reviewed_manifest(), evaluation_settings=settings
    ).model_copy(update={"readback_complete": complete})
    monkeypatch.setattr(reviewed_upload, "load_evaluation_settings", lambda: settings)
    monkeypatch.setattr(
        reviewed_upload,
        "load_langsmith_settings",
        lambda: LangSmithSettings.model_construct(api_key=SecretStr("synthetic-test-key")),
    )
    monkeypatch.setattr(
        reviewed_upload,
        "create_reviewed_trace_client",
        lambda settings, manifest: double.client,
    )
    monkeypatch.setattr(reviewed_upload, "run_reviewed_upload", lambda *args, **kwargs: report)

    assert reviewed_upload.main(["--upload", "--format", output_format]) == exit_code

    captured = capsys.readouterr()
    assert captured.err == ""
    if output_format == "json":
        output = json.loads(captured.out)
        assert output["example_count"] == 30
        assert output["failed_example_count"] == int(inject_failure)
        assert output["readback_complete"] is complete
        assert output["execution_mode"] == "fake_only"
    else:
        passed_count = 29 if inject_failure else 30
        assert f"{passed_count}/30" in captured.out
    assert "synthetic-test-key" not in captured.out
    double.client.close.assert_called_once()


def test_sdk_evaluator_error_is_failure_not_not_applicable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def evaluator_failed(rows: list[dict[str, Any]]) -> None:
        rows[0]["evaluation_results"]["results"] = [
            EvaluationResult(key=metric.key, score=None, extra={"error": True}, comment=_PRIVATE)
            if metric.key == "schema_validity"
            else metric
            for metric in rows[0]["evaluation_results"]["results"]
        ]

    double = _ExperimentDouble(mutate=evaluator_failed)
    monkeypatch.setattr(
        reviewed_upload, "SyntheticEvaluationObservability", _disabled_observability
    )

    report = run_reviewed_upload(
        cast(Client, double.client),
        build_reviewed_manifest(),
        evaluation_settings=EvaluationSettings.model_construct(run_langsmith_evals=True),
    )

    assert report.failed_example_count == 1
    assert any(
        item.key == "schema_validity" and item.category == "evaluator_error"
        for item in report.failures
    )
    assert _PRIVATE not in report.model_dump_json()
    double.client.evaluate.assert_called_once()


def test_recovery_inspects_existing_records_without_targets_or_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    double = _PersistedExperimentDouble()
    manifest = build_reviewed_manifest()
    for name in ("dispatch_evaluation_target", "fake_end_to_end_target", "_target"):
        monkeypatch.setattr(reviewed_upload, name, _forbidden_call)

    report = reviewed_upload.read_reviewed_experiment(
        cast(Client, double.client),
        manifest,
        experiment_name=_EXPERIMENT_NAME,
        evaluation_settings=EvaluationSettings.model_construct(run_langsmith_evals=True),
    )

    assert report.observation_source == "readback"
    assert report.dataset_created is False
    assert report.recorded_on == (_AS_OF - timedelta(days=2)).date()
    assert report.example_count == len(report.cases) == 30
    assert report.failed_example_count == 0
    assert report.readback_complete is True
    assert report.provisional_runtime_budgets_passed is False
    assert report.failures == ()
    graph = next(item for item in report.runtime_summaries if item.target == "graph_fake")
    assert graph.maximum_port_invocations == 76
    assert graph.invocation_budget == 40
    assert all(item.feedback_persisted and item.persisted for item in report.cases)
    assert all(item.graph_child_visible is not False for item in report.cases)
    assert report.content_digest == manifest.content_digest
    assert _PRIVATE not in report.model_dump_json()
    double.client.create_dataset.assert_not_called()
    double.client.create_examples.assert_not_called()
    double.client.evaluate.assert_not_called()
    double.client.flush.assert_not_called()
    double.client.update_examples.assert_not_called()
    for request in double.client.list_feedback.call_args_list:
        assert len(request.kwargs["run_ids"]) <= 8
        assert request.kwargs["limit"] <= 89


@pytest.mark.parametrize("drift", ["dataset_missing", "project_metadata", "example_content"])
def test_recovery_rejects_drift_without_recreating_or_reexecuting(drift: str) -> None:
    double = _PersistedExperimentDouble()
    if drift == "dataset_missing":
        double.dataset = None
    elif drift == "project_metadata":
        double.client.read_project.return_value.metadata["content_digest"] = _PRIVATE
    else:
        double.examples = (
            double.examples[0].model_copy(update={"outputs": {"expected": _PRIVATE}}),
            *double.examples[1:],
        )

    with pytest.raises(ReviewedUploadError) as raised:
        reviewed_upload.read_reviewed_experiment(
            cast(Client, double.client),
            build_reviewed_manifest(),
            experiment_name=_EXPERIMENT_NAME,
            evaluation_settings=EvaluationSettings.model_construct(run_langsmith_evals=True),
        )

    assert _PRIVATE not in str(raised.value)
    double.client.create_dataset.assert_not_called()
    double.client.create_examples.assert_not_called()
    double.client.evaluate.assert_not_called()
    double.client.update_examples.assert_not_called()


def test_recovery_requires_opt_in_before_reading_remote_state() -> None:
    client = MagicMock(spec=Client)

    with pytest.raises(ProviderConfigurationError):
        reviewed_upload.read_reviewed_experiment(
            cast(Client, client),
            build_reviewed_manifest(),
            experiment_name=_EXPERIMENT_NAME,
            evaluation_settings=EvaluationSettings.model_construct(run_langsmith_evals=False),
        )

    assert client.mock_calls == []


def test_cli_inspect_recovers_existing_report_without_upload(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    double = _PersistedExperimentDouble()
    monkeypatch.setattr(
        reviewed_upload,
        "load_evaluation_settings",
        lambda: EvaluationSettings.model_construct(run_langsmith_evals=True),
    )
    monkeypatch.setattr(
        reviewed_upload,
        "load_langsmith_settings",
        lambda: LangSmithSettings.model_construct(api_key=SecretStr("synthetic-test-key")),
    )
    monkeypatch.setattr(
        reviewed_upload,
        "create_reviewed_trace_client",
        lambda settings, manifest: double.client,
    )
    monkeypatch.setattr(reviewed_upload, "run_reviewed_upload", _forbidden_call)

    assert reviewed_upload.main(["--inspect", _EXPERIMENT_NAME, "--format", "json"]) == 0

    captured = capsys.readouterr()
    assert captured.err == ""
    output = json.loads(captured.out)
    assert output["observation_source"] == "readback"
    assert output["example_count"] == 30
    assert output["failed_example_count"] == 0
    assert output["dataset_created"] is False
    assert _PRIVATE not in captured.out
    double.client.close.assert_called_once()
    double.client.evaluate.assert_not_called()


def test_cli_inspect_and_upload_are_mutually_exclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(reviewed_upload, "load_evaluation_settings", _forbidden_call)

    with pytest.raises(SystemExit) as raised:
        reviewed_upload.main(["--upload", "--inspect", "existing-experiment"])

    assert raised.value.code == 2


def test_feedback_readback_batches_stay_below_sdk_pagination_boundary() -> None:
    client = MagicMock(spec=Client)
    run_ids = [UUID(int=index) for index in range(1, 31)]
    keys = sorted(item.__name__ for item in DETERMINISTIC_EVALUATORS)

    def one_page(
        *, run_ids: Sequence[UUID], feedback_key: Sequence[str], limit: int
    ) -> Iterator[SimpleNamespace]:
        assert len(run_ids) <= 8
        assert limit == len(run_ids) * len(keys) + 1
        assert limit < 100
        assert list(feedback_key) == keys
        return iter(
            SimpleNamespace(run_id=run_id, key=key, score=True, value=None, extra={})
            for run_id in run_ids
            for key in feedback_key
        )

    client.list_feedback.side_effect = one_page

    feedback = reviewed_upload._feedback_for_runs(cast(Client, client), run_ids)

    assert len(feedback) == 330
    assert len({(item.run_id, item.key) for item in feedback}) == 330
    batches = [call.kwargs["run_ids"] for call in client.list_feedback.call_args_list]
    assert [len(batch) for batch in batches] == [8, 8, 8, 6]
    assert [run_id for batch in batches for run_id in batch] == run_ids
    client.evaluate.assert_not_called()


def _stored_feedback(
    key: str,
    score: float | None,
    *,
    extra: dict[str, object] | None = None,
    source_metadata: dict[str, object] | None = None,
) -> Feedback:
    return Feedback.model_validate(
        {
            "id": _OTHER_ID,
            "created_at": _AS_OF,
            "modified_at": _AS_OF,
            "run_id": _DATASET_ID,
            "trace_id": _DATASET_ID,
            "key": key,
            "score": score,
            "extra": extra,
            "feedback_source": {"type": "model", "metadata": source_metadata}
            if source_metadata is not None
            else None,
        }
    )


@pytest.mark.parametrize(
    ("expected_score", "rate", "source"),
    [
        (1.0, 0.0, "graph_expected_behavior"),
        (0.0, 0.0, "unavailable"),
        (None, 0.0, "unavailable"),
        (1.0, 0.5, "unavailable"),
        (1.0, -0.1, "unavailable"),
    ],
)
def test_zero_duplicate_rate_requires_proven_graph_gate_semantics(
    expected_score: float | None, rate: float, source: str
) -> None:
    scenario = next(
        case.scenario
        for case in build_reviewed_manifest().source_draft.cases
        if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
    )
    records = [_stored_feedback("duplicate_supervisor_rate", rate)]
    if expected_score is not None:
        records.append(_stored_feedback("expected_behavior", expected_score))

    restored = reviewed_upload._recovered_metrics(records, scenario)[0]

    assert restored.score == rate
    assert restored.extra is not None
    assert restored.extra["reviewed_semantics_source"] == source
    assert restored.metadata is not None
    if source == "graph_expected_behavior":
        assert restored.metadata["threshold_passed"] is True
        assert restored.metadata["threshold"] == scenario.expected.maximum_duplicate_supervisor_rate
        assert restored.metadata["lower_is_better"] is True
    else:
        assert restored.metadata.get("threshold_passed") is not True
        assert restored.metadata["error"] is True


@pytest.mark.parametrize("location", ["extra", "feedback_source"])
def test_persisted_rate_interpretation_does_not_need_an_indirect_graph_inference(
    location: str,
) -> None:
    scenario = next(
        case.scenario
        for case in build_reviewed_manifest().source_draft.cases
        if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
    )
    interpretation: dict[str, object] = {
        "lower_is_better": True,
        "threshold": scenario.expected.maximum_duplicate_supervisor_rate,
        "threshold_passed": False,
    }
    record = _stored_feedback(
        "duplicate_supervisor_rate",
        0.0,
        extra=interpretation if location == "extra" else None,
        source_metadata=interpretation if location == "feedback_source" else None,
    )

    metric = reviewed_upload._recovered_metrics(
        [record, _stored_feedback("expected_behavior", 1.0)], scenario
    )[0]

    assert metric.metadata == interpretation
    assert metric.extra is not None
    assert metric.extra["reviewed_semantics_source"] == "feedback_metadata"
    assert metric.metadata["threshold_passed"] is False


def test_non_graph_expected_behavior_cannot_prove_duplicate_semantics() -> None:
    scenario = next(
        case.scenario
        for case in build_reviewed_manifest().source_draft.cases
        if case.scenario.target is not EvaluationTargetKind.GRAPH_FAKE
    )

    metric = reviewed_upload._recovered_metrics(
        [
            _stored_feedback("duplicate_supervisor_rate", 0.0),
            _stored_feedback("expected_behavior", 1.0),
        ],
        scenario,
    )[0]

    assert metric.extra is not None
    assert metric.extra["reviewed_semantics_source"] == "unavailable"
    assert metric.metadata == {"error": True}


def test_graph_expected_behavior_really_requires_duplicate_and_provenance_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    scenario = next(
        case.scenario
        for case in build_reviewed_manifest().source_draft.cases
        if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
    )
    inputs: dict[str, object] = {"scenario": scenario.model_dump(mode="json", exclude={"expected"})}
    with tracing_context(enabled=False):
        outputs = runner.dispatch_evaluation_target(inputs)
    reference: dict[str, object] = {"expected": scenario.expected.model_dump(mode="json")}
    assert evaluators.expected_behavior(outputs, reference).score is True
    wrapped = reviewed_upload._uploaded_evaluator(evaluators.duplicate_supervisor_rate)
    result = wrapped(outputs, reference)
    assert result.metadata is not None
    assert result.extra == result.metadata
    assert result.evaluator_info == result.metadata
    failed_subgate = MagicMock(
        return_value=EvaluationResult(
            key="duplicate_supervisor_rate",
            score=0.0,
            metadata={"lower_is_better": True, "threshold_passed": False},
        )
    )
    monkeypatch.setattr(evaluators, "duplicate_supervisor_rate", failed_subgate)

    assert evaluators.expected_behavior(outputs, reference).score is False
    failed_subgate.assert_called_once()


@pytest.mark.parametrize("expected_behavior_passed", [True, False])
def test_recovery_does_not_silently_pass_zero_rate_when_semantics_are_missing(
    expected_behavior_passed: bool,
) -> None:
    double = _PersistedExperimentDouble()
    manifest = build_reviewed_manifest()
    graph_example = next(
        example
        for example, case in zip(double.examples, manifest.source_draft.cases, strict=True)
        if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
    )
    graph_run_id = next(
        root.id for root in double.roots if root.reference_example_id == graph_example.id
    )
    double.feedback = tuple(
        item.model_copy(
            update={
                "extra": None,
                "feedback_source": None,
                **(
                    {"score": 0.0}
                    if not expected_behavior_passed
                    and item.run_id == graph_run_id
                    and item.key == "expected_behavior"
                    else {}
                ),
            }
        )
        for item in double.feedback
    )

    report = reviewed_upload.read_reviewed_experiment(
        cast(Client, double.client),
        manifest,
        experiment_name=_EXPERIMENT_NAME,
        evaluation_settings=EvaluationSettings.model_construct(run_langsmith_evals=True),
    )

    case = next(item for item in report.cases if item.example_id == graph_example.id)
    assert case.duplicate_rate_semantics_source == (
        "graph_expected_behavior" if expected_behavior_passed else "unavailable"
    )
    assert report.readback_complete is expected_behavior_passed
    assert report.failed_example_count == (0 if expected_behavior_passed else 1)
    if not expected_behavior_passed:
        assert any(
            item.scenario_id == case.scenario_id and item.key == "duplicate_supervisor_rate"
            for item in report.failures
        )
    double.client.evaluate.assert_not_called()
    double.client.create_examples.assert_not_called()
