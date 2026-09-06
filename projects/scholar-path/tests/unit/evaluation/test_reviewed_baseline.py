"""Reviewed expected behaviors do not turn fake observations into live quality claims."""

import json
from pathlib import Path
from typing import Never

import pytest
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context

from scholarpath.evaluation import reviewed_baseline, runner
from scholarpath.evaluation.draft_models import EvaluationDraft
from scholarpath.evaluation.draft_scenarios import build_evaluation_draft
from scholarpath.evaluation.reviewed_baseline import ReviewedBaselineReport, run_reviewed_baseline
from scholarpath.evaluation.reviewed_manifest import (
    ReviewedEvaluationManifest,
    build_reviewed_manifest,
)
from scholarpath.evaluation.scenarios import EVALUATION_DATASET_NAME, EVALUATION_SCENARIOS


@pytest.fixture(scope="module")
def report() -> ReviewedBaselineReport:
    return run_reviewed_baseline(build_reviewed_manifest())


def _forbidden_execution(*args: object, **kwargs: object) -> Never:
    raise AssertionError("Local reviewed evaluation must not invoke external operations")


def test_reviewed_baseline_retains_the_known_correctness_and_runtime_gaps(
    report: ReviewedBaselineReport,
) -> None:
    manifest = build_reviewed_manifest()
    assert report.scenario_count == 30
    assert report.passed_scenario_count == 29
    assert report.passed is False
    assert report.runtime_budgets_passed is False
    assert tuple(item.scenario_id for item in report.scenarios) == tuple(
        case.scenario.scenario_id for case in manifest.source_draft.cases
    )
    assert [(item.scenario_id, item.key, item.category) for item in report.failures] == [
        ("draft-evidence-heading-bound-research", "expected_behavior", "metric_failed")
    ]
    graph_runtime = next(item for item in report.runtime_summaries if item.target == "graph_fake")
    assert graph_runtime.maximum_port_invocations == 76
    assert graph_runtime.invocation_budget == 40
    assert graph_runtime.invocation_budget_passed is False
    assert report.runtime_budget.graph_port_invocations == 40
    assert max(item.runtime.port_invocations or 0 for item in report.scenarios) == 76


def test_report_uses_separate_reviewed_identity_and_round_trips(
    report: ReviewedBaselineReport,
) -> None:
    manifest = build_reviewed_manifest()
    restored = ReviewedBaselineReport.model_validate_json(report.model_dump_json())

    assert restored == report
    assert report.dataset_name == "scholarpath-week4-30case-reviewed-v1"
    assert report.reviewed_version == "week4-30case-reviewed-v1"
    assert report.baseline_name.startswith("scholarpath-week4-reviewed-local-")
    assert report.dataset_name != EVALUATION_DATASET_NAME
    assert report.content_digest == manifest.content_digest
    assert report.source_draft_digest == manifest.source_draft.content_digest
    assert report.source_draft_digest == build_evaluation_draft().content_digest
    assert report.approval_scope == "expected_behaviors"
    assert report.execution_mode == "fake_only"
    serialized = report.model_dump_json()
    for forbidden in (
        "candidate_id",
        "proposed_research_statement",
        "supporting_excerpt",
        "source_url",
        "api_key",
        "full_page_content",
    ):
        assert f'"{forbidden}"' not in serialized


def test_missing_runtime_observations_are_unknown_not_a_correctness_pass(
    report: ReviewedBaselineReport,
) -> None:
    unknown_runtime = report.model_copy(update={"runtime_summaries": ()})

    assert unknown_runtime.runtime_budgets_passed is None
    assert unknown_runtime.passed is False
    assert unknown_runtime.passed_scenario_count == 29


def test_reviewed_run_is_offline_even_with_live_flags_and_tracing_enabled(
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
        monkeypatch.setattr(runner, name, _forbidden_execution)
    real_dispatch = runner.dispatch_evaluation_target
    observed_scenarios: list[str] = []

    def checked_dispatch(inputs: dict[str, object], *, live: bool = False) -> dict[str, object]:
        assert get_tracing_context()["enabled"] is False
        assert live is False
        scenario = inputs["scenario"]
        assert isinstance(scenario, dict)
        observed_scenarios.append(str(scenario["scenario_id"]))
        return real_dispatch(inputs, live=live)

    monkeypatch.setattr(runner, "dispatch_evaluation_target", checked_dispatch)
    manifest = build_reviewed_manifest()
    manifest_snapshot = manifest.model_dump_json()
    draft_snapshot = build_evaluation_draft().model_dump_json()
    original_scenarios = tuple(item.model_dump_json() for item in EVALUATION_SCENARIOS)

    with tracing_context(enabled=True):
        result = run_reviewed_baseline(manifest)
        assert get_tracing_context()["enabled"] is True

    assert result.scenario_count == 30
    assert result.passed_scenario_count == 29
    assert len(observed_scenarios) == len(set(observed_scenarios)) == 30
    assert manifest.model_dump_json() == manifest_snapshot
    assert build_evaluation_draft().model_dump_json() == draft_snapshot
    assert tuple(item.model_dump_json() for item in EVALUATION_SCENARIOS) == original_scenarios


@pytest.mark.parametrize("mutation", ["identity", "expected_label", "execution_config"])
def test_tampered_manifest_is_rejected_before_target_execution(
    mutation: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest = build_reviewed_manifest()
    if mutation == "identity":
        corrupted = manifest.model_copy(update={"dataset_name": "unapproved-dataset"})
    else:
        raw_draft = manifest.source_draft.model_dump(mode="json")
        if mutation == "expected_label":
            raw_draft["cases"][0]["scenario"]["expected"]["minimum_research_fit_score"] = 0
        else:
            raw_draft["cases"][0]["scenario"]["config"]["unapproved_option"] = True
        corrupted = manifest.model_copy(
            update={"source_draft": EvaluationDraft.model_validate(raw_draft)}
        )
    monkeypatch.setattr(reviewed_baseline, "run_local_baseline", _forbidden_execution)

    with pytest.raises(ValueError):
        run_reviewed_baseline(corrupted)


@pytest.mark.parametrize("argv", [[], ["--format", "json"]])
def test_cli_preview_never_runs_targets(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(reviewed_baseline, "run_reviewed_baseline", _forbidden_execution)
    monkeypatch.setattr(runner, "dispatch_evaluation_target", _forbidden_execution)

    assert reviewed_baseline.main(argv) == 0

    output = capsys.readouterr().out
    manifest = build_reviewed_manifest()
    assert manifest.dataset_name in output
    assert manifest.content_digest in output
    if argv:
        decoded = json.loads(output)
        assert decoded["content_digest"] == manifest.content_digest
        assert decoded["approval_scope"] == "expected_behaviors"
        assert len(decoded["source_draft"]["cases"]) == 30
    else:
        assert "No targets executed" in output


@pytest.mark.parametrize("output_format", ["text", "json"])
def test_cli_check_keeps_nonzero_correctness_result_and_runtime_separate(
    output_format: str,
    report: ReviewedBaselineReport,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    supplied_digests: list[str] = []

    def fixed_result(manifest: ReviewedEvaluationManifest) -> ReviewedBaselineReport:
        supplied_digests.append(manifest.content_digest)
        return report

    monkeypatch.setattr(reviewed_baseline, "run_reviewed_baseline", fixed_result)

    assert reviewed_baseline.main(["--check", "--format", output_format]) == 1

    output = capsys.readouterr().out
    assert supplied_digests == [report.content_digest]
    assert "draft-evidence-heading-bound-research" in output
    if output_format == "json":
        decoded = ReviewedBaselineReport.model_validate_json(output)
        assert decoded == report
        assert decoded.passed is False
        assert decoded.runtime_budgets_passed is False
    else:
        assert "Offline checks: 29/30 passed" in output
        assert "FAIL draft-evidence-heading-bound-research: expected_behavior" in output
        assert "max=76.000; budget=40.000 [exceeded]" in output
        assert "runtime is reported separately" in output


@pytest.mark.parametrize(
    "argv",
    [
        ["--upload"],
        ["--live"],
        ["--include-llm-judges"],
        ["--output", "unrequested.json"],
        ["--enforce-runtime-budgets"],
        ["--format", "invalid-format"],
    ],
)
def test_cli_rejects_external_and_write_options(
    argv: list[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(reviewed_baseline, "run_reviewed_baseline", _forbidden_execution)

    with pytest.raises(SystemExit) as raised:
        reviewed_baseline.main(argv)

    assert raised.value.code == 2


def test_saved_manifest_and_baseline_are_linked_without_hiding_known_failure() -> None:
    documents = Path(__file__).resolve().parents[3] / "docs" / "evaluation"
    manifest = build_reviewed_manifest()
    saved_manifest = json.loads(
        (documents / "week4-30case-reviewed-v1.json").read_text(encoding="utf-8")
    )
    saved_report = ReviewedBaselineReport.model_validate_json(
        (documents / "week4-reviewed-baseline-2026-09-06.json").read_text(encoding="utf-8")
    )

    assert saved_manifest == {
        **manifest.model_dump(mode="json"),
        "content_digest": manifest.content_digest,
    }
    assert saved_report.content_digest == saved_manifest["content_digest"]
    assert saved_report.source_draft_digest == manifest.source_draft.content_digest
    assert saved_report.dataset_name == manifest.dataset_name
    assert saved_report.scenario_count == len(saved_report.scenarios) == 30
    assert saved_report.passed_scenario_count == 29
    assert saved_report.passed is False
    assert saved_report.runtime_budgets_passed is False
    assert [(item.scenario_id, item.key) for item in saved_report.failures] == [
        ("draft-evidence-heading-bound-research", "expected_behavior")
    ]
