"""The inspectable trace path accepts exactly one curated case and fake providers."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langsmith import Client
from langsmith.schemas import Example

from scholarpath.config import EvaluationSettings, ProviderConfigurationError
from scholarpath.evaluation.judges import JudgeEvaluator
from scholarpath.evaluation.models import EvaluationTargetKind
from scholarpath.evaluation.runner import (
    UploadedExperimentReport,
    UploadedRunReference,
    run_local_baseline,
    run_uploaded_experiment,
    stable_example_id,
)
from scholarpath.evaluation.scenarios import (
    EVALUATION_SCENARIOS,
    evaluation_dataset_inputs,
    evaluation_dataset_reference_outputs,
)
from scholarpath.evaluation.synthetic_tracing import SyntheticEvaluationObservability
from scholarpath.evaluation.trace_case import (
    SYNTHETIC_TRACE_CASE_ID,
    SYNTHETIC_TRACE_DATASET,
    synthetic_trace_scenario,
    traced_fallback_target,
)
from tests.unit.evaluation.test_runner import (
    ScriptMain,
    _ExperimentRows,
    _hard_gate_results,
    _script_main,
    _script_namespace,
    _set_script_global,
)

_PRIVATE = "private-person@example.test token-private research statement"
_RUN_ID = UUID("2273a4a9-9e7c-4ffc-9ab3-218f4d0e531c")
_TRACE_ID = UUID("4b9e66eb-8900-49c3-ae40-81888cfc2a56")
_START = datetime(2026, 9, 6, 10, tzinfo=UTC)


def _example() -> Example:
    scenario = synthetic_trace_scenario()
    example = MagicMock(spec=Example)
    example.id = stable_example_id(SYNTHETIC_TRACE_DATASET, scenario.scenario_id)
    example.inputs = evaluation_dataset_inputs(scenario)
    example.outputs = evaluation_dataset_reference_outputs(scenario)
    return cast(Example, example)


def _client(example: Example) -> MagicMock:
    client = MagicMock(spec=Client)
    client.list_examples.return_value = (example,)
    client.evaluate.return_value = _ExperimentRows(
        [
            {
                "example": example,
                "run": SimpleNamespace(
                    id=_RUN_ID,
                    trace_id=_TRACE_ID,
                    start_time=_START,
                    error=None,
                    outputs={"private": _PRIVATE},
                ),
                "evaluation_results": {"results": _hard_gate_results()},
            }
        ]
    )
    return client


def test_synthetic_scenario_is_a_fresh_copy_of_the_curated_timeout_case() -> None:
    first, second = synthetic_trace_scenario(), synthetic_trace_scenario()
    original = next(
        case for case in EVALUATION_SCENARIOS if case.scenario_id == SYNTHETIC_TRACE_CASE_ID
    )

    assert first == second == original
    assert first is not second and first is not original
    assert first.target is EvaluationTargetKind.GRAPH_FAKE
    first.config["private"] = _PRIVATE
    assert "private" not in second.config
    assert "private" not in original.config


@pytest.mark.parametrize("mutation", ("extra", "changed", "empty"))
def test_untrusted_trace_input_is_rejected_before_any_fake_execution_or_tagging(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs = evaluation_dataset_inputs(synthetic_trace_scenario())
    if mutation == "extra":
        inputs["private"] = _PRIVATE
    elif mutation == "changed":
        scenario = cast(dict[str, object], inputs["scenario"])
        scenario["title"] = _PRIVATE
    else:
        inputs = {}
    fake_target = MagicMock()
    parent_lookup = MagicMock()
    monkeypatch.setattr("scholarpath.evaluation.trace_case.fake_end_to_end_target", fake_target)
    monkeypatch.setattr("scholarpath.evaluation.trace_case.get_current_run_tree", parent_lookup)

    with pytest.raises(ValueError, match="unchanged curated") as error:
        traced_fallback_target(inputs)

    assert _PRIVATE not in str(error.value)
    fake_target.assert_not_called()
    parent_lookup.assert_not_called()


def test_traced_target_requires_an_existing_evaluation_parent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_target = MagicMock()
    monkeypatch.setattr("scholarpath.evaluation.trace_case.fake_end_to_end_target", fake_target)
    monkeypatch.setattr("scholarpath.evaluation.trace_case.get_current_run_tree", lambda: None)

    with pytest.raises(ValueError, match="active evaluation parent"):
        traced_fallback_target(evaluation_dataset_inputs(synthetic_trace_scenario()))

    fake_target.assert_not_called()


def test_traced_target_tags_parent_and_injects_only_synthetic_observability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parent = MagicMock()
    fake_target = MagicMock(return_value={"fake_result": True})
    monkeypatch.setattr("scholarpath.evaluation.trace_case.get_current_run_tree", lambda: parent)
    monkeypatch.setattr("scholarpath.evaluation.trace_case.fake_end_to_end_target", fake_target)
    inputs = evaluation_dataset_inputs(synthetic_trace_scenario())

    assert traced_fallback_target(inputs) == {"fake_result": True}
    parent.add_tags.assert_called_once_with(
        ["synthetic-evaluation:allowlisted", "model-provider:fake"]
    )
    assert fake_target.call_args.args == (inputs,)
    assert isinstance(
        fake_target.call_args.kwargs["observability"], SyntheticEvaluationObservability
    )


@pytest.mark.parametrize("incompatible", ("live", "judges", "component", "dataset"))
def test_synthetic_trace_rejects_incompatible_modes_before_listing_examples(
    incompatible: str,
) -> None:
    client = MagicMock(spec=Client)
    judges = (
        (cast(JudgeEvaluator, MagicMock(spec=JudgeEvaluator)),) if incompatible == "judges" else ()
    )

    with pytest.raises(ValueError, match="dedicated one-case"):
        run_uploaded_experiment(
            cast(Client, client),
            evaluation_settings=EvaluationSettings(
                run_langsmith_evals=True, run_live_e2e_evals=True
            ),
            dataset_name="wrong-dataset" if incompatible == "dataset" else SYNTHETIC_TRACE_DATASET,
            target=EvaluationTargetKind.SEARCH_PLANNING if incompatible == "component" else None,
            judge_evaluators=judges,
            live=incompatible == "live",
            synthetic_trace=True,
        )

    client.list_examples.assert_not_called()
    client.evaluate.assert_not_called()


def test_synthetic_upload_requires_explicit_evaluation_opt_in() -> None:
    client = MagicMock(spec=Client)
    with pytest.raises(ProviderConfigurationError, match="upload is disabled"):
        run_uploaded_experiment(
            cast(Client, client),
            evaluation_settings=EvaluationSettings(run_langsmith_evals=False),
            dataset_name=SYNTHETIC_TRACE_DATASET,
            synthetic_trace=True,
        )
    client.list_examples.assert_not_called()


@pytest.mark.parametrize("mutation", ("inputs", "reference", "duplicate"))
def test_upload_rejects_changed_inputs_labels_or_duplicate_curated_examples(mutation: str) -> None:
    example = _example()
    client = _client(example)
    if mutation == "inputs":
        assert example.inputs is not None
        scenario = cast(dict[str, object], example.inputs["scenario"])
        scenario["title"] = _PRIVATE
    elif mutation == "reference":
        example.outputs = {"private": _PRIVATE}
    else:
        client.list_examples.return_value = (example, example)

    with pytest.raises(ValueError, match="exactly one unchanged") as error:
        run_uploaded_experiment(
            cast(Client, client),
            evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
            dataset_name=SYNTHETIC_TRACE_DATASET,
            synthetic_trace=True,
        )

    assert _PRIVATE not in str(error.value)
    client.evaluate.assert_not_called()


@pytest.mark.parametrize("target", (None, EvaluationTargetKind.GRAPH_FAKE))
def test_synthetic_runner_selects_one_case_dispatches_tracer_and_returns_safe_run_coordinates(
    target: EvaluationTargetKind | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    example = _example()
    client = _client(example)
    unrelated = MagicMock(spec=Example)
    unrelated.inputs = evaluation_dataset_inputs(EVALUATION_SCENARIOS[0])
    client.list_examples.return_value = (unrelated, example)
    traced = MagicMock(return_value={"traced": True})
    ordinary = MagicMock(side_effect=AssertionError("must use the synthetic tracer"))
    monkeypatch.setattr("scholarpath.evaluation.runner.traced_fallback_target", traced)
    monkeypatch.setattr("scholarpath.evaluation.runner.dispatch_evaluation_target", ordinary)

    report = run_uploaded_experiment(
        cast(Client, client),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
        dataset_name=SYNTHETIC_TRACE_DATASET,
        target=target,
        synthetic_trace=True,
    )

    assert report.passed and report.example_count == 1
    assert client.evaluate.call_args.kwargs["data"] == (example,)
    target_callable = client.evaluate.call_args.args[0]
    assert target_callable(example.inputs) == {"traced": True}
    traced.assert_called_once_with(example.inputs)
    ordinary.assert_not_called()
    assert report.run_references == (
        UploadedRunReference(run_id=_RUN_ID, trace_id=_TRACE_ID, start_time=_START),
    )
    assert _PRIVATE not in report.model_dump_json()


def test_cli_default_executes_one_case_offline_without_constructing_a_client(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main = _script_main(_script_namespace("scripts/trace_eval_case.py"))
    preflight = MagicMock(wraps=run_local_baseline)
    forbidden_client = MagicMock(side_effect=AssertionError("offline must not create a client"))
    _set_script_global(main, "run_local_baseline", preflight)
    _set_script_global(main, "create_synthetic_trace_client", forbidden_client)

    assert main([]) == 0
    assert preflight.call_args.kwargs["scenarios"] == (synthetic_trace_scenario(),)
    forbidden_client.assert_not_called()
    assert "Offline preflight: 1/1 passed" in capsys.readouterr().out


def _upload_cli() -> tuple[ScriptMain, MagicMock, MagicMock, MagicMock]:
    main = _script_main(_script_namespace("scripts/trace_eval_case.py"))
    _set_script_global(
        main,
        "run_local_baseline",
        MagicMock(
            return_value=SimpleNamespace(passed=True, passed_scenario_count=1, scenario_count=1)
        ),
    )
    _set_script_global(
        main, "load_evaluation_settings", lambda: EvaluationSettings(run_langsmith_evals=True)
    )
    _set_script_global(main, "load_langsmith_settings", MagicMock())
    client = MagicMock(spec=Client)
    _set_script_global(main, "create_synthetic_trace_client", MagicMock(return_value=client))
    sync = MagicMock()
    upload = MagicMock(
        return_value=UploadedExperimentReport(
            experiment_name="synthetic-test",
            example_count=1,
            failed_example_count=0,
            run_references=(
                UploadedRunReference(run_id=_RUN_ID, trace_id=_TRACE_ID, start_time=_START),
            ),
        )
    )
    _set_script_global(main, "sync_evaluation_dataset", sync)
    _set_script_global(main, "run_uploaded_experiment", upload)
    return main, client, sync, upload


def test_cli_upload_requires_environment_opt_in_before_creating_client(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, client, sync, upload = _upload_cli()
    forbidden_client = MagicMock(side_effect=AssertionError("opt-in must precede client"))
    _set_script_global(
        main, "load_evaluation_settings", lambda: EvaluationSettings(run_langsmith_evals=False)
    )
    _set_script_global(main, "create_synthetic_trace_client", forbidden_client)

    assert main(["--upload"]) == 2
    forbidden_client.assert_not_called()
    sync.assert_not_called()
    upload.assert_not_called()
    client.close.assert_not_called()
    assert "SCHOLARPATH_RUN_LANGSMITH_EVALS=true" in capsys.readouterr().err


def test_cli_upload_syncs_only_one_case_and_flushes_and_closes_with_bounds(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, client, sync, upload = _upload_cli()

    assert main(["--upload"]) == 0
    assert sync.call_args.args == (client,)
    assert sync.call_args.kwargs == {
        "dataset_name": SYNTHETIC_TRACE_DATASET,
        "scenarios": (synthetic_trace_scenario(),),
    }
    assert upload.call_args.kwargs["dataset_name"] == SYNTHETIC_TRACE_DATASET
    assert upload.call_args.kwargs["synthetic_trace"] is True
    client.flush.assert_called_once_with(timeout=5)
    client.close.assert_called_once_with(timeout=5)
    output = capsys.readouterr().out
    assert str(_RUN_ID) in output
    assert "Only LangSmith was live" in output


@pytest.mark.parametrize("failure", ("sync", "upload", "flush", "close"))
def test_cli_sdk_and_cleanup_failures_are_sanitized_and_return_nonzero(
    failure: str,
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, client, sync, upload = _upload_cli()
    failing_call = {"sync": sync, "upload": upload, "flush": client.flush, "close": client.close}[
        failure
    ]
    failing_call.side_effect = RuntimeError(_PRIVATE)

    assert main(["--upload"]) == 2
    client.close.assert_called_once_with(timeout=5)
    captured = capsys.readouterr()
    assert _PRIVATE not in captured.err + captured.out
    assert "failed" in captured.err.lower()


def test_cli_evaluation_failure_returns_one_and_still_closes_client(
    capsys: pytest.CaptureFixture[str],
) -> None:
    main, client, _, upload = _upload_cli()
    upload.return_value = UploadedExperimentReport(
        experiment_name="synthetic-test",
        example_count=1,
        failed_example_count=1,
    )

    assert main(["--upload"]) == 1
    client.close.assert_called_once_with(timeout=5)
    assert "1/1 cases failed" in capsys.readouterr().out
