"""Check ledger arithmetic and provenance without replaying private or live data."""

import re
from pathlib import Path

import pytest

from scholarpath.evaluation.reviewed_baseline import ReviewedBaselineReport

DOCS = Path(__file__).resolve().parents[2] / "docs"
LEDGER = DOCS / "week4-improvement-ledger.md"


@pytest.mark.parametrize(
    ("step", "before", "after", "size"),
    (("3g", 0, 5, 5), ("3k", 17, 30, 30), ("3t", 42, 56, 56), ("3ag", 29, 30, 30)),
)
def test_comparison_rows_use_fixed_denominators_and_correct_deltas(
    step: str, before: int, after: int, size: int
) -> None:
    row = next(line for line in LEDGER.read_text().splitlines() if line.startswith(f"| {step} —"))
    cells = [cell.strip() for cell in row.strip("|").split("|")]

    assert cells[1:3] == [f"{before}/{size}", f"{after}/{size}"]
    assert cells[3] == f"+{after - before}"
    assert cells[4] == f"+{100 * (after - before) / size:.2f} pp"


@pytest.mark.parametrize(
    ("step", "recorded_red", "recorded_green"),
    (
        ("3g", ("5 failed, 103 deselected",), "5 passed, 103 deselected"),
        ("3k", ("5 failed, 14 passed", "8 failed, 3 passed"), "30 passed in 0.25s"),
        ("3t", ("14 failed, 42 passed",), "425 passed in 0.74s"),
    ),
)
def test_focused_before_results_remain_linked_to_historical_journal(
    step: str, recorded_red: tuple[str, ...], recorded_green: str
) -> None:
    journal = (DOCS / "build-journal.md").read_text()
    section = journal.split(f"## Week 4 step {step} —", 1)[1].split("\n## ", 1)[0]

    assert all(observation in section for observation in recorded_red)
    assert recorded_green in section
    assert f"build-journal.md#week-4-step-{step}--" in LEDGER.read_text()


def test_only_the_golden_row_claims_saved_reviewed_comparison() -> None:
    before = ReviewedBaselineReport.model_validate_json(
        (DOCS / "evaluation/week4-reviewed-baseline-2026-09-06.json").read_text()
    )
    after = ReviewedBaselineReport.model_validate_json(
        (DOCS / "evaluation/week4-heading-grounding-after-2026-09-06.json").read_text()
    )
    assert before.content_digest == after.content_digest
    assert before.scenario_count == after.scenario_count == 30
    assert (before.passed_scenario_count, after.passed_scenario_count) == (29, 30)
    assert len(before.failures) == 1
    assert before.failures[0].scenario_id == "draft-evidence-heading-bound-research"
    assert after.failures == ()
    ledger = re.sub(r"\s+", " ", LEDGER.read_text())
    for qualification in (
        "not three additional golden-dataset gains",
        "journal-recorded observations",
        "no isolated committed pre-repair snapshots",
        "retrospective",
        "Do not sum these denominators or gains",
        "zero calls saved",
        "76/40",
        "Live quality/cost remain unmeasured",
        "report and recording are still required",
    ):
        assert qualification in ledger
