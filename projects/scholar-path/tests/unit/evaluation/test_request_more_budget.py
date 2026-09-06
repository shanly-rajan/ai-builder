"""Offline call attribution preserves frozen expectations and the whole-case budget."""

import json
import runpy
from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Never

import pytest
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
from pydantic import ValidationError

from scholarpath.domain import CandidateReviewAction
from scholarpath.evaluation import request_more_budget, runner
from scholarpath.evaluation.evaluators import expected_behavior
from scholarpath.evaluation.measurements import GraphPortInvocationCounts, RuntimeBudget
from scholarpath.evaluation.request_more_budget import (
    SCENARIO_IDS,
    GraphBudgetCase,
    GraphPortInvocationDelta,
    RequestMoreBudgetDiagnosticError,
    RequestMoreBudgetReport,
    main,
    render_request_more_budget_report,
    run_request_more_budget_diagnostic,
)
from scholarpath.evaluation.reviewed_manifest import build_reviewed_manifest
from scholarpath.evaluation.scenarios import EVALUATION_SCENARIOS
from scholarpath.evaluation.targets import fake_end_to_end_target
from scholarpath.graph import ReviewStatus

PRIVATE = "private-person@example.test secret-token-full-research-statement"


@pytest.fixture
def report() -> RequestMoreBudgetReport:
    return run_request_more_budget_diagnostic(recorded_on=date(2026, 9, 6))


def _forbidden(*args: object, **kwargs: object) -> Never:
    del args, kwargs
    pytest.fail("Offline diagnostics must not construct live providers or upload")


def test_diagnostic_measures_two_independent_cases_and_preserves_budget(
    report: RequestMoreBudgetReport,
) -> None:
    first, second = report.cases
    assert tuple(case.scenario_id for case in report.cases) == SCENARIO_IDS
    assert (first.total_port_invocations, second.total_port_invocations) == (38, 76)
    assert (first.planning_passes, second.planning_passes) == (1, 2)
    assert first.port_invocations.model_dump() == {
        "planning": 1,
        "primary_search": 4,
        "fallback_search": 0,
        "alternate_evidence_search": 0,
        "content_extraction": 8,
        "evidence_model": 8,
        "research_fit": 8,
        "independent_review": 8,
        "memory_load": 1,
        "memory_store": 0,
    }
    assert second.port_invocations.model_dump() == {
        "planning": 2,
        "primary_search": 8,
        "fallback_search": 0,
        "alternate_evidence_search": 0,
        "content_extraction": 16,
        "evidence_model": 16,
        "research_fit": 16,
        "independent_review": 16,
        "memory_load": 1,
        "memory_store": 1,
    }
    assert first.candidate_actions == ()
    assert second.candidate_actions == (CandidateReviewAction.REQUEST_MORE,)
    assert all(
        case.interrupted and case.review_status is ReviewStatus.PROPOSED for case in report.cases
    )
    assert all(case.expected_behavior_passed for case in report.cases)
    assert report.graph_port_invocation_budget == RuntimeBudget().graph_port_invocations == 40
    assert report.budget_scope == "complete_graph_case"
    assert report.comparison_scope == "two_independent_frozen_cases"
    assert first.whole_case_budget_passed is True
    assert second.whole_case_budget_passed is False
    assert report.whole_case_budget_passed is False
    assert (
        report.additional_total_port_invocations == report.additional_port_invocations.total == 38
    )
    assert report.additional_port_invocations.memory_load == 0
    assert report.additional_port_invocations.memory_store == 1


def test_report_round_trip_retains_frozen_identity_and_utc_recording_date(
    report: RequestMoreBudgetReport,
) -> None:
    manifest = build_reviewed_manifest()
    assert report.recorded_on == date(2026, 9, 6)
    assert report.dataset_name == manifest.dataset_name
    assert report.reviewed_version == manifest.reviewed_version
    assert report.content_digest == manifest.content_digest
    assert report.source_draft_digest == manifest.source_draft_digest
    assert RequestMoreBudgetReport.model_validate_json(report.model_dump_json()) == report


def test_default_recording_date_is_current_utc_date() -> None:
    before = datetime.now(UTC).date()
    result = run_request_more_budget_diagnostic()
    after = datetime.now(UTC).date()
    assert before <= result.recorded_on <= after


def test_saved_diagnostic_matches_fresh_frozen_case_observations(
    report: RequestMoreBudgetReport,
) -> None:
    saved = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "evaluation"
        / "week4-request-more-budget-2026-09-06.json"
    )
    recorded = RequestMoreBudgetReport.model_validate_json(saved.read_text(encoding="utf-8"))
    assert recorded == report


def test_fake_execution_and_evaluation_remain_untraced_with_all_optins_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for flag in (
        "LANGSMITH_TRACING",
        "SCHOLARPATH_RUN_LIVE_TESTS",
        "SCHOLARPATH_RUN_LIVE_CANARY",
        "SCHOLARPATH_RUN_LANGSMITH_EVALS",
        "SCHOLARPATH_RUN_LIVE_E2E_EVALS",
    ):
        monkeypatch.setenv(flag, "true")
    for name in (
        "Client",
        "create_langsmith_evaluation_client",
        "live_end_to_end_target",
        "sync_evaluation_dataset",
        "build_openai_judge_evaluators",
        "OpenAIEvaluationJudgeAdapter",
    ):
        monkeypatch.setattr(runner, name, _forbidden)
    actual_target = fake_end_to_end_target
    actual_evaluator = expected_behavior
    target_ids: list[str] = []
    evaluator_calls: list[bool] = []

    def checked_target(
        inputs: dict[str, object],
        *,
        port_usage_observer: Callable[[GraphPortInvocationCounts], None],
    ) -> dict[str, object]:
        assert get_tracing_context()["enabled"] is False
        scenario = inputs["scenario"]
        assert isinstance(scenario, dict)
        assert "expected" not in scenario
        target_ids.append(str(scenario["scenario_id"]))
        return actual_target(inputs, port_usage_observer=port_usage_observer)

    def checked_evaluator(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None = None
    ) -> object:
        assert get_tracing_context()["enabled"] is False
        assert reference_outputs is not None and "expected" in reference_outputs
        evaluator_calls.append(True)
        return actual_evaluator(outputs, reference_outputs)

    monkeypatch.setattr(request_more_budget, "fake_end_to_end_target", checked_target)
    monkeypatch.setattr(request_more_budget, "expected_behavior", checked_evaluator)
    manifest = build_reviewed_manifest()
    original_manifest = manifest.model_dump_json()
    original_catalog = tuple(case.model_dump_json() for case in EVALUATION_SCENARIOS)
    with tracing_context(enabled=True):
        result = run_request_more_budget_diagnostic(manifest)
        assert get_tracing_context()["enabled"] is True
    assert tuple(target_ids) == SCENARIO_IDS
    assert len(evaluator_calls) == 2
    assert result.execution_mode == "fake_only"
    assert manifest.model_dump_json() == original_manifest
    assert tuple(case.model_dump_json() for case in EVALUATION_SCENARIOS) == original_catalog


def test_manifest_drift_is_rejected_before_any_target_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(request_more_budget, "fake_end_to_end_target", _forbidden)
    corrupted = build_reviewed_manifest().model_copy(update={"dataset_name": PRIVATE})
    with pytest.raises(ValidationError):
        run_request_more_budget_diagnostic(corrupted)


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_observer",
        "duplicate_observer",
        "wrong_identity",
        "wrong_target",
        "wrong_total",
        "unknown_total",
    ],
)
def test_missing_or_inconsistent_measurements_fail_closed(
    mutation: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual_target = fake_end_to_end_target

    def corrupted_target(
        inputs: dict[str, object],
        *,
        port_usage_observer: Callable[[GraphPortInvocationCounts], None],
    ) -> dict[str, object]:
        observed: list[GraphPortInvocationCounts] = []
        output = actual_target(inputs, port_usage_observer=observed.append)
        if mutation != "missing_observer":
            port_usage_observer(observed[0])
        if mutation == "duplicate_observer":
            port_usage_observer(observed[0])
        elif mutation == "wrong_identity":
            output["scenario_id"] = SCENARIO_IDS[1]
        elif mutation == "wrong_target":
            output["target"] = "graph_live"
        elif mutation == "wrong_total":
            output["measurements"] = {"port_invocations": 0}
        elif mutation == "unknown_total":
            output["measurements"] = {"port_invocations": None}
        return output

    monkeypatch.setattr(request_more_budget, "fake_end_to_end_target", corrupted_target)
    with pytest.raises(RequestMoreBudgetDiagnosticError, match="could not complete safely"):
        run_request_more_budget_diagnostic()


def test_current_expected_behavior_is_evaluated_not_assumed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    actual_target = fake_end_to_end_target

    def wrong_behavior(
        inputs: dict[str, object],
        *,
        port_usage_observer: Callable[[GraphPortInvocationCounts], None],
    ) -> dict[str, object]:
        output = actual_target(inputs, port_usage_observer=port_usage_observer)
        output["interrupted"] = False
        return output

    monkeypatch.setattr(request_more_budget, "fake_end_to_end_target", wrong_behavior)
    with pytest.raises(RequestMoreBudgetDiagnosticError):
        run_request_more_budget_diagnostic()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("scenario_id", PRIVATE),
        ("candidate_actions", [PRIVATE]),
        ("review_status", PRIVATE),
        ("planning_passes", "2"),
        ("planning_passes", True),
        ("planning_passes", 0),
        ("total_port_invocations", 0),
        ("whole_case_budget_passed", False),
        ("expected_behavior_passed", False),
        ("candidate_name", PRIVATE),
    ),
)
def test_case_contract_rejects_private_fields_and_false_observations(
    field: str,
    value: object,
    report: RequestMoreBudgetReport,
) -> None:
    raw = report.cases[0].model_dump()
    raw[field] = value
    with pytest.raises(ValidationError):
        GraphBudgetCase.model_validate(raw)


@pytest.mark.parametrize(
    "mutation",
    [
        "order",
        "duplicate",
        "delta",
        "total",
        "budget",
        "scope",
        "decision",
        "private",
        "digest",
        "source_digest",
    ],
)
def test_report_rejects_relabelled_or_inconsistent_comparisons(
    mutation: str,
    report: RequestMoreBudgetReport,
) -> None:
    raw = report.model_dump(mode="json")
    if mutation == "order":
        raw["cases"].reverse()
    elif mutation == "duplicate":
        raw["cases"][1] = raw["cases"][0]
    elif mutation == "delta":
        raw["additional_port_invocations"]["memory_store"] = 0
    elif mutation == "total":
        raw["additional_total_port_invocations"] = 0
    elif mutation == "budget":
        raw["graph_port_invocation_budget"] = 80
    elif mutation == "scope":
        raw["budget_scope"] = "per_round"
    elif mutation == "decision":
        raw["whole_case_budget_passed"] = True
    elif mutation == "digest":
        raw["content_digest"] = "0" * 64
    elif mutation == "source_digest":
        raw["source_draft_digest"] = "0" * 64
    else:
        raw["raw_output"] = PRIVATE
    with pytest.raises(ValidationError):
        RequestMoreBudgetReport.model_validate(raw)


@pytest.mark.parametrize("value", ["1", True, 1.5])
def test_delta_values_are_strict_integers(value: object, report: RequestMoreBudgetReport) -> None:
    raw = report.additional_port_invocations.model_dump()
    raw["planning"] = value
    with pytest.raises(ValidationError):
        GraphPortInvocationDelta.model_validate(raw)


def test_text_and_json_include_only_allowlisted_counts_and_statuses(
    report: RequestMoreBudgetReport,
) -> None:
    text = render_request_more_budget_report(report)
    assert "38/40 calls [pass]" in text
    assert "76/40 calls [exceeded]" in text
    assert "Additional calls across independent cases: 38" in text
    assert "not a measured per-round breakdown" in text
    assert "not HTTP requests, tokens, or monetary cost" in text
    for rendered in (text, report.model_dump_json()):
        assert all(
            private_field not in rendered
            for private_field in (
                PRIVATE,
                "candidate-001",
                "supervisor-001",
                "Amara",
                "enterprise architecture",
                "https://",
                "candidate_profile",
                "source_url",
                "source_excerpt",
                "research_statement",
            )
        )


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_cli_exits_one_for_real_whole_case_budget_failure(
    output_format: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    report: RequestMoreBudgetReport,
) -> None:
    monkeypatch.setattr(request_more_budget, "run_request_more_budget_diagnostic", lambda: report)
    assert main(["--format", output_format]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    if output_format == "json":
        output = json.loads(captured.out)
        assert output["graph_port_invocation_budget"] == 40
        assert output["whole_case_budget_passed"] is False
        assert output["additional_total_port_invocations"] == 38
    else:
        assert "76/40 calls [exceeded]" in captured.out


def test_cli_can_report_a_future_budget_pass_without_changing_budget(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
    report: RequestMoreBudgetReport,
) -> None:
    # Test-only observations exercise exit 0; no frozen target or label is edited.
    raw = report.model_dump(mode="json")
    counts = {
        **raw["cases"][0]["port_invocations"],
        "planning": 2,
        "memory_load": 0,
        "memory_store": 1,
    }
    raw["cases"][1]["port_invocations"] = counts
    raw["cases"][1]["total_port_invocations"] = sum(counts.values())
    raw["cases"][1]["whole_case_budget_passed"] = True
    raw["additional_port_invocations"] = {
        name: counts[name] - raw["cases"][0]["port_invocations"][name]
        for name in GraphPortInvocationCounts.model_fields
    }
    raw["additional_total_port_invocations"] = 1
    raw["whole_case_budget_passed"] = True
    passing = RequestMoreBudgetReport.model_validate(raw)
    monkeypatch.setattr(request_more_budget, "run_request_more_budget_diagnostic", lambda: passing)
    assert main([]) == 0
    assert "39/40 calls [pass]" in capsys.readouterr().out


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_cli_sanitizes_unexpected_failures_and_restores_trace_context(
    output_format: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def failing_target(*args: object, **kwargs: object) -> Never:
        del args, kwargs
        assert get_tracing_context()["enabled"] is False
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(request_more_budget, "fake_end_to_end_target", failing_target)
    with tracing_context(enabled=True):
        assert main(["--format", output_format]) == 2
        assert get_tracing_context()["enabled"] is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "The offline call-budget diagnostic could not complete safely."
    assert PRIVATE not in captured.err
    assert "Traceback" not in captured.err


@pytest.mark.parametrize("interruption", [KeyboardInterrupt, SystemExit])
def test_cli_does_not_swallow_process_control_exceptions(
    interruption: type[BaseException],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def interrupted() -> Never:
        raise interruption()

    monkeypatch.setattr(request_more_budget, "run_request_more_budget_diagnostic", interrupted)
    with pytest.raises(interruption):
        main([])


@pytest.mark.parametrize(
    "args",
    [
        ["--live"],
        ["--upload"],
        ["--judge"],
        ["--write"],
        ["--output", "file.json"],
        ["--format", "html"],
    ],
)
def test_cli_rejects_unscoped_modes_before_execution(
    args: list[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(request_more_budget, "run_request_more_budget_diagnostic", _forbidden)
    with pytest.raises(SystemExit) as caught:
        main(args)
    assert caught.value.code == 2


def test_script_delegates_to_the_offline_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(request_more_budget, "main", lambda: 7)
    script = Path(__file__).resolve().parents[3] / "scripts" / "inspect_request_more_budget.py"
    with pytest.raises(SystemExit) as caught:
        runpy.run_path(str(script), run_name="__main__")
    assert caught.value.code == 7
