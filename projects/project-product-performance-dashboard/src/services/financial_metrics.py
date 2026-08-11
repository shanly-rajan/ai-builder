"""Initial investment, cumulative profit, ROI, and break-even calculations."""

from __future__ import annotations

from collections.abc import Iterable

import pandas as pd

from ._utils import (
    datetime_series,
    normalize_token,
    numeric_series,
    require_columns,
    safe_percentage,
)

INVESTMENT_TYPES = {
    "additional_launch_cost": "additional_launch_cost",
    "third_party_setup_cost": "third_party_setup_cost",
}


def calculate_initial_investments(
    allocated_engineering_costs: pd.DataFrame,
    product_investment_items: pd.DataFrame,
    *,
    product_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Build each product's simplified initial-investment basis.

    Args:
        allocated_engineering_costs: Mapping-level or product-level data containing
            ``product_id`` and ``allocated_actual_engineering_cost``.
        product_investment_items: Additional launch and third-party setup items.
        product_ids: Optional complete product universe, including products with no
            recorded investment.

    Returns:
        One row per product with allocated engineering, launch/setup components, and
        total ``initial_investment``.

    Raises:
        ValueError: If amounts are negative or an unsupported investment type exists.
    """

    require_columns(
        allocated_engineering_costs,
        ["product_id", "allocated_actual_engineering_cost"],
        name="allocated_engineering_costs",
    )
    require_columns(
        product_investment_items,
        ["product_id", "investment_type", "amount"],
        name="product_investment_items",
    )
    allocated = allocated_engineering_costs.copy()
    allocated["allocated_actual_engineering_cost"] = numeric_series(
        allocated,
        "allocated_actual_engineering_cost",
        name="allocated_engineering_costs",
    )
    negative_allocated = allocated["allocated_actual_engineering_cost"].lt(0)
    if negative_allocated.any():
        raise ValueError("Allocated engineering cost cannot be negative")
    allocated_grouped = (
        allocated.groupby("product_id", as_index=False, sort=False)[
            "allocated_actual_engineering_cost"
        ].sum(min_count=1)
        if not allocated.empty
        else pd.DataFrame(columns=["product_id", "allocated_actual_engineering_cost"])
    )

    items = product_investment_items.copy()
    items["amount"] = numeric_series(items, "amount", name="product_investment_items")
    negative_amount = items["amount"].lt(0)
    if negative_amount.any():
        raise ValueError(
            "product_investment_items.amount cannot be negative at rows "
            f"{items.index[negative_amount].tolist()}"
        )
    items["_investment_type"] = items["investment_type"].map(normalize_token)
    unsupported = ~items["_investment_type"].isin(INVESTMENT_TYPES)
    if unsupported.any():
        values = sorted(items.loc[unsupported, "investment_type"].astype(str).unique())
        raise ValueError(f"Unsupported investment types: {values}")
    if items.empty:
        item_pivot = pd.DataFrame(
            columns=["product_id", "additional_launch_cost", "third_party_setup_cost"]
        )
    else:
        item_pivot = (
            items.groupby(["product_id", "_investment_type"])["amount"]
            .sum(min_count=1)
            .unstack(fill_value=0.0)
            .reset_index()
        )
        item_pivot.columns.name = None
        for column in INVESTMENT_TYPES.values():
            if column not in item_pivot:
                item_pivot[column] = 0.0

    if product_ids is None:
        ids = pd.concat(
            [allocated["product_id"], items["product_id"]], ignore_index=True
        ).drop_duplicates()
        base = pd.DataFrame({"product_id": ids})
    else:
        base = pd.DataFrame({"product_id": list(dict.fromkeys(product_ids))})
    result = base.merge(allocated_grouped, how="left", on="product_id")
    result = result.merge(item_pivot, how="left", on="product_id")
    component_columns = [
        "allocated_actual_engineering_cost",
        "additional_launch_cost",
        "third_party_setup_cost",
    ]
    result[component_columns] = result[component_columns].fillna(0.0)
    result["initial_investment"] = result[component_columns].sum(axis=1)
    return result[["product_id", *component_columns, "initial_investment"]]


def calculate_financial_metrics(
    product_monthly_metrics: pd.DataFrame,
    initial_investments: pd.DataFrame,
) -> pd.DataFrame:
    """Calculate monthly and cumulative product financial curves.

    Cumulative profit is cumulative revenue less cumulative operating cost and the
    complete initial investment basis. ROI is unavailable when initial investment is
    zero.

    Args:
        product_monthly_metrics: Canonical monthly revenue and operating-cost facts.
        initial_investments: Per-product output from
            :func:`calculate_initial_investments`.

    Returns:
        Product/month financial curves with profit, cumulative totals, ROI, and a
        current break-even indicator.

    Raises:
        ValueError: If product/month rows are duplicated or financial values are
            negative/invalid.
    """

    require_columns(
        product_monthly_metrics,
        ["product_id", "month", "revenue", "operating_cost"],
        name="product_monthly_metrics",
    )
    require_columns(
        initial_investments,
        ["product_id", "initial_investment"],
        name="initial_investments",
    )
    if initial_investments["product_id"].duplicated().any():
        raise ValueError("initial_investments must contain one row per product")
    result = product_monthly_metrics.copy()
    result["month"] = (
        datetime_series(result, "month", name="product_monthly_metrics")
        .dt.to_period("M")
        .dt.to_timestamp()
    )
    duplicates = result[["product_id", "month"]].duplicated(keep=False)
    if duplicates.any():
        pairs = result.loc[duplicates, ["product_id", "month"]].drop_duplicates()
        raise ValueError(f"Duplicate product/month metrics: {pairs.to_dict('records')}")
    for column in ("revenue", "operating_cost"):
        result[column] = numeric_series(result, column, name="product_monthly_metrics")
        negative = result[column].lt(0)
        if negative.any():
            raise ValueError(
                f"product_monthly_metrics.{column} cannot be negative at rows "
                f"{result.index[negative].tolist()}"
            )

    investments = initial_investments[["product_id", "initial_investment"]].copy()
    investments["initial_investment"] = numeric_series(
        investments, "initial_investment", name="initial_investments"
    )
    if investments["initial_investment"].lt(0).any():
        raise ValueError("initial_investment cannot be negative")

    result = result.sort_values(["product_id", "month"], kind="stable").reset_index(drop=True)
    result = result.merge(investments, how="left", on="product_id", validate="many_to_one")
    result["initial_investment"] = result["initial_investment"].fillna(0.0)
    result["monthly_profit"] = result["revenue"] - result["operating_cost"]
    result["cumulative_revenue"] = result.groupby("product_id", sort=False)["revenue"].cumsum()
    result["cumulative_operating_cost"] = result.groupby("product_id", sort=False)[
        "operating_cost"
    ].cumsum()
    result["cumulative_profit"] = (
        result["cumulative_revenue"]
        - result["cumulative_operating_cost"]
        - result["initial_investment"]
    )
    result["roi_pct"] = safe_percentage(result["cumulative_profit"], result["initial_investment"])
    result["at_or_above_break_even"] = result["cumulative_profit"].ge(0)
    return result


def summarize_financials(
    financial_metrics: pd.DataFrame,
    *,
    products: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Summarize current and historical break-even state by product.

    The first observed month-end at or above zero is retained even when a product
    later falls below zero. Months to break-even are counted inclusively from the
    launch month, or from the first observed metric month when no product master is
    supplied.

    Args:
        financial_metrics: Output from :func:`calculate_financial_metrics`.
        products: Optional product master with ``product_id`` and ``launch_date``.

    Returns:
        One row per product with latest cumulative values, first break-even month,
        inclusive months to break-even, and current/historical break-even flags.
    """

    required = [
        "product_id",
        "month",
        "initial_investment",
        "monthly_profit",
        "cumulative_revenue",
        "cumulative_operating_cost",
        "cumulative_profit",
        "roi_pct",
    ]
    require_columns(financial_metrics, required, name="financial_metrics")
    ordered = financial_metrics.sort_values(["product_id", "month"], kind="stable")

    if products is not None:
        require_columns(products, ["product_id", "launch_date"], name="products")
        if products["product_id"].duplicated().any():
            raise ValueError("products must contain one row per product")
        base = products[["product_id", "launch_date"]].copy()
        base["launch_date"] = datetime_series(base, "launch_date", name="products")
    else:
        first_month = (
            ordered.groupby("product_id", as_index=False, sort=False)["month"]
            .min()
            .rename(columns={"month": "launch_date"})
        )
        base = first_month

    latest_columns = [
        "product_id",
        "month",
        "initial_investment",
        "monthly_profit",
        "cumulative_revenue",
        "cumulative_operating_cost",
        "cumulative_profit",
        "roi_pct",
    ]
    latest = (
        ordered.groupby("product_id", as_index=False, sort=False)
        .tail(1)[latest_columns]
        .rename(
            columns={
                "month": "latest_month",
                "monthly_profit": "latest_monthly_profit",
            }
        )
    )
    crossing = ordered[ordered["cumulative_profit"].ge(0)]
    first_crossing = (
        crossing.groupby("product_id", as_index=False, sort=False)["month"]
        .min()
        .rename(columns={"month": "break_even_month"})
    )
    result = base.merge(latest, how="left", on="product_id", validate="one_to_one")
    result = result.merge(first_crossing, how="left", on="product_id", validate="one_to_one")
    result["ever_broken_even"] = result["break_even_month"].notna()
    result["currently_at_or_above_break_even"] = result["cumulative_profit"].ge(0)

    month_difference = (
        (result["break_even_month"].dt.year - result["launch_date"].dt.year) * 12
        + result["break_even_month"].dt.month
        - result["launch_date"].dt.month
        + 1
    )
    invalid_order = result["break_even_month"].notna() & month_difference.lt(1)
    if invalid_order.any():
        products_invalid = result.loc[invalid_order, "product_id"].tolist()
        raise ValueError(f"Break-even precedes launch for products: {products_invalid}")
    result["months_to_break_even"] = month_difference.astype("Int64")
    return result
