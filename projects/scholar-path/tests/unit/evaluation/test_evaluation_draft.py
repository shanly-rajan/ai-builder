"""Draft labels are explicit, distinct, offline, and not human-approved ground truth."""

import hashlib
import json
from collections import Counter
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholarpath.evaluation import draft_review, runner
from scholarpath.evaluation.draft_models import (
    DraftEvaluationCase,
    EvaluationDraft,
    executable_case_fingerprint,
)
from scholarpath.evaluation.draft_review import main, render_review_table, run_draft_checks
from scholarpath.evaluation.draft_scenarios import (
    DRAFT_DATASET_NAME,
    DRAFT_SCENARIO_VERSION,
    build_evaluation_draft,
)
from scholarpath.evaluation.models import EvaluationTargetKind
from scholarpath.evaluation.scenarios import (
    EVALUATION_DATASET_NAME,
    EVALUATION_SCENARIOS,
    evaluation_dataset_inputs,
    evaluation_dataset_reference_outputs,
)


def test_original_eleven_scenarios_are_preserved_byte_for_byte() -> None:
    snapshot = json.dumps(
        [case.model_dump(mode="json") for case in EVALUATION_SCENARIOS], sort_keys=True
    )
    assert hashlib.sha256(snapshot.encode()).hexdigest() == (
        "d86374ba9cc97f75d1fac5c430278824204cd5c9658fe7a29d23bef042da1fb3"
    )
    assert (
        tuple(case.scenario for case in build_evaluation_draft().cases[:11]) == EVALUATION_SCENARIOS
    )
    assert EVALUATION_DATASET_NAME == "scholarpath-week4-regression-v1"
    assert build_evaluation_draft().dataset_name != EVALUATION_DATASET_NAME


def test_draft_has_thirty_distinct_executable_cases_and_required_mix() -> None:
    draft = build_evaluation_draft()
    assert len(draft.cases) == 30
    assert len({executable_case_fingerprint(case.scenario) for case in draft.cases}) == 30
    assert Counter(case.scenario_type.value for case in draft.cases) == {
        "happy": 15,
        "edge": 9,
        "known_failure": 4,
        "adversarial": 2,
    }
    assert Counter(case.origin for case in draft.cases) == {
        "retained_v1": 11,
        "new_synthetic_fixture": 19,
    }
    assert {case.scenario.target for case in draft.cases} == {
        EvaluationTargetKind.SEARCH_PLANNING,
        EvaluationTargetKind.EVIDENCE_VERIFICATION,
        EvaluationTargetKind.RESEARCH_FIT,
        EvaluationTargetKind.GRAPH_FAKE,
    }


def test_pending_review_is_not_confused_with_five_starting_outcome_acknowledgments() -> None:
    draft = build_evaluation_draft()
    assert draft.status == "pending_human_review"
    assert all(case.human_review_status == "pending" for case in draft.cases)
    assert all(case.reviewer is None and case.reviewed_at is None for case in draft.cases)
    acknowledged = {
        case.scenario.scenario_id
        for case in draft.cases
        if case.starting_outcome_previously_acknowledged
    }
    assert acknowledged == {
        "strong-research-alignment",
        "superficial-keyword-poor-fit",
        "evidence-extraction-failure",
        "you-timeout-tavily-fallback",
        "candidate-rejects-highly-theoretical",
    }
    for case in draft.cases:
        assert case.label_rationale and case.source_reference and case.source_version
        assert case.label_author == "engineering_draft"


@pytest.mark.parametrize(
    "case", build_evaluation_draft().cases, ids=lambda case: case.scenario.scenario_id
)
def test_each_label_round_trips_and_is_not_passed_to_the_target(case: DraftEvaluationCase) -> None:
    assert DraftEvaluationCase.model_validate_json(case.model_dump_json()) == case
    inputs = evaluation_dataset_inputs(case.scenario)
    references = evaluation_dataset_reference_outputs(case.scenario)
    scenario_input = inputs["scenario"]
    assert isinstance(scenario_input, dict)
    assert "expected" not in scenario_input
    assert set(references) == {"expected"}
    assert "human_review_status" not in scenario_input


def test_manifest_round_trip_and_content_digest_are_reproducible() -> None:
    draft = build_evaluation_draft()
    assert EvaluationDraft.model_validate_json(draft.model_dump_json()) == draft
    assert draft.content_digest == build_evaluation_draft().content_digest
    assert draft.draft_version == DRAFT_SCENARIO_VERSION
    raw = draft.model_dump(mode="json")
    raw["cases"][0]["label_rationale"] += " Review note."
    assert EvaluationDraft.model_validate(raw).content_digest != draft.content_digest


@pytest.mark.parametrize(
    "mutation",
    ["duplicate_id", "duplicate_recipe", "wrong_mix", "live", "reviewed", "new_acknowledgment"],
)
def test_draft_rejects_invalid_provenance_or_execution_scope(mutation: str) -> None:
    raw = build_evaluation_draft().model_dump(mode="json")
    cases = raw["cases"]
    if mutation == "duplicate_id":
        cases[1]["scenario"]["scenario_id"] = cases[0]["scenario"]["scenario_id"]
    elif mutation == "duplicate_recipe":
        for key in ("target", "candidate_preferences", "inputs", "config"):
            cases[1]["scenario"][key] = cases[0]["scenario"][key]
    elif mutation == "wrong_mix":
        cases[0]["scenario_type"] = "edge"
    elif mutation == "live":
        cases[0]["scenario"]["target"] = "graph_live"
    elif mutation == "reviewed":
        cases[0]["human_review_status"] = "approved"
    else:
        cases[11]["starting_outcome_previously_acknowledged"] = True
        cases[11]["starting_outcome_reference"] = "invented-review"
    with pytest.raises(ValidationError):
        EvaluationDraft.model_validate(raw)


def _unexpected_external_call(*args: object, **kwargs: object) -> None:
    raise AssertionError("Draft inspection/checks must never call an external service")


def test_current_thirty_offline_checks_pass_without_rewriting_pending_draft_labels(
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
        monkeypatch.setattr(runner, name, _unexpected_external_call)
    draft = build_evaluation_draft()
    report = run_draft_checks(draft)
    # Production grounding now satisfies the same unchanged heading expectation.
    # A passing current check must not rewrite the historical draft provenance.
    assert report.passed
    assert report.passed_scenario_count == 30
    assert report.scenario_count == 30
    assert report.failures == ()
    assert report.dataset_name == DRAFT_DATASET_NAME
    assert report.human_review_status == "pending_human_review"
    graph_runtime = next(item for item in report.runtime_summaries if item.target == "graph_fake")
    assert graph_runtime.maximum_port_invocations == 76
    assert graph_runtime.invocation_budget == 40
    assert graph_runtime.invocation_budget_passed is False
    assert draft == build_evaluation_draft()


def test_incorrect_declared_label_causes_a_failed_check() -> None:
    raw = build_evaluation_draft().model_dump(mode="json")
    raw["cases"][2]["scenario"]["expected"]["expected_availability_status"] = "confirmed_accepting"
    report = run_draft_checks(EvaluationDraft.model_validate(raw))
    assert not report.passed
    assert any(failure.scenario_id == "availability-not-stated" for failure in report.failures)


def test_cli_check_reports_current_correctness_pass_and_runtime_limit_separately(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["--check"]) == 0
    output = capsys.readouterr().out
    assert "Offline checks: 30/30 passed" in output
    assert "FAIL " not in output
    assert "max=76.000; budget=40.000 [exceeded]" in output
    assert "pending_human_review" in output
    assert "--enforce-runtime-budgets" not in output


def test_cli_still_returns_nonzero_for_an_incorrect_expected_outcome(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    raw = build_evaluation_draft().model_dump(mode="json")
    raw["cases"][2]["scenario"]["expected"]["expected_availability_status"] = "confirmed_accepting"
    failing_report = run_draft_checks(EvaluationDraft.model_validate(raw))
    monkeypatch.setattr(draft_review, "run_draft_checks", lambda _: failing_report)

    assert main(["--check"]) == 1
    output = capsys.readouterr().out
    assert "Offline checks: 29/30 passed" in output
    assert "FAIL availability-not-stated: expected_behavior" in output


@pytest.mark.parametrize(
    "argv", [[], ["--format", "json"], ["--case", "strong-research-alignment"]]
)
def test_cli_preview_does_not_run_targets(
    argv: list[str], monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(runner, "dispatch_evaluation_target", _unexpected_external_call)
    assert main(argv) == 0
    assert "pending" in capsys.readouterr().out


@pytest.mark.parametrize(
    "argv",
    [
        ["--upload"],
        ["--live"],
        ["--include-llm-judges"],
        ["--case", "unknown"],
        ["--check", "--format", "json"],
    ],
)
def test_cli_rejects_live_upload_and_invalid_options(argv: list[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        main(argv)
    assert raised.value.code == 2


def test_table_contains_every_case_and_explicit_review_boundary() -> None:
    draft = build_evaluation_draft()
    table = render_review_table(draft)
    assert "All detailed labels await human review" in table
    assert draft.content_digest in table
    for case in draft.cases:
        assert case.scenario.scenario_id in table
        assert case.label_rationale in table
    guide = Path(__file__).resolve().parents[3] / "docs" / "week4-evaluation-draft.md"
    assert table.replace("# ", "### ", 1) in guide.read_text(encoding="utf-8")
