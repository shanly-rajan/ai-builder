"""Supplemental policy reports cannot rewrite historical effort or invent completion."""

import json
import runpy
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Never

import pytest
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
from pydantic import ValidationError

from scholarpath.evaluation import interaction_policy_report as reporting
from scholarpath.evaluation.interaction_budget import (
    InteractionBudgetReport,
    run_interaction_budget_diagnostic,
)
from scholarpath.evaluation.interaction_policy_report import (
    InteractionPolicyReport,
    build_interaction_policy_report,
    main,
    policy_report_exit_code,
    render_interaction_policy_report,
    run_interaction_policy_check,
    summarize_policy_decisions,
)

PRIVATE = "private-name@example.test secret-token full-research-statement"


@pytest.fixture(scope="module")
def report() -> InteractionPolicyReport:
    measured = run_interaction_budget_diagnostic(recorded_on=date(2026, 9, 6))
    return build_interaction_policy_report(measured, recorded_on=date(2026, 9, 6))


def test_saved_policy_report_matches_fresh_frozen_measurements(
    report: InteractionPolicyReport,
) -> None:
    saved = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "evaluation"
        / "week4-interaction-policy-2026-09-06.json"
    )
    recorded = InteractionPolicyReport.model_validate_json(saved.read_text(encoding="utf-8"))
    assert recorded == report


def test_policy_is_supplemental_and_does_not_mutate_source(
    report: InteractionPolicyReport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = report.source_measurements.model_dump_json()

    def forbidden() -> Never:
        pytest.fail("Building a policy report must not execute a graph")

    monkeypatch.setattr(reporting, "run_interaction_budget_diagnostic", forbidden)
    actual = build_interaction_policy_report(
        report.source_measurements, recorded_on=date(2026, 9, 6)
    )
    assert report.source_measurements.model_dump_json() == before
    assert actual.source_measurements.model_dump_json() == before
    assert actual.policy.first_review_limit == 40
    assert actual.policy.full_interaction_limit == 80
    assert actual.source_measurements.first_review_limit is None
    assert actual.source_measurements.full_interaction_limit is None
    assert actual.source_measurements.supplemental_policy_status == "not_configured"
    assert actual.source_measurements.legacy_graph_port_invocation_budget == 40
    assert actual.source_measurements.legacy_whole_case_budget_passed is False


def test_summary_keeps_twelve_first_reviews_three_completions_and_nine_pauses_distinct(
    report: InteractionPolicyReport,
) -> None:
    assert report.summary.model_dump() == {
        "first_review_passed": 12,
        "first_review_exceeded": 0,
        "first_review_not_reached": 0,
        "completed_interaction_passed": 3,
        "within_budget_so_far": 9,
        "interaction_exceeded": 0,
        "interaction_not_completed": 0,
        "interaction_not_applicable": 0,
        "legacy_whole_case_failures": 1,
    }
    request_more = next(
        item for item in report.decisions if item.scenario_id == "draft-graph-request-more"
    )
    assert request_more.interaction_calls == 76
    assert request_more.interaction_status == "within_budget_so_far"
    assert request_more.legacy_whole_case_budget_passed is False
    assert policy_report_exit_code(report) == 1


def test_report_round_trip_and_default_utc_date(report: InteractionPolicyReport) -> None:
    assert InteractionPolicyReport.model_validate_json(report.model_dump_json()) == report
    before = datetime.now(UTC).date()
    actual = build_interaction_policy_report(report.source_measurements)
    assert before <= actual.recorded_on <= datetime.now(UTC).date()
    assert actual.source_measurements.recorded_on == date(2026, 9, 6)


@pytest.mark.parametrize(
    "mutation",
    ("summary", "decision_count", "decision_status", "decision_order", "policy", "digest"),
)
def test_forged_derivations_and_provenance_fail_closed(
    mutation: str, report: InteractionPolicyReport
) -> None:
    raw = report.model_dump(mode="json")
    if mutation == "summary":
        raw["summary"]["completed_interaction_passed"] = 12
    elif mutation == "decision_count":
        raw["decisions"][0]["interaction_calls"] = 0
    elif mutation == "decision_status":
        raw["decisions"][0]["interaction_status"] = "passed"
    elif mutation == "decision_order":
        raw["decisions"].reverse()
    elif mutation == "policy":
        raw["policy"]["full_interaction_limit"] = 100
    else:
        raw["source_measurements"]["content_digest"] = "0" * 64
    with pytest.raises(ValidationError):
        InteractionPolicyReport.model_validate(raw)


@pytest.mark.parametrize("mutation", ("policy", "source", "summary"))
def test_unchecked_nested_model_copies_are_revalidated(
    mutation: str, report: InteractionPolicyReport
) -> None:
    if mutation == "policy":
        invalid = report.model_copy(
            update={"policy": report.policy.model_copy(update={"first_review_limit": 80})}
        )
    elif mutation == "source":
        invalid = report.model_copy(
            update={
                "source_measurements": report.source_measurements.model_copy(
                    update={"source_draft_digest": "0" * 64}
                )
            }
        )
    else:
        invalid = report.model_copy(
            update={"summary": report.summary.model_copy(update={"legacy_whole_case_failures": 0})}
        )
    with pytest.raises(ValidationError):
        render_interaction_policy_report(invalid)
    with pytest.raises(ValidationError):
        policy_report_exit_code(invalid)


def test_summary_counts_every_status_without_collapsing_unknown_into_pass(
    report: InteractionPolicyReport,
) -> None:
    base = report.decisions[0]
    decisions = (
        base.model_copy(update={"interaction_status": "passed"}),
        base.model_copy(update={"interaction_status": "within_budget_so_far"}),
        base.model_copy(
            update={"first_review_status": "exceeded", "interaction_status": "exceeded"}
        ),
        base.model_copy(
            update={"first_review_status": "not_reached", "interaction_status": "not_completed"}
        ),
        base.model_copy(
            update={
                "interaction_status": "not_applicable",
                "legacy_whole_case_budget_passed": False,
            }
        ),
    )
    actual = summarize_policy_decisions(decisions)
    assert actual.first_review_passed == 3
    assert actual.first_review_exceeded == actual.first_review_not_reached == 1
    assert actual.completed_interaction_passed == actual.within_budget_so_far == 1
    assert actual.interaction_exceeded == actual.interaction_not_completed == 1
    assert actual.interaction_not_applicable == actual.legacy_whole_case_failures == 1


def test_rendering_explains_partial_progress_and_has_no_private_payloads(
    report: InteractionPolicyReport,
) -> None:
    text = render_interaction_policy_report(report)
    assert "interaction=76/80 [within_budget_so_far]" in text
    assert "3 completed within budget; 9 paused within budget so far" in text
    assert "Legacy whole-case budget failures: 1." in text
    assert "A paused prefix is not a completed interaction or an approved shortlist." in text
    assert "not a runtime optimization" in text
    for rendered in (text, report.model_dump_json()):
        for value in (
            PRIVATE,
            "candidate-001",
            "supervisor-001",
            "Amara",
            "https://",
            "candidate_profile",
            "source_excerpt",
            "research_statement",
        ):
            assert value not in rendered


@pytest.mark.parametrize("output_format", ("text", "json"))
def test_cli_keeps_exit_one_for_the_historical_budget_failure(
    output_format: str,
    report: InteractionPolicyReport,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(reporting, "run_interaction_policy_check", lambda: report)
    assert main(["--format", output_format]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    if output_format == "json":
        assert json.loads(captured.out) == report.model_dump(mode="json")
    else:
        assert "76/80 [within_budget_so_far]" in captured.out
        assert "Legacy whole-case budget failures: 1." in captured.out


def test_run_disables_tracing_despite_optins_and_restores_parent_context(
    report: InteractionPolicyReport, monkeypatch: pytest.MonkeyPatch
) -> None:
    for flag in (
        "LANGSMITH_TRACING",
        "SCHOLARPATH_RUN_LIVE_TESTS",
        "SCHOLARPATH_RUN_LANGSMITH_EVALS",
        "SCHOLARPATH_RUN_LIVE_E2E_EVALS",
    ):
        monkeypatch.setenv(flag, "true")
    observed: list[bool] = []

    def measured() -> InteractionBudgetReport:
        assert get_tracing_context()["enabled"] is False
        observed.append(True)
        return report.source_measurements

    monkeypatch.setattr(reporting, "run_interaction_budget_diagnostic", measured)
    with tracing_context(enabled=True):
        actual = run_interaction_policy_check()
        assert get_tracing_context()["enabled"] is True
    assert observed == [True]
    assert actual.source_measurements == report.source_measurements


@pytest.mark.parametrize("error_type", (RuntimeError, ValueError))
def test_cli_sanitizes_exceptions_and_restores_context(
    error_type: type[Exception],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def failure() -> Never:
        assert get_tracing_context()["enabled"] is False
        raise error_type(PRIVATE)

    monkeypatch.setattr(reporting, "run_interaction_budget_diagnostic", failure)
    with tracing_context(enabled=True):
        assert main([]) == 2
        assert get_tracing_context()["enabled"] is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "The offline interaction policy check could not complete safely."


@pytest.mark.parametrize("error", (KeyboardInterrupt(), SystemExit(7)))
def test_cli_does_not_swallow_process_control(
    error: BaseException, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stop() -> Never:
        raise error

    monkeypatch.setattr(reporting, "run_interaction_policy_check", stop)
    with pytest.raises(type(error)):
        main([])


@pytest.mark.parametrize("option", ("--live", "--upload", "--write", "--budget"))
def test_cli_has_no_live_write_or_budget_override(option: str) -> None:
    with pytest.raises(SystemExit) as error:
        main([option])
    assert error.value.code == 2


def test_script_delegates_without_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(reporting, "main", lambda: 1)
    script = Path(__file__).resolve().parents[3] / "scripts" / "check_interaction_policy.py"
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(script), run_name="__main__")
    assert error.value.code == 1


def test_exit_zero_requires_no_legacy_failure_without_changing_its_limit(
    report: InteractionPolicyReport,
) -> None:
    # A synthetic observation only: frozen targets, labels, and saved results stay unchanged.
    raw = report.source_measurements.model_dump(mode="json")
    case = next(item for item in raw["cases"] if item["scenario_id"] == "draft-graph-request-more")
    first, second = case["invocations"]
    second["cumulative_counts"] = dict(first["cumulative_counts"])
    second["cumulative_counts"]["memory_store"] = 1
    second["invocation_counts"] = {key: 0 for key in first["invocation_counts"]}
    second["invocation_counts"]["memory_store"] = 1
    second["invocation_calls"] = 1
    case["complete_scripted_interaction_calls"] = 39
    case["legacy_whole_case_budget_passed"] = True
    raw["legacy_whole_case_budget_passed"] = True
    synthetic = build_interaction_policy_report(InteractionBudgetReport.model_validate(raw))
    assert synthetic.summary.legacy_whole_case_failures == 0
    assert synthetic.policy.first_review_limit == 40
    assert synthetic.source_measurements.legacy_graph_port_invocation_budget == 40
    assert policy_report_exit_code(synthetic) == 0
