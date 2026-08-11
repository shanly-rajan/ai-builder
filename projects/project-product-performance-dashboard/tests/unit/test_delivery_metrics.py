"""Unit tests for project delivery calculations."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.services.delivery_metrics import (
    active_days_overdue,
    calculate_delivery_metrics,
    inclusive_duration_days,
    schedule_variance_days,
    summarize_delivery,
)


def _projects() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project_id": "early",
                "status": "Complete",
                "planned_start_date": "2025-01-01",
                "planned_completion_date": "2025-01-10",
                "actual_start_date": "2025-01-01",
                "actual_completion_date": "2025-01-08",
            },
            {
                "project_id": "on-time",
                "status": "Complete",
                "planned_start_date": "2025-02-01",
                "planned_completion_date": "2025-02-01",
                "actual_start_date": "2025-02-01",
                "actual_completion_date": "2025-02-01",
            },
            {
                "project_id": "late",
                "status": "Complete",
                "planned_start_date": "2025-03-01",
                "planned_completion_date": "2025-03-10",
                "actual_start_date": "2025-03-02",
                "actual_completion_date": "2025-03-15",
            },
            {
                "project_id": "overdue",
                "status": "In Progress",
                "planned_start_date": "2025-04-01",
                "planned_completion_date": "2025-04-10",
                "actual_start_date": "2025-04-01",
                "actual_completion_date": pd.NaT,
            },
            {
                "project_id": "cancelled",
                "status": "Cancelled",
                "planned_start_date": "2025-04-01",
                "planned_completion_date": "2025-04-05",
                "actual_start_date": "2025-04-01",
                "actual_completion_date": pd.NaT,
            },
        ]
    )


def test_scalar_duration_and_variance_semantics() -> None:
    assert inclusive_duration_days("2025-01-01", "2025-01-01") == 1
    assert inclusive_duration_days("2025-01-01", "2025-01-10") == 10
    assert math.isnan(inclusive_duration_days(None, "2025-01-10"))
    assert schedule_variance_days("2025-01-10", "2025-01-08") == -2
    assert math.isnan(schedule_variance_days("2025-01-10", None))
    with pytest.raises(ValueError, match="cannot precede"):
        inclusive_duration_days("2025-01-02", "2025-01-01")


def test_active_overdue_uses_explicit_reporting_date() -> None:
    assert active_days_overdue("2025-01-01", as_of="2025-01-11") == 10
    assert active_days_overdue("2025-02-01", as_of="2025-01-11") == 0
    assert math.isnan(
        active_days_overdue("2025-01-01", as_of="2025-01-11", actual_completion="2025-01-05")
    )


def test_calculate_delivery_metrics_keeps_incomplete_variance_unavailable() -> None:
    result = calculate_delivery_metrics(_projects(), as_of="2025-04-20").set_index("project_id")

    assert result.loc["early", "planned_duration_days"] == 10
    assert result.loc["early", "actual_duration_days"] == 8
    assert result.loc["early", "schedule_variance_days"] == -2
    assert result.loc["early", "schedule_variance_pct"] == pytest.approx(-20)
    assert result.loc["on-time", "planned_duration_days"] == 1
    assert result.loc["on-time", "delivery_outcome"] == "on_time"
    assert result.loc["late", "delivery_outcome"] == "late"
    assert math.isnan(result.loc["overdue", "schedule_variance_days"])
    assert math.isnan(result.loc["overdue", "actual_duration_days"])
    assert result.loc["overdue", "days_overdue"] == 10
    assert result.loc["overdue", "delivery_outcome"] == "active_overdue"
    assert result.loc["cancelled", "delivery_outcome"] == "cancelled"


def test_delivery_summary_excludes_cancelled_and_counts_early_as_on_time() -> None:
    result = calculate_delivery_metrics(_projects(), as_of="2025-04-20")
    summary = summarize_delivery(result)

    assert summary["completed_projects"] == 3
    assert summary["on_time_projects"] == 2
    assert summary["on_time_delivery_pct"] == pytest.approx(200 / 3)
    assert summary["active_overdue_projects"] == 1
    assert summary["cancelled_projects"] == 1
    assert summary["average_schedule_variance_days"] == pytest.approx(1)


def test_invalid_project_date_ranges_are_rejected() -> None:
    projects = _projects().iloc[[0]].copy()
    projects.loc[:, "planned_completion_date"] = "2024-12-31"
    with pytest.raises(ValueError, match="planned completion precedes"):
        calculate_delivery_metrics(projects, as_of="2025-04-20")

    projects = _projects().iloc[[0]].copy()
    projects.loc[:, "actual_start_date"] = pd.NaT
    with pytest.raises(ValueError, match="requires an actual start"):
        calculate_delivery_metrics(projects, as_of="2025-04-20")
