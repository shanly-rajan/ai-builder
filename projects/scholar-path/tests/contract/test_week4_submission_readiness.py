"""Keep the current submission handoff linked to recorded evidence, not invented wins."""

import json
import re
from pathlib import Path

import pytest

from scholarpath.evaluation.interaction_policy_report import InteractionPolicyReport
from scholarpath.evaluation.reviewed_baseline import ReviewedBaselineReport

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DOCS = PROJECT_ROOT / "docs"
SCORECARD = DOCS / "week4-submission-readiness.md"


@pytest.mark.parametrize(
    "relative_path",
    (
        "README.md",
        "docs/week4-submission-readiness.md",
        "docs/week4-triage.md",
        "docs/prompts/week4-3ak-submission-evidence-check.md",
    ),
)
def test_current_handoff_relative_links_resolve(relative_path: str) -> None:
    document = PROJECT_ROOT / relative_path
    for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", document.read_text()):
        relative_target = target.split("#", 1)[0]
        if not relative_target or relative_target.startswith(("https://", "http://")):
            continue
        assert (document.parent / relative_target).resolve().exists(), target


def test_scorecard_comparison_matches_saved_frozen_artifacts() -> None:
    before = ReviewedBaselineReport.model_validate_json(
        (DOCS / "evaluation/week4-reviewed-baseline-2026-09-06.json").read_text()
    )
    after = ReviewedBaselineReport.model_validate_json(
        (DOCS / "evaluation/week4-heading-grounding-after-2026-09-06.json").read_text()
    )
    scorecard = SCORECARD.read_text()

    assert before.content_digest == after.content_digest
    assert before.content_digest in scorecard
    assert before.dataset_name == after.dataset_name
    assert before.dataset_name in scorecard
    assert before.scenario_count == after.scenario_count == 30
    assert (before.passed_scenario_count, after.passed_scenario_count) == (29, 30)
    assert "29/30 (96.67%)" in scorecard
    assert "30/30 (100%)" in scorecard
    assert "+1 case, +3.33 percentage points" in scorecard
    assert len(before.failures) == 1
    assert before.failures[0].scenario_id == "draft-evidence-heading-bound-research"
    assert after.failures == ()
    failed_case = next(
        item
        for item in before.scenarios
        if item.scenario_id == "draft-evidence-heading-bound-research"
    )
    assert failed_case.runtime.port_invocations == 1
    assert "failing case used one fake port call" in scorecard
    for report in (before, after):
        graph = next(item for item in report.runtime_summaries if item.target == "graph_fake")
        assert (graph.maximum_port_invocations, graph.invocation_budget) == (76, 40)
        assert not graph.invocation_budget_passed
        assert f"{graph.p95_target_seconds:.6f} s" in scorecard


def test_scorecard_keeps_paused_and_completed_policy_results_separate() -> None:
    report = InteractionPolicyReport.model_validate_json(
        (DOCS / "evaluation/week4-interaction-policy-2026-09-06.json").read_text()
    )
    scorecard = SCORECARD.read_text()
    assert report.summary.first_review_passed == 12
    assert report.summary.completed_interaction_passed == 3
    assert report.summary.within_budget_so_far == 9
    assert report.summary.legacy_whole_case_failures == 1
    for phrase in (
        "12 first-review passes",
        "3 completed interactions within",
        "9 paused within budget so far",
        "zero calls saved",
    ):
        assert phrase in scorecard


def test_scorecard_distinguishes_uploaded_before_from_local_after() -> None:
    recorded = json.loads(
        (DOCS / "evaluation/week4-reviewed-langsmith-baseline-2026-09-06.json").read_text()
    )
    assert recorded["example_count"] == 30
    assert recorded["failed_example_count"] == 1
    scorecard = SCORECARD.read_text()
    assert "Submission incomplete" in scorecard
    assert "after upload still pending" in scorecard
    assert "remaining 2–3 targeted improvements is incomplete" in scorecard
    assert "no Windows runner evidence" in scorecard
    assert "short Loom" in scorecard
    assert "No new live check is needed" in scorecard


def test_readme_and_triage_point_to_current_status_without_rewriting_history() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text()
    triage = (DOCS / "week4-triage.md").read_text()
    assert "docs/week4-submission-readiness.md" in readme
    assert "[submission evidence scorecard](week4-submission-readiness.md)" in triage
    assert "Current checkpoint: step 3ak" in triage
    assert "Incomplete: after-experiment trace comparison" in readme
    assert "historical records" in SCORECARD.read_text()
