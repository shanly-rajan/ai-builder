"""Unit tests for executive portfolio helpers."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.services.portfolio_metrics import build_executive_summary, weighted_rate_from_counts


def test_weighted_rate_uses_summed_counts_and_zero_total_is_na() -> None:
    assert weighted_rate_from_counts(pd.Series([1, 1]), pd.Series([1, 9])) == 20
    assert math.isnan(weighted_rate_from_counts(pd.Series(dtype=float), pd.Series(dtype=float)))
    assert math.isnan(weighted_rate_from_counts(pd.Series([0]), pd.Series([0])))


def test_executive_summary_reconciles_source_totals() -> None:
    delivery = pd.DataFrame(
        [
            {"delivery_outcome": "early", "schedule_variance_days": -1},
            {"delivery_outcome": "late", "schedule_variance_days": 2},
            {"delivery_outcome": "active_overdue", "schedule_variance_days": None},
        ]
    )
    costs = pd.DataFrame(
        [
            {"estimated_engineering_cost": 100, "actual_engineering_cost": 110},
            {"estimated_engineering_cost": 200, "actual_engineering_cost": 190},
        ]
    )
    quality = pd.DataFrame(
        [{"passed": 5, "failed": 1, "blocked": 0, "not_run": 4, "total": 10, "executed": 6}]
    )
    latest_products = pd.DataFrame(
        [
            {"product_id": "A", "revenue": 100, "monthly_profit": 20},
            {"product_id": "B", "revenue": 50, "monthly_profit": -5},
        ]
    )
    financial = pd.DataFrame(
        [
            {
                "product_id": "A",
                "initial_investment": 100,
                "cumulative_revenue": 300,
                "cumulative_profit": 20,
                "currently_at_or_above_break_even": True,
            },
            {
                "product_id": "B",
                "initial_investment": 200,
                "cumulative_revenue": 100,
                "cumulative_profit": -150,
                "currently_at_or_above_break_even": False,
            },
        ]
    )
    summary = build_executive_summary(delivery, costs, quality, latest_products, financial)
    assert summary["on_time_delivery_pct"] == 50
    assert summary["active_overdue_projects"] == 1
    assert summary["actual_engineering_cost"] == 300
    assert summary["engineering_cost_variance"] == 0
    assert summary["test_execution_rate_pct"] == 60
    assert summary["test_pass_rate_pct"] == pytest.approx(500 / 6)
    assert summary["latest_monthly_revenue"] == 150
    assert summary["latest_monthly_profit"] == 15
    assert summary["currently_break_even_products"] == 1
