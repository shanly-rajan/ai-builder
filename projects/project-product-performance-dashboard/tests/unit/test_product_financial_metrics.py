"""Unit tests for monthly product and financial performance services."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.services.financial_metrics import (
    calculate_financial_metrics,
    calculate_initial_investments,
    summarize_financials,
)
from src.services.product_metrics import (
    calculate_product_metrics,
    classify_product_performance,
    latest_product_metrics,
)


def _monthly_product_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "product_id": "A",
                "month": "2025-02-01",
                "active_customers": 20,
                "eligible_customers": 100,
                "transaction_count": 30,
                "transaction_value": 1_000,
                "revenue": 200,
                "operating_cost": 120,
            },
            {
                "product_id": "A",
                "month": "2025-01-01",
                "active_customers": 0,
                "eligible_customers": 0,
                "transaction_count": 0,
                "transaction_value": 0,
                "revenue": 0,
                "operating_cost": 20,
            },
            {
                "product_id": "B",
                "month": "2025-01-01",
                "active_customers": 5,
                "eligible_customers": 10,
                "transaction_count": 10,
                "transaction_value": 500,
                "revenue": 100,
                "operating_cost": 100,
            },
        ]
    )


def test_product_metrics_sort_months_and_handle_zero_denominators() -> None:
    result = calculate_product_metrics(_monthly_product_rows())
    product_a = result[result["product_id"].eq("A")].reset_index(drop=True)

    assert list(product_a["month"].dt.month) == [1, 2]
    assert math.isnan(product_a.loc[0, "adoption_rate_pct"])
    assert math.isnan(product_a.loc[0, "margin_pct"])
    assert math.isnan(product_a.loc[1, "revenue_growth_pct"])
    assert product_a.loc[1, "adoption_rate_pct"] == 20
    assert product_a.loc[1, "monthly_profit"] == 80
    assert product_a.loc[1, "cumulative_revenue"] == 200
    assert product_a.loc[1, "cumulative_operating_profit"] == 60

    latest = latest_product_metrics(_monthly_product_rows(), as_of="2025-01-31")
    assert len(latest) == 2
    assert set(latest["month"].dt.month) == {1}


def test_invalid_product_counts_and_duplicate_months_are_rejected() -> None:
    rows = _monthly_product_rows()
    rows.loc[0, "active_customers"] = 101
    with pytest.raises(ValueError, match="cannot exceed"):
        calculate_product_metrics(rows)

    duplicate = pd.concat([_monthly_product_rows(), _monthly_product_rows().iloc[[0]]])
    with pytest.raises(ValueError, match="Duplicate product/month"):
        calculate_product_metrics(duplicate)


def test_initial_investment_combines_many_projects_and_setup_costs() -> None:
    allocated = pd.DataFrame(
        [
            {"product_id": "A", "allocated_actual_engineering_cost": 100},
            {"product_id": "A", "allocated_actual_engineering_cost": 50},
            {"product_id": "B", "allocated_actual_engineering_cost": 40},
        ]
    )
    items = pd.DataFrame(
        [
            {
                "product_id": "A",
                "investment_type": "Additional Launch Cost",
                "amount": 30,
            },
            {
                "product_id": "A",
                "investment_type": "Third-party Setup Cost",
                "amount": 20,
            },
            {
                "product_id": "C",
                "investment_type": "Additional Launch Cost",
                "amount": 10,
            },
        ]
    )
    result = calculate_initial_investments(
        allocated, items, product_ids=["A", "B", "C", "D"]
    ).set_index("product_id")
    assert result.loc["A", "allocated_actual_engineering_cost"] == 150
    assert result.loc["A", "initial_investment"] == 200
    assert result.loc["B", "initial_investment"] == 40
    assert result.loc["C", "initial_investment"] == 10
    assert result.loc["D", "initial_investment"] == 0


def test_unsupported_investment_type_is_rejected() -> None:
    allocated = pd.DataFrame(columns=["product_id", "allocated_actual_engineering_cost"])
    items = pd.DataFrame([{"product_id": "A", "investment_type": "Tax", "amount": 10}])
    with pytest.raises(ValueError, match="Unsupported"):
        calculate_initial_investments(allocated, items)


def test_break_even_first_crossing_is_preserved_after_falling_below_zero() -> None:
    monthly = pd.DataFrame(
        [
            {"product_id": "A", "month": "2025-03-01", "revenue": 0, "operating_cost": 30},
            {"product_id": "A", "month": "2025-01-01", "revenue": 70, "operating_cost": 20},
            {"product_id": "A", "month": "2025-02-01", "revenue": 60, "operating_cost": 10},
            {"product_id": "B", "month": "2025-01-01", "revenue": 20, "operating_cost": 10},
            {"product_id": "B", "month": "2025-03-01", "revenue": 20, "operating_cost": 10},
            {"product_id": "ZERO", "month": "2025-01-01", "revenue": 0, "operating_cost": 0},
        ]
    )
    investments = pd.DataFrame(
        [
            {"product_id": "A", "initial_investment": 100},
            {"product_id": "B", "initial_investment": 500},
            {"product_id": "ZERO", "initial_investment": 0},
        ]
    )
    curve = calculate_financial_metrics(monthly, investments)
    a_curve = curve[curve["product_id"].eq("A")].reset_index(drop=True)
    assert list(a_curve["cumulative_profit"]) == [-50, 0, -30]

    products = pd.DataFrame(
        [
            {"product_id": "A", "launch_date": "2025-01-15"},
            {"product_id": "B", "launch_date": "2025-01-01"},
            {"product_id": "ZERO", "launch_date": "2025-01-01"},
        ]
    )
    summary = summarize_financials(curve, products=products).set_index("product_id")
    assert summary.loc["A", "break_even_month"] == pd.Timestamp("2025-02-01")
    assert summary.loc["A", "months_to_break_even"] == 2
    assert summary.loc["A", "ever_broken_even"]
    assert not summary.loc["A", "currently_at_or_above_break_even"]
    assert pd.isna(summary.loc["B", "break_even_month"])
    assert pd.isna(summary.loc["B", "months_to_break_even"])
    assert summary.loc["ZERO", "months_to_break_even"] == 1
    zero_roi = curve.loc[curve["product_id"].eq("ZERO"), "roi_pct"].iloc[0]
    assert math.isnan(zero_roi)


def test_months_to_break_even_use_calendar_months_when_history_has_gaps() -> None:
    monthly = pd.DataFrame(
        [
            {"product_id": "A", "month": "2025-01-01", "revenue": 50, "operating_cost": 0},
            {"product_id": "A", "month": "2025-03-01", "revenue": 50, "operating_cost": 0},
        ]
    )
    investments = pd.DataFrame([{"product_id": "A", "initial_investment": 100}])
    summary = summarize_financials(
        calculate_financial_metrics(monthly, investments),
        products=pd.DataFrame([{"product_id": "A", "launch_date": "2025-01-01"}]),
    )
    assert summary.loc[0, "months_to_break_even"] == 3


def _classification_months() -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    profits = {
        "new": [20, 20],
        "profitable": [40, 40, 40],
        "approaching": [60, 60, 60],
        "under": [30, 30, 30],
    }
    for product_id, monthly_profits in profits.items():
        for month, profit in enumerate(monthly_profits, start=1):
            rows.append(
                {
                    "product_id": product_id,
                    "month": f"2025-{month:02d}-01",
                    "active_customers": 10,
                    "eligible_customers": 100,
                    "transaction_count": 10,
                    "transaction_value": 100,
                    "revenue": 100,
                    "operating_cost": 100 - profit,
                }
            )
    return pd.DataFrame(rows)


def test_product_performance_classification_is_transparent() -> None:
    products = pd.DataFrame(
        [{"product_id": product_id} for product_id in ["new", "profitable", "approaching", "under"]]
    )
    financial = pd.DataFrame(
        [
            {
                "product_id": "new",
                "cumulative_profit": -10,
                "currently_at_or_above_break_even": False,
            },
            {
                "product_id": "profitable",
                "cumulative_profit": 10,
                "currently_at_or_above_break_even": True,
            },
            {
                "product_id": "approaching",
                "cumulative_profit": -300,
                "currently_at_or_above_break_even": False,
            },
            {
                "product_id": "under",
                "cumulative_profit": -500,
                "currently_at_or_above_break_even": False,
            },
        ]
    )
    result = classify_product_performance(
        products, financial, _classification_months(), as_of="2025-03-31"
    ).set_index("product_id")
    assert result.loc["new", "performance_status"] == "New"
    assert result.loc["profitable", "performance_status"] == "Profitable"
    assert result.loc["approaching", "performance_status"] == "Approaching Break-even"
    assert result.loc["approaching", "projected_months_to_break_even"] == 5
    assert result.loc["under", "performance_status"] == "Underperforming"


def test_classification_handles_financial_summary_latest_profit_column() -> None:
    products = pd.DataFrame([{"product_id": "new"}])
    financial = pd.DataFrame(
        [
            {
                "product_id": "new",
                "cumulative_profit": -10,
                "currently_at_or_above_break_even": False,
                "latest_monthly_profit": 999,
            }
        ]
    )
    result = classify_product_performance(
        products,
        financial,
        _classification_months().query("product_id == 'new'"),
        as_of="2025-01-31",
    )
    assert result.loc[0, "latest_monthly_profit"] == 20
