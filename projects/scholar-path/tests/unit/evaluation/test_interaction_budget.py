"""Real invocation boundaries supplement, never redefine, the legacy budget."""

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
from scholarpath.evaluation import interaction_budget, runner
from scholarpath.evaluation.evaluators import expected_behavior
from scholarpath.evaluation.interaction_budget import (
    InteractionBudgetReport,
    InteractionCaseMeasurement,
    InteractionMeasurementError,
    main,
    render_interaction_budget_report,
    run_interaction_budget_diagnostic,
)
from scholarpath.evaluation.measurements import GraphInvocationObservation, RuntimeBudget
from scholarpath.evaluation.models import EvaluationTargetKind
from scholarpath.evaluation.reviewed_manifest import build_reviewed_manifest
from scholarpath.evaluation.targets import fake_end_to_end_target
from scholarpath.graph import ReviewStatus

PRIVATE = "private-name@example.test secret-token full-research-statement"


@pytest.fixture(scope="module")
def report() -> InteractionBudgetReport:
    return run_interaction_budget_diagnostic(recorded_on=date(2026, 9, 6))


def _forbidden(*args: object, **kwargs: object) -> Never:
    del args, kwargs
    pytest.fail("Offline interaction measurement must never call live services")


def test_all_twelve_frozen_graph_cases_are_measured_without_new_limits(
    report: InteractionBudgetReport,
) -> None:
    manifest = build_reviewed_manifest()
    expected_ids = tuple(
        case.scenario.scenario_id
        for case in manifest.source_draft.cases
        if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
    )
    assert tuple(case.scenario_id for case in report.cases) == expected_ids
    assert report.case_count == len(report.cases) == 12
    assert report.content_digest == manifest.content_digest
    assert report.source_draft_digest == manifest.source_draft_digest
    assert report.measurement_version == "week4-interaction-measurements-v1"
    assert report.first_review_limit is report.full_interaction_limit is None
    assert report.supplemental_policy_status == "not_configured"
    assert (
        report.legacy_graph_port_invocation_budget == RuntimeBudget().graph_port_invocations == 40
    )
    assert report.legacy_whole_case_budget_passed is False
    assert all(case.expected_behavior_passed for case in report.cases)
    for case in report.cases:
        assert sum(item.invocation_calls for item in case.invocations) == (
            case.complete_scripted_interaction_calls
        )
        assert case.final_interrupted is case.invocations[-1].at_candidate_review
        assert case.candidate_action_count == len(case.candidate_actions)


def test_request_more_is_measured_within_one_case_not_inferred_from_another(
    report: InteractionBudgetReport,
) -> None:
    case = next(item for item in report.cases if item.scenario_id == "draft-graph-request-more")
    assert case.first_review_calls == 38
    assert case.complete_scripted_interaction_calls == 76
    assert [item.invocation_calls for item in case.invocations] == [38, 38]
    assert [item.cumulative_counts.total for item in case.invocations] == [38, 76]
    assert [item.invocation_index for item in case.invocations] == [0, 1]
    assert case.invocations[0].invocation_counts.memory_store == 0
    assert case.invocations[1].invocation_counts.memory_store == 1
    assert case.invocations[1].invocation_counts.memory_load == 0
    assert case.candidate_actions == (CandidateReviewAction.REQUEST_MORE,)
    assert case.final_review_status is ReviewStatus.PROPOSED
    assert case.final_interrupted is True
    assert case.legacy_whole_case_budget_passed is False


@pytest.mark.parametrize(
    ("scenario_id", "actions", "invocation_count", "completed"),
    (
        ("approval-required-before-persistence", (), 1, False),
        ("draft-graph-approve-one", (CandidateReviewAction.APPROVE,), 2, True),
        ("candidate-rejects-highly-theoretical", (CandidateReviewAction.REJECT,), 2, False),
        (
            "draft-graph-reject-then-approve",
            (CandidateReviewAction.REJECT, CandidateReviewAction.APPROVE),
            3,
            True,
        ),
    ),
)
def test_view_reject_and_approve_have_distinct_actual_boundaries(
    scenario_id: str,
    actions: tuple[CandidateReviewAction, ...],
    invocation_count: int,
    completed: bool,
    report: InteractionBudgetReport,
) -> None:
    case = next(item for item in report.cases if item.scenario_id == scenario_id)
    assert case.first_review_calls == 38
    assert len(case.invocations) == invocation_count
    assert case.candidate_actions == actions
    assert (case.final_review_status is ReviewStatus.COMPLETED) is completed
    assert case.final_interrupted is not completed
    assert case.invocations[0].invocation_counts.memory_store == 0


def test_terminal_before_review_is_not_reported_as_a_first_result(
    report: InteractionBudgetReport,
) -> None:
    raw = report.cases[0].model_dump(mode="json")
    raw["invocations"][0]["at_candidate_review"] = False
    raw["first_review_calls"] = None
    raw["final_interrupted"] = False
    raw["final_review_status"] = "evidence_incomplete"
    result = InteractionCaseMeasurement.model_validate(raw)
    assert result.first_review_calls is None
    assert result.complete_scripted_interaction_calls > 0
    raw["first_review_calls"] = result.complete_scripted_interaction_calls
    with pytest.raises(ValidationError):
        InteractionCaseMeasurement.model_validate(raw)


def test_round_trip_and_current_utc_date(report: InteractionBudgetReport) -> None:
    assert InteractionBudgetReport.model_validate_json(report.model_dump_json()) == report
    assert report.recorded_on == date(2026, 9, 6)
    before = datetime.now(UTC).date()
    actual = run_interaction_budget_diagnostic()
    assert before <= actual.recorded_on <= datetime.now(UTC).date()


def test_every_target_and_evaluator_is_untraced_even_with_optins_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for flag in (
        "LANGSMITH_TRACING",
        "SCHOLARPATH_RUN_LIVE_TESTS",
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
    ):
        monkeypatch.setattr(runner, name, _forbidden)
    target_ids: list[str] = []
    evaluations: list[bool] = []

    def checked_target(
        inputs: dict[str, object],
        *,
        invocation_usage_observer: Callable[[GraphInvocationObservation], None],
    ) -> dict[str, object]:
        assert get_tracing_context()["enabled"] is False
        scenario = inputs["scenario"]
        assert isinstance(scenario, dict) and "expected" not in scenario
        target_ids.append(str(scenario["scenario_id"]))
        return fake_end_to_end_target(inputs, invocation_usage_observer=invocation_usage_observer)

    def checked_evaluator(
        outputs: dict[str, object], reference_outputs: dict[str, object] | None = None
    ) -> object:
        assert get_tracing_context()["enabled"] is False
        assert reference_outputs is not None and "expected" in reference_outputs
        evaluations.append(True)
        return expected_behavior(outputs, reference_outputs)

    monkeypatch.setattr(interaction_budget, "fake_end_to_end_target", checked_target)
    monkeypatch.setattr(interaction_budget, "expected_behavior", checked_evaluator)
    manifest = build_reviewed_manifest()
    original = manifest.model_dump_json()
    with tracing_context(enabled=True):
        result = run_interaction_budget_diagnostic(manifest)
        assert get_tracing_context()["enabled"] is True
    assert manifest.model_dump_json() == original
    assert tuple(target_ids) == tuple(case.scenario_id for case in result.cases)
    assert len(evaluations) == 12


@pytest.mark.parametrize(
    "mutation",
    (
        "missing_observation",
        "duplicate_observation",
        "out_of_order",
        "unknown_total",
        "wrong_total",
        "wrong_id",
        "wrong_target",
        "wrong_expected_behavior",
    ),
)
def test_missing_or_invalid_observations_and_outcomes_fail_closed(
    mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def corrupted_target(
        inputs: dict[str, object],
        *,
        invocation_usage_observer: Callable[[GraphInvocationObservation], None],
    ) -> dict[str, object]:
        snapshots: list[GraphInvocationObservation] = []
        output = fake_end_to_end_target(inputs, invocation_usage_observer=snapshots.append)
        if mutation != "missing_observation":
            for snapshot in snapshots:
                if mutation == "out_of_order":
                    snapshot = snapshot.model_copy(update={"invocation_index": 1})
                invocation_usage_observer(snapshot)
        if mutation == "duplicate_observation":
            invocation_usage_observer(snapshots[-1])
        elif mutation == "unknown_total":
            output["measurements"] = {"port_invocations": None}
        elif mutation == "wrong_total":
            output["measurements"] = {"port_invocations": 0}
        elif mutation == "wrong_id":
            output["scenario_id"] = PRIVATE
        elif mutation == "wrong_target":
            output["target"] = "graph_live"
        elif mutation == "wrong_expected_behavior":
            output["interrupted"] = False
        return output

    monkeypatch.setattr(interaction_budget, "fake_end_to_end_target", corrupted_target)
    with pytest.raises((ValidationError, InteractionMeasurementError)):
        run_interaction_budget_diagnostic()


@pytest.mark.parametrize(
    "mutation",
    (
        "first_limit",
        "interaction_limit",
        "legacy_budget",
        "scope",
        "policy",
        "digest",
        "source_digest",
        "order",
        "decision",
        "private",
    ),
)
def test_report_rejects_unapproved_limits_relabelling_and_private_payloads(
    mutation: str, report: InteractionBudgetReport
) -> None:
    raw = report.model_dump(mode="json")
    if mutation == "first_limit":
        raw["first_review_limit"] = 40
    elif mutation == "interaction_limit":
        raw["full_interaction_limit"] = 80
    elif mutation == "legacy_budget":
        raw["legacy_graph_port_invocation_budget"] = 80
    elif mutation == "scope":
        raw["legacy_budget_scope"] = "per_round"
    elif mutation == "policy":
        raw["supplemental_policy_status"] = "approved"
    elif mutation == "digest":
        raw["content_digest"] = "0" * 64
    elif mutation == "source_digest":
        raw["source_draft_digest"] = "0" * 64
    elif mutation == "order":
        raw["cases"].reverse()
    elif mutation == "decision":
        raw["legacy_whole_case_budget_passed"] = True
    else:
        raw["research_statement"] = PRIVATE
    with pytest.raises(ValidationError):
        InteractionBudgetReport.model_validate(raw)


@pytest.mark.parametrize(
    "mutation",
    ("delta", "negative", "total", "first", "action_count", "outcome", "terminal_resume"),
)
def test_case_rejects_inconsistent_deltas_and_boundaries(
    mutation: str, report: InteractionBudgetReport
) -> None:
    case = next(item for item in report.cases if item.scenario_id == "draft-graph-request-more")
    raw = case.model_dump(mode="json")
    if mutation == "delta":
        raw["invocations"][1]["invocation_counts"]["memory_load"] = 1
        raw["invocations"][1]["invocation_calls"] += 1
    elif mutation == "negative":
        raw["invocations"][1]["cumulative_counts"]["planning"] = 0
    elif mutation == "total":
        raw["complete_scripted_interaction_calls"] = 38
    elif mutation == "first":
        raw["first_review_calls"] = 76
    elif mutation == "action_count":
        raw["candidate_action_count"] = 0
    elif mutation == "outcome":
        raw["expected_behavior_passed"] = False
    else:
        raw["invocations"][0]["at_candidate_review"] = False
        raw["first_review_calls"] = None
    with pytest.raises(ValidationError):
        InteractionCaseMeasurement.model_validate(raw)


def test_merged_resume_boundary_cannot_hide_an_accepted_action(
    report: InteractionBudgetReport,
) -> None:
    case = next(
        item for item in report.cases if item.scenario_id == "draft-graph-reject-then-approve"
    )
    raw = case.model_dump(mode="json")
    first, _, last = raw["invocations"]
    last["invocation_index"] = 1
    last["invocation_counts"] = {
        key: count - first["cumulative_counts"][key]
        for key, count in last["cumulative_counts"].items()
    }
    last["invocation_calls"] = sum(last["invocation_counts"].values())
    raw["invocations"] = [first, last]
    with pytest.raises(ValidationError, match="own measured resume"):
        InteractionCaseMeasurement.model_validate(raw)


def test_completed_status_cannot_disguise_a_review_pause(
    report: InteractionBudgetReport,
) -> None:
    raw = report.cases[0].model_dump(mode="json")
    raw["final_review_status"] = "completed"
    with pytest.raises(ValidationError, match="proposed review status"):
        InteractionCaseMeasurement.model_validate(raw)


def test_rendered_output_contains_only_safe_counts_and_controlled_labels(
    report: InteractionBudgetReport,
) -> None:
    text = render_interaction_budget_report(report)
    assert "first review=38; complete interaction=76/40 [exceeded]" in text
    assert "invocation calls=[38, 38]" in text
    assert "full interaction=not configured" in text
    assert "may end paused" in text
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
def test_cli_preserves_legacy_budget_exit_one(
    output_format: str,
    report: InteractionBudgetReport,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(interaction_budget, "run_interaction_budget_diagnostic", lambda: report)
    assert main(["--format", output_format]) == 1
    captured = capsys.readouterr()
    assert captured.err == ""
    if output_format == "json":
        output = json.loads(captured.out)
        assert output["legacy_whole_case_budget_passed"] is False
        assert output["first_review_limit"] is output["full_interaction_limit"] is None
    else:
        assert "76/40 [exceeded]" in captured.out


def test_cli_can_report_pass_without_raising_the_legacy_limit(
    report: InteractionBudgetReport,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Test-only observation, not a change to the frozen case or its fixture behavior.
    raw = report.model_dump(mode="json")
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
    passing = InteractionBudgetReport.model_validate(raw)
    monkeypatch.setattr(interaction_budget, "run_interaction_budget_diagnostic", lambda: passing)
    assert main([]) == 0
    assert "39/40 [pass]" in capsys.readouterr().out


def test_cli_sanitizes_exceptions_and_restores_trace_context(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def failure(*args: object, **kwargs: object) -> Never:
        del args, kwargs
        assert get_tracing_context()["enabled"] is False
        raise RuntimeError(PRIVATE)

    monkeypatch.setattr(interaction_budget, "fake_end_to_end_target", failure)
    with tracing_context(enabled=True):
        assert main([]) == 2
        assert get_tracing_context()["enabled"] is True
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.strip() == "The offline interaction measurement could not complete safely."


@pytest.mark.parametrize("option", ("--live", "--upload", "--write", "--budget"))
def test_cli_has_no_network_write_or_budget_override_options(option: str) -> None:
    with pytest.raises(SystemExit) as error:
        main([option])
    assert error.value.code == 2


def test_script_delegates_to_cli_without_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(interaction_budget, "main", lambda: 1)
    script = Path(__file__).resolve().parents[3] / "scripts" / "inspect_interaction_budget.py"
    with pytest.raises(SystemExit) as error:
        runpy.run_path(str(script), run_name="__main__")
    assert error.value.code == 1
