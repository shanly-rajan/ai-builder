"""Case-level evaluation diagnostics stay useful, bounded, and private."""

from __future__ import annotations

from collections.abc import Sequence
from types import SimpleNamespace
from typing import cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langsmith import Client
from langsmith.evaluation import EvaluationResult
from langsmith.schemas import Example

from scholarpath.config import EvaluationSettings, LangSmithSettings
from scholarpath.evaluation import (
    EVALUATION_SCENARIOS,
    EvaluationScenario,
    EvaluationTargetKind,
    format_failure_summary,
    run_local_baseline,
    run_uploaded_experiment,
    stable_example_id,
)
from tests.unit.evaluation.test_runner import (
    _ExperimentRows,
    _hard_gate_results,
    _script_main,
    _script_namespace,
    _set_script_global,
)

_PRIVATE_TEXT = "private-person@example.test SECRET_TOKEN full private research statement"
_RUN_ID = UUID("ae752a49-044b-4b8b-b0e7-9f240c81069c")


def _example(scenario: EvaluationScenario) -> Example:
    example = MagicMock(spec=Example)
    example.id = stable_example_id("failure-report-tests", scenario.scenario_id)
    example.inputs = {"scenario": scenario.model_dump(mode="json", exclude={"expected"})}
    return cast(Example, example)


def _row(example: Example, results: Sequence[EvaluationResult]) -> dict[str, object]:
    return {
        "example": example,
        "run": SimpleNamespace(id=_RUN_ID, error=None, outputs={"private": _PRIVATE_TEXT}),
        "evaluation_results": {"results": list(results)},
    }


def _client(examples: Sequence[Example], rows: list[dict[str, object]]) -> Client:
    client = MagicMock(spec=Client)
    client.list_examples.return_value = examples
    client.evaluate.return_value = _ExperimentRows(rows)
    return cast(Client, client)


def test_multiple_failed_checks_are_grouped_with_case_ids_and_guidance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scholarpath.evaluation.runner.dispatch_evaluation_target", lambda _: {})

    def schema_validity(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None
    ) -> EvaluationResult:
        return EvaluationResult(key="schema_validity", score=False)

    def evidence_id_validity(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None
    ) -> EvaluationResult:
        return EvaluationResult(key="evidence_id_validity", score=False)

    report = run_local_baseline(
        scenarios=EVALUATION_SCENARIOS[:2], evaluators=(schema_validity, evidence_id_validity)
    )
    summary = format_failure_summary(report)

    assert report.passed_scenario_count == 0
    assert len(report.failures) == 4
    assert "2/2 cases failed" in summary
    assert "schema_validity [metric_failed]: 2" in summary
    assert "evidence_id_validity [metric_failed]: 2" in summary
    assert "inspect the target response contract" in summary
    for scenario in EVALUATION_SCENARIOS[:2]:
        assert f"{scenario.scenario_id} [{scenario.target.value}]" in summary


def test_not_applicable_and_zero_duplicate_rate_do_not_become_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("scholarpath.evaluation.runner.dispatch_evaluation_target", lambda _: {})

    def not_applicable(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None
    ) -> EvaluationResult:
        return EvaluationResult(key="not_applicable", score=None)

    def duplicate_supervisor_rate(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None
    ) -> EvaluationResult:
        return EvaluationResult(
            key="duplicate_supervisor_rate",
            score=0.0,
            metadata={"lower_is_better": True, "threshold_passed": True},
        )

    report = run_local_baseline(
        scenarios=EVALUATION_SCENARIOS[:1], evaluators=(not_applicable, duplicate_supervisor_rate)
    )

    assert report.passed
    assert report.failures == ()
    assert report.metric_summaries[0].applicable_count == 0
    assert report.metric_summaries[0].observed_mean is None
    assert report.metric_summaries[1].passed_count == 1
    assert report.metric_summaries[1].observed_mean == 0.0


def test_expected_fallback_and_rejection_are_successful_evaluation_cases() -> None:
    report = run_local_baseline(target=EvaluationTargetKind.GRAPH_FAKE)

    assert report.passed
    assert report.failures == ()
    assert "Expected fallback or rejection is not a failure" in format_failure_summary(report)


def test_empty_dataset_is_not_reported_as_success() -> None:
    report = run_local_baseline(scenarios=())

    assert not report.passed
    assert "no evaluation cases ran" in format_failure_summary(report)


def test_target_and_evaluator_errors_do_not_abort_later_cases_or_leak_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    def target(inputs: dict[str, object]) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(_PRIVATE_TEXT)
        return {"private": _PRIVATE_TEXT}

    def broken_check(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None
    ) -> EvaluationResult:
        raise ValueError(_PRIVATE_TEXT)

    def schema_validity(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None
    ) -> EvaluationResult:
        return EvaluationResult(
            key="schema_validity",
            score=False,
            comment=_PRIVATE_TEXT,
            metadata={"private": _PRIVATE_TEXT},
        )

    monkeypatch.setattr("scholarpath.evaluation.runner.dispatch_evaluation_target", target)
    report = run_local_baseline(
        scenarios=EVALUATION_SCENARIOS[:2], evaluators=(broken_check, schema_validity)
    )

    assert calls == 2
    assert report.scenario_count == 2
    assert {item.category for item in report.failures} == {
        "target_error",
        "evaluator_error",
        "metric_failed",
    }
    assert report.failures[0].scenario_id == EVALUATION_SCENARIOS[0].scenario_id
    assert report.scenarios[1].metrics[1].key == "schema_validity"
    assert _PRIVATE_TEXT not in report.model_dump_json()
    assert _PRIVATE_TEXT not in format_failure_summary(report)


def test_uploaded_failure_identifies_the_actual_example_despite_out_of_order_rows() -> None:
    first, second = (_example(scenario) for scenario in EVALUATION_SCENARIOS[:2])
    client = _client(
        (first, second),
        [
            _row(second, _hard_gate_results(failing_key="schema_validity")),
            _row(first, _hard_gate_results()),
        ],
    )

    report = run_uploaded_experiment(
        client, evaluation_settings=EvaluationSettings(run_langsmith_evals=True)
    )

    assert report.failed_example_count == 1
    assert len(report.failures) == 1
    assert report.failures[0].scenario_id == EVALUATION_SCENARIOS[1].scenario_id
    assert report.failures[0].target is EvaluationTargetKind.RESEARCH_FIT
    assert report.failures[0].run_id == _RUN_ID
    assert str(_RUN_ID) in format_failure_summary(report)
    assert _PRIVATE_TEXT not in report.model_dump_json()


@pytest.mark.parametrize("problem", ("target_error", "evaluator_error", "missing_result"))
def test_uploaded_errors_are_typed_and_do_not_expose_sdk_text(problem: str) -> None:
    example = _example(EVALUATION_SCENARIOS[0])
    results = _hard_gate_results()
    row = _row(example, results)
    if problem == "target_error":
        row["run"] = SimpleNamespace(id=_RUN_ID, error=_PRIVATE_TEXT)
    elif problem == "evaluator_error":
        results[0] = EvaluationResult(
            key=results[0].key,
            score=None,
            comment=_PRIVATE_TEXT,
            metadata={"error": True, "private": _PRIVATE_TEXT},
        )
        row["evaluation_results"] = {"results": results}
    else:
        row["evaluation_results"] = {"results": results[1:]}

    report = run_uploaded_experiment(
        _client((example,), [row]),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
    )

    assert not report.passed
    assert report.failed_example_count == 1
    assert len(report.failures) == 1
    assert report.failures[0].category == problem
    assert report.failures[0].scenario_id == EVALUATION_SCENARIOS[0].scenario_id
    assert _PRIVATE_TEXT not in report.model_dump_json()
    assert _PRIVATE_TEXT not in format_failure_summary(report)


def test_missing_sdk_example_result_cannot_turn_an_incomplete_experiment_green() -> None:
    first, second = (_example(scenario) for scenario in EVALUATION_SCENARIOS[:2])

    report = run_uploaded_experiment(
        _client((first, second), [_row(first, _hard_gate_results())]),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
    )

    assert not report.passed
    assert report.example_count == 2
    assert report.failed_example_count == 1
    assert report.failures[0].scenario_id == EVALUATION_SCENARIOS[1].scenario_id
    assert report.failures[0].category == "missing_result"


def test_unknown_uploaded_case_identity_is_reported_without_guessing_or_echoing_input() -> None:
    example = _example(EVALUATION_SCENARIOS[0])
    row = _row(example, _hard_gate_results())
    row["example"] = SimpleNamespace(id=_PRIVATE_TEXT)

    report = run_uploaded_experiment(
        _client((example,), [row]),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
    )

    assert not report.passed
    assert report.failures[0].scenario_id == "unidentified-example-1"
    assert report.failures[0].key == "case_identity"
    assert _PRIVATE_TEXT not in format_failure_summary(report)


def test_nonhard_judge_advisories_do_not_change_deterministic_gate_status() -> None:
    example = _example(EVALUATION_SCENARIOS[0])
    results = [
        *_hard_gate_results(),
        EvaluationResult(key="research_fit_relevance_judge", score=False, comment=_PRIVATE_TEXT),
    ]
    report = run_uploaded_experiment(
        _client((example,), [_row(example, results)]),
        evaluation_settings=EvaluationSettings(run_langsmith_evals=True),
    )

    assert report.passed
    assert report.failures == ()
    assert _PRIVATE_TEXT not in report.model_dump_json()


@pytest.mark.parametrize("upload", (False, True))
@pytest.mark.parametrize("passed", (False, True))
def test_cli_prints_failure_summary_and_matching_exit_status_without_network(
    upload: bool,
    passed: bool,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    main = _script_main(_script_namespace("scripts/run_evals.py"))
    _set_script_global(
        main, "load_evaluation_settings", lambda: EvaluationSettings(run_langsmith_evals=True)
    )
    if upload:
        example = _example(EVALUATION_SCENARIOS[0])
        client = _client(
            (example,),
            [_row(example, _hard_gate_results(failing_key=None if passed else "schema_validity"))],
        )
        _set_script_global(main, "load_langsmith_settings", LangSmithSettings)
        _set_script_global(main, "create_langsmith_evaluation_client", lambda _: client)
        _set_script_global(main, "sync_evaluation_dataset", MagicMock())
    else:
        monkeypatch.setattr(
            "scholarpath.evaluation.runner.dispatch_evaluation_target", lambda _: {}
        )

        def schema_validity(
            outputs: dict[str, object], reference_outputs: dict[str, object] | None
        ) -> EvaluationResult:
            return EvaluationResult(key="schema_validity", score=passed)

        report = run_local_baseline(
            scenarios=EVALUATION_SCENARIOS[:1], evaluators=(schema_validity,)
        )
        _set_script_global(main, "run_local_baseline", lambda **_: report)

    assert main(["--upload"] if upload else []) == (0 if passed else 1)
    output = capsys.readouterr().out
    assert "Failure summary:" in output
    assert ("no failed cases" if passed else "1/1 cases failed") in output
    if not passed:
        assert EVALUATION_SCENARIOS[0].scenario_id in output
        assert "schema_validity" in output
    assert _PRIVATE_TEXT not in output
