"""Offline and explicitly gated execution tests for the M12 evaluation runner."""

from __future__ import annotations

import runpy
from collections.abc import Callable, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from langsmith import Client
from langsmith.evaluation import EvaluationResult
from langsmith.utils import LangSmithError, LangSmithRetry
from pydantic import HttpUrl, SecretStr

from scholarpath.config import (
    EvaluationSettings,
    LangSmithSettings,
    ProviderConfigurationError,
)
from scholarpath.evaluation import (
    DETERMINISTIC_EVALUATORS,
    EVALUATION_SCENARIOS,
    EvaluationTargetKind,
    UploadedExperimentReport,
    create_langsmith_evaluation_client,
    evaluation_example,
    run_local_baseline,
    run_uploaded_experiment,
    stable_example_id,
    sync_evaluation_dataset,
)

PROJECT_ROOT = Path(__file__).resolve().parents[3]
type ScriptMain = Callable[[Sequence[str] | None], int]


def _script_namespace(relative_path: str) -> dict[str, Any]:
    return runpy.run_path(str(PROJECT_ROOT / relative_path))


def _script_main(namespace: dict[str, Any]) -> ScriptMain:
    return cast(ScriptMain, namespace["main"])


def _set_script_global(main: ScriptMain, name: str, value: object) -> None:
    globals_dict = cast(dict[str, Any], cast(Any, main).__globals__)
    globals_dict[name] = value


def test_local_baseline_passes_all_curated_scenarios_without_a_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_if_client_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("The offline baseline must not construct a LangSmith client")

    monkeypatch.setattr("scholarpath.evaluation.runner.Client", fail_if_client_is_constructed)

    report = run_local_baseline()

    assert report.passed
    assert report.scenario_count == 11
    assert report.passed_scenario_count == 11
    assert all(
        summary.passed_count == summary.applicable_count for summary in report.metric_summaries
    )


def test_evaluation_client_uses_explicit_timeout_and_finite_retries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    client = MagicMock(spec=Client)

    def construct_client(**kwargs: object) -> Client:
        captured.update(kwargs)
        return cast(Client, client)

    monkeypatch.setattr("scholarpath.evaluation.runner.Client", construct_client)
    settings = LangSmithSettings(
        api_key=SecretStr("not-a-real-langsmith-secret"),
        endpoint=HttpUrl("https://eu.api.smith.langchain.com"),
        workspace_id="workspace-test-001",
        request_timeout_seconds=8.25,
        maximum_retry_count=2,
    )

    assert create_langsmith_evaluation_client(settings) is client
    assert captured["timeout_ms"] == 8_250
    retry_config = captured["retry_config"]
    assert isinstance(retry_config, LangSmithRetry)
    assert retry_config.total == 2
    assert retry_config.redirect == 0
    assert captured["hide_inputs"] is True
    assert captured["hide_outputs"] is True


def test_local_baseline_can_select_one_target_family() -> None:
    report = run_local_baseline(target=EvaluationTargetKind.RESEARCH_FIT)

    assert report.scenario_count == 2
    assert report.passed
    assert {record.target for record in report.scenarios} == {EvaluationTargetKind.RESEARCH_FIT}


def test_local_baseline_refuses_live_target() -> None:
    with pytest.raises(ValueError, match="offline baseline"):
        run_local_baseline(target=EvaluationTargetKind.GRAPH_LIVE)


def test_example_identifiers_are_stable_and_dataset_scoped() -> None:
    scenario_id = EVALUATION_SCENARIOS[0].scenario_id

    assert stable_example_id("dataset-a", scenario_id) == stable_example_id(
        "dataset-a", scenario_id
    )
    assert stable_example_id("dataset-a", scenario_id) != stable_example_id(
        "dataset-b", scenario_id
    )


def test_dataset_example_contains_only_synthetic_bounded_metadata() -> None:
    scenario = EVALUATION_SCENARIOS[0]

    example = evaluation_example(scenario, "dataset-a")

    assert example.inputs == {"scenario": scenario.model_dump(mode="json", exclude={"expected"})}
    assert example.outputs == {"expected": scenario.expected.model_dump(mode="json")}
    assert example.metadata is not None
    assert example.metadata["synthetic_data"] is True
    assert "candidate_id" not in example.metadata
    assert "research_statement" not in example.metadata
    assert example.split == list(scenario.splits)


def test_dataset_sync_is_idempotent_and_upserts_stable_examples() -> None:
    client = MagicMock(spec=Client)
    client.has_dataset.return_value = False

    result = sync_evaluation_dataset(cast(Client, client), dataset_name="dataset-a")

    assert result.dataset_created
    assert result.example_count == 11
    client.create_dataset.assert_called_once()
    call = client.create_examples.call_args
    assert call.kwargs["dataset_name"] == "dataset-a"
    examples = call.kwargs["examples"]
    assert len(examples) == 11
    assert len({example.id for example in examples}) == 11


def test_existing_dataset_is_updated_without_recreation() -> None:
    client = MagicMock(spec=Client)
    client.has_dataset.return_value = True

    result = sync_evaluation_dataset(cast(Client, client), dataset_name="dataset-a")

    assert not result.dataset_created
    client.create_dataset.assert_not_called()
    client.create_examples.assert_called_once()


def test_uploaded_experiment_requires_explicit_evaluation_opt_in() -> None:
    client = MagicMock(spec=Client)

    with pytest.raises(ProviderConfigurationError, match="evaluation upload is disabled"):
        run_uploaded_experiment(
            cast(Client, client),
            evaluation_settings=EvaluationSettings(run_langsmith_evals=False),
        )

    client.list_examples.assert_not_called()
    client.evaluate.assert_not_called()


def test_live_experiment_requires_separate_live_opt_in() -> None:
    client = MagicMock(spec=Client)

    with pytest.raises(ProviderConfigurationError, match="Live end-to-end evaluation"):
        run_uploaded_experiment(
            cast(Client, client),
            evaluation_settings=EvaluationSettings(
                run_langsmith_evals=True,
                run_live_e2e_evals=False,
            ),
            live=True,
        )

    client.list_examples.assert_not_called()
    client.evaluate.assert_not_called()


def _hard_gate_results(*, failing_key: str | None = None) -> list[EvaluationResult]:
    results: list[EvaluationResult] = []
    for evaluator in DETERMINISTIC_EVALUATORS:
        key = evaluator.__name__
        if key == "duplicate_supervisor_rate":
            results.append(
                EvaluationResult(
                    key=key,
                    score=0.0,
                    metadata={
                        "lower_is_better": True,
                        "threshold_passed": failing_key != key,
                    },
                )
            )
        else:
            results.append(EvaluationResult(key=key, score=key != failing_key))
    return results


class _ExperimentRows:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.experiment_name = "m12-test-experiment"
        self._rows = rows

    def __iter__(self) -> object:
        return iter(self._rows)


def test_uploaded_experiment_reports_deterministic_gate_failures_truthfully() -> None:
    scenario = next(
        item for item in EVALUATION_SCENARIOS if item.target is EvaluationTargetKind.RESEARCH_FIT
    )
    example = MagicMock()
    example.inputs = {"scenario": scenario.model_dump(mode="json", exclude={"expected"})}
    client = MagicMock(spec=Client)
    client.list_examples.return_value = (example,)
    client.evaluate.return_value = _ExperimentRows(
        [
            {
                "run": SimpleNamespace(error=None),
                "evaluation_results": {
                    "results": _hard_gate_results(failing_key="schema_validity")
                },
            }
        ]
    )

    report = run_uploaded_experiment(
        cast(Client, client),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
        target=EvaluationTargetKind.RESEARCH_FIT,
    )

    assert report == UploadedExperimentReport(
        experiment_name="m12-test-experiment",
        example_count=1,
        failed_example_count=1,
    )
    assert not report.passed
    call = client.evaluate.call_args
    assert call.kwargs["upload_results"] is True
    assert call.kwargs["error_handling"] == "log"
    assert "candidate_id" not in str(call.kwargs["metadata"])


def test_uploaded_experiment_passes_only_with_complete_hard_gate_results() -> None:
    scenario = next(
        item for item in EVALUATION_SCENARIOS if item.target is EvaluationTargetKind.SEARCH_PLANNING
    )
    example = MagicMock()
    example.inputs = {"scenario": scenario.model_dump(mode="json", exclude={"expected"})}
    client = MagicMock(spec=Client)
    client.list_examples.return_value = (example,)
    client.evaluate.return_value = _ExperimentRows(
        [
            {
                "run": SimpleNamespace(error=None),
                "evaluation_results": {"results": _hard_gate_results()},
            }
        ]
    )

    report = run_uploaded_experiment(
        cast(Client, client),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
        target=EvaluationTargetKind.SEARCH_PLANNING,
    )

    assert report.passed
    assert report.failed_example_count == 0


@pytest.mark.parametrize(
    "script_path",
    ("scripts/create_eval_dataset.py", "scripts/run_evals.py"),
)
def test_upload_cli_checks_evaluation_opt_in_before_constructing_a_client(
    script_path: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    namespace = _script_namespace(script_path)
    main = _script_main(namespace)
    _set_script_global(
        main,
        "load_evaluation_settings",
        lambda: EvaluationSettings(run_langsmith_evals=False),
    )

    def fail_if_client_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Disabled upload must not construct a LangSmith client")

    _set_script_global(
        main,
        "create_langsmith_evaluation_client",
        fail_if_client_is_constructed,
    )

    exit_code = main(["--upload"])

    assert exit_code == 2
    assert "SCHOLARPATH_RUN_LANGSMITH_EVALS=true" in capsys.readouterr().err


def test_run_evals_rejects_live_flag_for_a_non_graph_target_before_network(
    capsys: pytest.CaptureFixture[str],
) -> None:
    namespace = _script_namespace("scripts/run_evals.py")
    main = _script_main(namespace)
    _set_script_global(
        main,
        "load_evaluation_settings",
        lambda: EvaluationSettings(
            run_langsmith_evals=True,
            run_live_e2e_evals=True,
        ),
    )

    def fail_if_client_is_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("Invalid CLI arguments must be rejected before network access")

    _set_script_global(
        main,
        "create_langsmith_evaluation_client",
        fail_if_client_is_constructed,
    )

    exit_code = main(["--upload", "--live", "--target", EvaluationTargetKind.RESEARCH_FIT.value])

    assert exit_code == 2
    assert "graph_live" in capsys.readouterr().err


def test_run_evals_maps_langsmith_failure_to_a_recoverable_cli_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    namespace = _script_namespace("scripts/run_evals.py")
    main = _script_main(namespace)
    _set_script_global(
        main,
        "load_evaluation_settings",
        lambda: EvaluationSettings(run_langsmith_evals=True),
    )

    def fail_client_construction(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise LangSmithError("synthetic credential detail must not become a stack trace")

    _set_script_global(
        main,
        "create_langsmith_evaluation_client",
        fail_client_construction,
    )

    exit_code = main(["--upload", "--target", "graph_fake"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "LangSmith" in captured.err
    assert "request failed" in captured.err
    assert "credential detail" not in captured.err
