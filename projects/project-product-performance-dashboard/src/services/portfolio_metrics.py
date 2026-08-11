"""Portfolio aggregation helpers for executive-level dashboard metrics."""

from __future__ import annotations

from collections.abc import Mapping

import pandas as pd

from ._utils import require_columns, safe_percentage
from .delivery_metrics import summarize_delivery


def weighted_rate_from_counts(
    numerators: pd.Series,
    denominators: pd.Series,
) -> float:
    """Calculate a portfolio percentage from summed counts.

    Args:
        numerators: Group-level successful/executed counts.
        denominators: Corresponding eligible/total counts.

    Returns:
        Percentage of summed numerator over summed denominator. Empty and zero-total
        inputs return ``NaN``.
    """

    numerator = pd.to_numeric(numerators, errors="coerce").sum(min_count=1)
    denominator = pd.to_numeric(denominators, errors="coerce").sum(min_count=1)
    return float(safe_percentage(numerator, denominator))


def summarize_quality_portfolio(
    project_quality_metrics: pd.DataFrame,
) -> Mapping[str, int | float]:
    """Aggregate project test counts and recalculate portfolio rates.

    Args:
        project_quality_metrics: Project-level output from
            ``calculate_quality_metrics``. It must not contain overlapping groups.

    Returns:
        Summed status counts, totals, execution percentage, and pass percentage.
    """

    required = ["passed", "failed", "blocked", "not_run", "total", "executed"]
    require_columns(project_quality_metrics, required, name="project_quality_metrics")
    sums = {
        column: int(pd.to_numeric(project_quality_metrics[column], errors="coerce").sum())
        for column in required
    }
    return {
        **sums,
        "execution_rate_pct": float(safe_percentage(sums["executed"], sums["total"])),
        "pass_rate_pct": float(safe_percentage(sums["passed"], sums["executed"])),
    }


def _numeric_sum(frame: pd.DataFrame, column: str) -> float:
    """Return an explicit ``NaN`` rather than zero for an empty series."""

    values = pd.to_numeric(frame[column], errors="coerce")
    return float(values.sum(min_count=1))


def build_executive_summary(
    delivery_metrics: pd.DataFrame,
    project_costs: pd.DataFrame,
    project_quality_metrics: pd.DataFrame,
    latest_product_metrics: pd.DataFrame,
    financial_summary: pd.DataFrame,
) -> Mapping[str, int | float]:
    """Build auditable top-level cards from already calculated service outputs.

    Args:
        delivery_metrics: Project-level delivery metrics.
        project_costs: One row per project from ``calculate_project_costs``.
        project_quality_metrics: Non-overlapping project-level quality counts.
        latest_product_metrics: One latest monthly metric row per product.
        financial_summary: One row per product from ``summarize_financials``.

    Returns:
        A dictionary of delivery, investment, quality, product, and break-even card
        values. Percentages are recomputed from counts rather than averaged.
    """

    require_columns(
        project_costs,
        ["estimated_engineering_cost", "actual_engineering_cost"],
        name="project_costs",
    )
    require_columns(
        latest_product_metrics,
        ["product_id", "revenue", "monthly_profit"],
        name="latest_product_metrics",
    )
    require_columns(
        financial_summary,
        [
            "product_id",
            "initial_investment",
            "cumulative_revenue",
            "cumulative_profit",
            "currently_at_or_above_break_even",
        ],
        name="financial_summary",
    )
    delivery = summarize_delivery(delivery_metrics)
    quality = summarize_quality_portfolio(project_quality_metrics)
    estimated_cost = _numeric_sum(project_costs, "estimated_engineering_cost")
    actual_cost = _numeric_sum(project_costs, "actual_engineering_cost")
    cost_variance = actual_cost - estimated_cost
    cost_variance_pct = float(safe_percentage(cost_variance, estimated_cost))

    return {
        **delivery,
        "estimated_engineering_cost": estimated_cost,
        "actual_engineering_cost": actual_cost,
        "engineering_cost_variance": cost_variance,
        "engineering_cost_variance_pct": cost_variance_pct,
        "test_execution_rate_pct": quality["execution_rate_pct"],
        "test_pass_rate_pct": quality["pass_rate_pct"],
        "total_products": int(latest_product_metrics["product_id"].nunique()),
        "latest_monthly_revenue": _numeric_sum(latest_product_metrics, "revenue"),
        "latest_monthly_profit": _numeric_sum(latest_product_metrics, "monthly_profit"),
        "operating_profitable_products": int(
            pd.to_numeric(latest_product_metrics["monthly_profit"], errors="coerce").gt(0).sum()
        ),
        "total_initial_investment": _numeric_sum(financial_summary, "initial_investment"),
        "cumulative_product_revenue": _numeric_sum(financial_summary, "cumulative_revenue"),
        "cumulative_product_profit": _numeric_sum(financial_summary, "cumulative_profit"),
        "currently_break_even_products": int(
            financial_summary["currently_at_or_above_break_even"].fillna(False).sum()
        ),
    }
