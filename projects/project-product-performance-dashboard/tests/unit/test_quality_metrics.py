"""Unit tests for test metrics and release readiness."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.services.portfolio_metrics import summarize_quality_portfolio
from src.services.quality_metrics import (
    assess_release_readiness,
    calculate_defect_metrics,
    calculate_quality_metrics,
    calculate_quality_rates,
)


def test_blocked_tests_are_executed_but_not_passed() -> None:
    metrics = calculate_quality_rates(passed=6, failed=2, blocked=2, not_run=10)
    assert metrics["total"] == 20
    assert metrics["executed"] == 10
    assert metrics["execution_rate_pct"] == 50
    assert metrics["pass_rate_pct"] == 60

    empty = calculate_quality_rates(passed=0, failed=0, blocked=0, not_run=0)
    assert math.isnan(empty["execution_rate_pct"])
    assert math.isnan(empty["pass_rate_pct"])


def test_granular_quality_metrics_support_project_and_category_groups() -> None:
    cases = pd.DataFrame(
        [
            {"project_id": "P1", "test_category": "Unit", "status": "Passed"},
            {"project_id": "P1", "test_category": "Unit", "status": "Blocked"},
            {"project_id": "P1", "test_category": "System", "status": "Not Run"},
            {"project_id": "P2", "test_category": "Unit", "status": "Failed"},
        ]
    )
    project = calculate_quality_metrics(cases).set_index("project_id")
    assert project.loc["P1", "total"] == 3
    assert project.loc["P1", "executed"] == 2
    assert project.loc["P1", "execution_rate_pct"] == pytest.approx(200 / 3)
    assert project.loc["P1", "pass_rate_pct"] == 50

    categories = calculate_quality_metrics(cases, group_columns=("project_id", "test_category"))
    assert len(categories) == 3


def test_portfolio_quality_rates_are_recomputed_from_counts() -> None:
    groups = pd.DataFrame(
        [
            {
                "passed": 1,
                "failed": 0,
                "blocked": 0,
                "not_run": 0,
                "total": 1,
                "executed": 1,
            },
            {
                "passed": 1,
                "failed": 8,
                "blocked": 0,
                "not_run": 0,
                "total": 9,
                "executed": 9,
            },
        ]
    )
    summary = summarize_quality_portfolio(groups)
    assert summary["execution_rate_pct"] == 100
    assert summary["pass_rate_pct"] == 20


def _requirements(project_ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project_id": project_id,
                "test_category": "Unit",
                "applicable": True,
                "required": True,
            }
            for project_id in project_ids
        ]
    )


def _assessments(project_ids: list[str]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "project_id": project_id,
                "uat_applicable": project_id == "uat-waiting",
                "uat_status": "In Progress" if project_id == "uat-waiting" else "Not Applicable",
                "actual_release_date": (
                    "2025-03-01" if project_id == "released-with-failure" else pd.NaT
                ),
                "release_exception_approved": project_id == "released-with-failure",
            }
            for project_id in project_ids
        ]
    )


def test_release_readiness_exposes_each_gate_and_release_exception() -> None:
    planned_projects = [
        "ready",
        "testing",
        "failed",
        "blocked-defect",
        "uat-waiting",
        "released-with-failure",
    ]
    all_projects = [*planned_projects, "missing-plan"]
    requirements = _requirements(planned_projects)
    cases = pd.DataFrame(
        [
            {"project_id": "ready", "test_category": "Unit", "status": "Passed"},
            {"project_id": "testing", "test_category": "Unit", "status": "Not Run"},
            {"project_id": "failed", "test_category": "Unit", "status": "Failed"},
            {"project_id": "blocked-defect", "test_category": "Unit", "status": "Passed"},
            {"project_id": "uat-waiting", "test_category": "Unit", "status": "Passed"},
            {
                "project_id": "released-with-failure",
                "test_category": "Unit",
                "status": "Failed",
            },
        ]
    )
    defects = pd.DataFrame(
        [
            {
                "project_id": "blocked-defect",
                "severity": "High",
                "status": "Open",
                "release_blocker": True,
            },
            {
                "project_id": "ready",
                "severity": "Low",
                "status": "Open",
                "release_blocker": True,
            },
        ]
    )
    result = assess_release_readiness(
        requirements,
        cases,
        defects,
        _assessments(all_projects),
        project_ids=all_projects,
    ).set_index("project_id")

    assert result.loc["ready", "release_readiness"] == "Ready for Release"
    assert result.loc["ready", "release_gate_passed"]
    assert result.loc["testing", "release_readiness"] == "Testing"
    assert result.loc["testing", "required_not_run_count"] == 1
    assert result.loc["failed", "release_readiness"] == "Not Ready"
    assert result.loc["blocked-defect", "open_release_blocker_count"] == 1
    assert result.loc["blocked-defect", "release_readiness"] == "Not Ready"
    assert result.loc["uat-waiting", "release_readiness"] == "Testing"
    assert result.loc["missing-plan", "release_readiness"] == "Not Ready"
    assert not result.loc["missing-plan", "test_plan_present"]
    assert result.loc["released-with-failure", "release_readiness"] == "Released"
    assert result.loc["released-with-failure", "release_exception_warning"]
    assert result.loc["released-with-failure", "release_exception_approved"]


def test_missing_required_category_evidence_is_not_ready() -> None:
    requirements = pd.DataFrame(
        [
            {
                "project_id": "P1",
                "test_category": "Security",
                "applicable": True,
                "required": True,
            }
        ]
    )
    cases = pd.DataFrame(columns=["project_id", "test_category", "status"])
    defects = pd.DataFrame(columns=["project_id", "severity", "status", "release_blocker"])
    assessments = pd.DataFrame(
        [
            {
                "project_id": "P1",
                "uat_applicable": False,
                "uat_status": "Not Applicable",
                "actual_release_date": pd.NaT,
                "release_exception_approved": False,
            }
        ]
    )
    result = assess_release_readiness(requirements, cases, defects, assessments).iloc[0]
    assert result["release_readiness"] == "Not Ready"
    assert result["missing_required_category_count"] == 1
    assert "security" in result["readiness_reason"]


def test_unknown_test_status_is_rejected() -> None:
    cases = pd.DataFrame([{"project_id": "P1", "test_category": "Unit", "status": "Skipped"}])
    with pytest.raises(ValueError, match="Unknown test"):
        calculate_quality_metrics(cases)


def test_defect_metrics_count_open_work_by_severity_and_closed_as_resolved() -> None:
    defects = pd.DataFrame(
        [
            {"project_id": "P1", "severity": "Critical", "status": "Open"},
            {"project_id": "P1", "severity": "High", "status": "In Progress"},
            {"project_id": "P1", "severity": "Medium", "status": "Resolved"},
            {"project_id": "P1", "severity": "Low", "status": "Closed"},
            {"project_id": "P2", "severity": "Medium", "status": "Open"},
            {"project_id": "P2", "severity": "Low", "status": "In Progress"},
        ]
    )

    result = calculate_defect_metrics(defects).set_index("project_id")
    assert result.loc["P1", "open_defects"] == 2
    assert result.loc["P1", "resolved_defects"] == 2
    assert result.loc["P1", "open_critical_defects"] == 1
    assert result.loc["P1", "open_high_defects"] == 1
    assert result.loc["P1", "open_medium_defects"] == 0
    assert result.loc["P2", "open_defects"] == 2
    assert result.loc["P2", "open_medium_defects"] == 1
    assert result.loc["P2", "open_low_defects"] == 1


def test_defect_metrics_support_configurable_groups() -> None:
    defects = pd.DataFrame(
        [
            {
                "project_id": "P1",
                "release_blocker": True,
                "severity": "High",
                "status": "Open",
            },
            {
                "project_id": "P1",
                "release_blocker": False,
                "severity": "Low",
                "status": "Closed",
            },
        ]
    )
    result = calculate_defect_metrics(defects, group_columns=("project_id", "release_blocker"))
    assert len(result) == 2
    assert result["open_defects"].sum() == 1
    assert result["resolved_defects"].sum() == 1


def test_defect_metrics_empty_input_has_stable_schema() -> None:
    defects = pd.DataFrame(columns=["project_id", "severity", "status"])
    result = calculate_defect_metrics(defects)
    assert result.empty
    assert list(result.columns) == [
        "project_id",
        "open_defects",
        "resolved_defects",
        "open_critical_defects",
        "open_high_defects",
        "open_medium_defects",
        "open_low_defects",
    ]


@pytest.mark.parametrize(
    ("column", "value", "match"),
    [
        ("status", "Deferred", "Unknown defect statuses"),
        ("severity", "Urgent", "Unknown defect severities"),
    ],
)
def test_defect_metrics_reject_unknown_values(column: str, value: str, match: str) -> None:
    defect = {"project_id": "P1", "severity": "High", "status": "Open"}
    defect[column] = value
    with pytest.raises(ValueError, match=match):
        calculate_defect_metrics(pd.DataFrame([defect]))
