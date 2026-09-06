"""Runtime reporting does not hide failed cases or turn unknown usage into zero."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock

import pytest
from langsmith import Client

from scholarpath.config import EvaluationSettings
from scholarpath.evaluation import (
    EVALUATION_SCENARIOS,
    LocalEvaluationReport,
    RuntimeBudget,
    run_local_baseline,
    run_uploaded_experiment,
    runtime_budgets_passed,
    sync_evaluation_dataset,
)
from tests.unit.evaluation.test_failure_reporting import _client, _example, _row
from tests.unit.evaluation.test_runner import (
    _hard_gate_results,
    _script_main,
    _script_namespace,
    _set_script_global,
)


def test_runner_separates_target_from_evaluator_time_and_redacts_payloads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "scholarpath.evaluation.runner.dispatch_evaluation_target",
        lambda _: {"measurements": {"port_invocations": 2}, "secret": "DO_NOT_LOG_ME"},
    )
    ticks = iter((0.0, 2.0, 2.0, 102.0))
    report = run_local_baseline(
        scenarios=EVALUATION_SCENARIOS[:1], evaluators=(), clock=lambda: next(ticks)
    )
    assert report.scenarios[0].runtime.target_seconds == 2.0
    assert report.scenarios[0].runtime.evaluator_seconds == 100.0
    assert report.scenarios[0].runtime.port_invocations == 2
    assert report.runtime_summaries[0].p95_target_seconds == 2.0
    assert runtime_budgets_passed(report.runtime_summaries) is True
    assert "DO_NOT_LOG_ME" not in report.model_dump_json()
    assert LocalEvaluationReport.model_validate_json(report.model_dump_json()) == report


def test_failed_targets_have_duration_but_unknown_usage_and_do_not_stop_measurement(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def target(_: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("DO_NOT_LOG_ME")
        return {"measurements": {"port_invocations": 0}}

    monkeypatch.setattr("scholarpath.evaluation.runner.dispatch_evaluation_target", target)
    ticks = iter((0.0, 1.0, 1.0, 1.0, 2.0, 4.0, 4.0, 4.0))
    report = run_local_baseline(
        scenarios=EVALUATION_SCENARIOS[:2], evaluators=(), clock=lambda: next(ticks)
    )
    assert not report.passed
    assert report.scenarios[0].runtime.target_seconds == 1
    assert report.scenarios[0].runtime.port_invocations is None
    assert report.scenarios[1].runtime.port_invocations == 0
    assert report.runtime_summaries[0].latency_sample_count == 2
    assert report.runtime_summaries[0].invocation_sample_count == 1
    assert runtime_budgets_passed(report.runtime_summaries) is None
    assert "DO_NOT_LOG_ME" not in report.model_dump_json()


def test_current_run_identity_is_not_historical_and_is_unique() -> None:
    first = run_local_baseline(scenarios=())
    second = run_local_baseline(scenarios=())
    assert first.recorded_on == datetime.now(UTC).date()
    assert first.recorded_on.isoformat() in first.baseline_name
    assert first.baseline_name != second.baseline_name
    fixed = run_local_baseline(scenarios=(), recorded_on=date(2026, 9, 6))
    assert fixed.recorded_on == date(2026, 9, 6)
    assert "2026-09-06" in fixed.baseline_name


def test_historical_dataset_cannot_be_overwritten_by_new_labels() -> None:
    client = MagicMock(spec=Client)
    with pytest.raises(ValueError, match="historical M12 dataset is frozen"):
        sync_evaluation_dataset(cast(Client, client), dataset_name="scholarpath-m12-regression-v1")
    assert client.mock_calls == []


def test_uploaded_timestamps_and_counters_match_example_ids_not_row_order() -> None:
    first, second = (_example(scenario) for scenario in EVALUATION_SCENARIOS[:2])
    start = datetime(2026, 9, 6, tzinfo=UTC)
    rows = [_row(second, _hard_gate_results()), _row(first, _hard_gate_results())]
    for row, elapsed, count in zip(rows, (4, 1), (2, 1), strict=True):
        row["run"] = SimpleNamespace(
            error=None,
            start_time=start,
            end_time=start + timedelta(seconds=elapsed),
            outputs={"measurements": {"port_invocations": count}, "secret": "DO_NOT_LOG_ME"},
        )
    report = run_uploaded_experiment(
        _client((first, second), rows),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
    )
    assert report.passed
    assert report.runtime_cases[0].measurement.target_seconds == 1
    assert report.runtime_cases[0].measurement.port_invocations == 1
    assert report.runtime_cases[1].measurement.target_seconds == 4
    assert report.runtime_summaries[0].median_target_seconds == 2.5
    assert runtime_budgets_passed(report.runtime_summaries) is True
    assert all(case.measurement.evaluator_seconds is None for case in report.runtime_cases)
    assert "DO_NOT_LOG_ME" not in report.model_dump_json()


@pytest.mark.parametrize("missing_second", (False, True))
def test_duplicate_sdk_row_cannot_replace_a_missing_case_or_report_success(
    missing_second: bool,
) -> None:
    first, second = (_example(scenario) for scenario in EVALUATION_SCENARIOS[:2])
    examples = (first, second) if missing_second else (first,)
    report = run_uploaded_experiment(
        _client(examples, [_row(first, _hard_gate_results()), _row(first, _hard_gate_results())]),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
    )
    assert not report.passed
    assert report.example_count == (3 if missing_second else 2)
    assert report.failed_example_count == (2 if missing_second else 1)
    assert report.failures[0].scenario_id == "duplicate-example-result-2"
    if missing_second:
        assert report.failures[1].scenario_id == EVALUATION_SCENARIOS[1].scenario_id
        assert report.runtime_cases[1].measurement.target_seconds is None


@pytest.mark.parametrize("case", ("missing_row", "missing_time", "negative", "timezone"))
def test_incomplete_uploaded_runtime_is_unknown(case: str) -> None:
    example = _example(EVALUATION_SCENARIOS[0])
    row = _row(example, _hard_gate_results())
    start = datetime(2026, 9, 6, tzinfo=UTC)
    if case in {"negative", "timezone"}:
        row["run"] = SimpleNamespace(
            error=None,
            start_time=start,
            end_time=start - timedelta(seconds=1)
            if case == "negative"
            else start.replace(tzinfo=None),
        )
    report = run_uploaded_experiment(
        _client((example,), [] if case == "missing_row" else [row]),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
    )
    assert report.runtime_cases[0].measurement.target_seconds is None
    assert report.runtime_cases[0].measurement.port_invocations is None
    assert report.runtime_summaries[0].latency_sample_count == 0
    assert runtime_budgets_passed(report.runtime_summaries) is None


@pytest.mark.parametrize("enforce,expected_exit", ((False, 0), (True, 1)))
def test_cli_runtime_budgets_are_explicitly_opt_in(
    enforce: bool,
    expected_exit: int,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        "scholarpath.evaluation.runner.dispatch_evaluation_target",
        lambda _: {"measurements": {"port_invocations": 3}},
    )
    ticks = iter((0.0, 6.0, 6.0, 6.0))
    report = run_local_baseline(
        scenarios=EVALUATION_SCENARIOS[:1],
        evaluators=(),
        clock=lambda: next(ticks),
        runtime_budget=RuntimeBudget(component_port_invocations=2),
    )
    main = _script_main(_script_namespace("scripts/run_evals.py"))
    _set_script_global(main, "run_local_baseline", lambda **_: report)
    assert main(["--enforce-runtime-budgets"] if enforce else []) == expected_exit
    output = capsys.readouterr().out
    assert "[exceeded]" in output
    assert "Tokens and monetary cost: unmeasured" in output
    assert report.passed  # Correctness and runtime decisions are intentionally separate.


@pytest.mark.parametrize(
    "args",
    (
        ["--max-target-p95-seconds", "nan"],
        ["--max-target-p95-seconds", "0"],
        ["--max-component-port-invocations", "-1"],
        ["--max-graph-port-invocations", "0"],
        ["--live", "--upload", "--enforce-runtime-budgets"],
    ),
)
def test_cli_rejects_invalid_or_live_fake_budgets_before_any_target(args: list[str]) -> None:
    main = _script_main(_script_namespace("scripts/run_evals.py"))
    assert main(args) == 2
