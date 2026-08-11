"""Monthly product adoption, transaction, revenue, and performance metrics."""

from __future__ import annotations

from datetime import date, datetime

import numpy as np
import pandas as pd

from ._utils import datetime_series, numeric_series, require_columns, safe_percentage

DateLike = str | date | datetime | pd.Timestamp


def calculate_product_metrics(product_monthly_metrics: pd.DataFrame) -> pd.DataFrame:
    """Calculate ordered monthly operating metrics for each product.

    Args:
        product_monthly_metrics: Canonical monthly product facts.

    Returns:
        A product/month-sorted copy with adoption, monthly profit, margin, revenue
        growth, and cumulative operating measures.

    Raises:
        ValueError: If months are duplicated or business measures are invalid.
    """

    required = [
        "product_id",
        "month",
        "active_customers",
        "eligible_customers",
        "transaction_count",
        "transaction_value",
        "revenue",
        "operating_cost",
    ]
    require_columns(product_monthly_metrics, required, name="product_monthly_metrics")
    result = product_monthly_metrics.copy()
    result["month"] = (
        datetime_series(result, "month", name="product_monthly_metrics")
        .dt.to_period("M")
        .dt.to_timestamp()
    )
    if result[["product_id", "month"]].duplicated().any():
        duplicates = result.loc[
            result[["product_id", "month"]].duplicated(keep=False),
            ["product_id", "month"],
        ].drop_duplicates()
        raise ValueError(f"Duplicate product/month metrics: {duplicates.to_dict('records')}")

    numeric_columns = [
        "active_customers",
        "eligible_customers",
        "transaction_count",
        "transaction_value",
        "revenue",
        "operating_cost",
    ]
    for column in numeric_columns:
        values = numeric_series(result, column, name="product_monthly_metrics")
        negative = values.lt(0)
        if negative.any():
            raise ValueError(
                f"product_monthly_metrics.{column} cannot be negative at rows "
                f"{result.index[negative].tolist()}"
            )
        result[column] = values
    over_eligible = result["active_customers"].gt(result["eligible_customers"])
    if over_eligible.any():
        raise ValueError(
            "active_customers cannot exceed eligible_customers at rows "
            f"{result.index[over_eligible].tolist()}"
        )

    result = result.sort_values(["product_id", "month"], kind="stable").reset_index(drop=True)
    result["adoption_rate_pct"] = safe_percentage(
        result["active_customers"], result["eligible_customers"]
    )
    result["monthly_profit"] = result["revenue"] - result["operating_cost"]
    result["margin_pct"] = safe_percentage(result["monthly_profit"], result["revenue"])
    prior_revenue = result.groupby("product_id", sort=False)["revenue"].shift(1)
    result["revenue_growth_pct"] = safe_percentage(result["revenue"] - prior_revenue, prior_revenue)
    result["cumulative_revenue"] = result.groupby("product_id", sort=False)["revenue"].cumsum()
    result["cumulative_operating_cost"] = result.groupby("product_id", sort=False)[
        "operating_cost"
    ].cumsum()
    result["cumulative_operating_profit"] = result.groupby("product_id", sort=False)[
        "monthly_profit"
    ].cumsum()
    return result


def latest_product_metrics(
    product_metrics: pd.DataFrame,
    *,
    as_of: DateLike | None = None,
) -> pd.DataFrame:
    """Select each product's latest observed monthly metrics.

    Args:
        product_metrics: Raw or calculated canonical monthly product records.
        as_of: Optional reporting cutoff; future metric months are excluded.

    Returns:
        One latest row per product, with all calculated product metric columns.
    """

    calculated = calculate_product_metrics(product_metrics)
    if as_of is not None:
        try:
            as_of_ts = pd.Timestamp(as_of).normalize()
        except (TypeError, ValueError) as exc:
            raise ValueError("as_of must be a valid date") from exc
        calculated = calculated[calculated["month"].le(as_of_ts)]
    if calculated.empty:
        return calculated.copy()
    return (
        calculated.sort_values(["product_id", "month"], kind="stable")
        .groupby("product_id", as_index=False, sort=False)
        .tail(1)
        .reset_index(drop=True)
    )


def classify_product_performance(
    products: pd.DataFrame,
    financial_summary: pd.DataFrame,
    product_monthly_metrics: pd.DataFrame,
    *,
    as_of: DateLike,
    new_product_months: int = 3,
    approaching_break_even_months: int = 6,
) -> pd.DataFrame:
    """Classify products using explicit maturity and simple run-rate rules.

    ``Approaching Break-even`` is not a forecast: it divides the remaining
    cumulative loss by the average profit of the latest three complete observed
    months. Products with fewer than three complete months are ``New``.

    Args:
        products: Canonical product master records.
        financial_summary: Output from ``summarize_financials``.
        product_monthly_metrics: Raw canonical monthly metrics.
        as_of: Fixed reporting date used to identify complete months.
        new_product_months: Minimum complete month count for a mature product.
        approaching_break_even_months: Maximum simple run-rate payback horizon.

    Returns:
        Product records augmented with operating/lifetime profitability indicators,
        run-rate details, and ``performance_status``.
    """

    require_columns(products, ["product_id"], name="products")
    require_columns(
        financial_summary,
        ["product_id", "cumulative_profit", "currently_at_or_above_break_even"],
        name="financial_summary",
    )
    if new_product_months < 1 or approaching_break_even_months < 1:
        raise ValueError("Classification month thresholds must be positive")
    if products["product_id"].duplicated().any():
        raise ValueError("products must contain one row per product")
    if financial_summary["product_id"].duplicated().any():
        raise ValueError("financial_summary must contain one row per product")
    try:
        as_of_ts = pd.Timestamp(as_of).normalize()
    except (TypeError, ValueError) as exc:
        raise ValueError("as_of must be a valid date") from exc

    monthly = calculate_product_metrics(product_monthly_metrics)
    month_end = monthly["month"].dt.to_period("M").dt.end_time.dt.normalize()
    complete = monthly[month_end.le(as_of_ts)].copy()
    latest = (
        complete.groupby("product_id", as_index=False, sort=False)
        .tail(1)[["product_id", "monthly_profit"]]
        .rename(columns={"monthly_profit": "latest_monthly_profit"})
    )
    counts = (
        complete.groupby("product_id", as_index=False)
        .size()
        .rename(columns={"size": "complete_month_count"})
    )

    trailing_rows = complete.groupby("product_id", sort=False).tail(3)
    trailing = trailing_rows.groupby("product_id", as_index=False).agg(
        trailing_three_month_profit=("monthly_profit", "sum"),
        trailing_month_count=("monthly_profit", "size"),
    )
    trailing["average_monthly_profit_run_rate"] = (
        trailing["trailing_three_month_profit"] / trailing["trailing_month_count"]
    )

    result = products.copy()
    # Recalculate the latest operating profit at the requested ``as_of`` cutoff.
    # ``summarize_financials`` also exposes a latest value, so remove that copy to
    # avoid suffixes and prevent future-dated summary data from leaking through.
    summary_for_merge = financial_summary.drop(columns=["latest_monthly_profit"], errors="ignore")
    result = result.merge(summary_for_merge, how="left", on="product_id", validate="one_to_one")
    result = result.merge(latest, how="left", on="product_id", validate="one_to_one")
    result = result.merge(counts, how="left", on="product_id", validate="one_to_one")
    result = result.merge(trailing, how="left", on="product_id", validate="one_to_one")
    result["complete_month_count"] = result["complete_month_count"].fillna(0).astype(int)
    result["trailing_month_count"] = result["trailing_month_count"].fillna(0).astype(int)
    result["operating_profitable"] = result["latest_monthly_profit"].gt(0)
    result["lifetime_profitable"] = result["cumulative_profit"].ge(0)

    positive_run_rate = result["average_monthly_profit_run_rate"].gt(0)
    result["projected_months_to_break_even"] = np.nan
    eligible_projection = result["cumulative_profit"].lt(0) & positive_run_rate
    result.loc[eligible_projection, "projected_months_to_break_even"] = (
        -result.loc[eligible_projection, "cumulative_profit"]
        / result.loc[eligible_projection, "average_monthly_profit_run_rate"]
    )

    is_new = result["complete_month_count"].lt(new_product_months)
    is_profitable = result["currently_at_or_above_break_even"].fillna(False).astype(bool)
    is_approaching = (
        ~is_new
        & ~is_profitable
        & result["trailing_month_count"].ge(3)
        & positive_run_rate
        & result["projected_months_to_break_even"].le(approaching_break_even_months)
    )
    result["performance_status"] = "Underperforming"
    result.loc[is_approaching, "performance_status"] = "Approaching Break-even"
    result.loc[is_profitable & ~is_new, "performance_status"] = "Profitable"
    result.loc[is_new, "performance_status"] = "New"
    return result
