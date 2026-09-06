"""Saved count-only observations agree with a fresh execution of the frozen cases."""

from datetime import date
from pathlib import Path

from scholarpath.evaluation.interaction_budget import (
    InteractionBudgetReport,
    run_interaction_budget_diagnostic,
)


def test_saved_interaction_measurements_match_fresh_execution() -> None:
    saved = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "evaluation"
        / "week4-interaction-measurements-2026-09-06.json"
    )
    recorded = InteractionBudgetReport.model_validate_json(saved.read_text(encoding="utf-8"))
    actual = run_interaction_budget_diagnostic(recorded_on=date(2026, 9, 6))
    assert actual == recorded
