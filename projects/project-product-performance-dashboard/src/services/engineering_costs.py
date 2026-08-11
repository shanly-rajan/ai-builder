"""Engineering effort, cost, and project-to-product allocation calculations."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from ._utils import numeric_series, require_columns, safe_percentage

ALLOCATION_TOLERANCE = 1e-9


def calculate_resource_costs(resource_allocations: pd.DataFrame) -> pd.DataFrame:
    """Calculate estimated and actual role-level resource costs.

    Args:
        resource_allocations: Allocation records containing canonical estimated and
            actual person-days plus the snapshotted fictional daily rate.

    Returns:
        A copy with ``estimated_resource_cost`` and ``actual_resource_cost``.

    Raises:
        ValueError: If required numeric values are invalid or negative.
    """

    required = [
        "project_id",
        "estimated_person_days",
        "actual_person_days",
        "fictional_daily_rate",
    ]
    require_columns(resource_allocations, required, name="resource_allocations")
    result = resource_allocations.copy()
    estimated_days = numeric_series(result, "estimated_person_days", name="resource_allocations")
    actual_days = numeric_series(result, "actual_person_days", name="resource_allocations")
    daily_rate = numeric_series(result, "fictional_daily_rate", name="resource_allocations")

    for column, values in (
        ("estimated_person_days", estimated_days),
        ("actual_person_days", actual_days),
        ("fictional_daily_rate", daily_rate),
    ):
        negative = values.lt(0)
        if negative.any():
            raise ValueError(
                f"resource_allocations.{column} cannot be negative at rows "
                f"{result.index[negative].tolist()}"
            )

    result["estimated_resource_cost"] = estimated_days * daily_rate
    result["actual_resource_cost"] = actual_days * daily_rate
    return result


def cost_variance(actual_cost: float, estimated_cost: float) -> tuple[float, float]:
    """Calculate absolute and percentage cost variance.

    Args:
        actual_cost: Actual cost or cost to date.
        estimated_cost: Approved cost estimate.

    Returns:
        A ``(variance, variance_percentage)`` tuple. The percentage is ``NaN``
        when the estimate is zero or missing.
    """

    if pd.isna(actual_cost) or pd.isna(estimated_cost):
        return float("nan"), float("nan")
    variance = float(actual_cost) - float(estimated_cost)
    return variance, float(safe_percentage(variance, estimated_cost))


def _group_costs(
    frame: pd.DataFrame,
    *,
    value_columns: list[str],
    output_columns: list[str],
) -> pd.DataFrame:
    """Aggregate cost columns with explicit all-missing semantics."""

    if frame.empty:
        return pd.DataFrame(columns=["project_id", *output_columns])
    grouped = (
        frame.groupby("project_id", as_index=False, sort=False)[value_columns]
        .sum(min_count=1)
        .rename(columns=dict(zip(value_columns, output_columns, strict=True)))
    )
    return grouped


def calculate_project_costs(
    resource_allocations: pd.DataFrame,
    project_cost_items: pd.DataFrame,
    *,
    project_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Aggregate estimated and actual engineering cost by project.

    Engineering cost comprises role-level resource cost plus engineering
    infrastructure and external cost items. Missing actual values remain unknown;
    projects with no rows in one component receive zero for that component.

    Args:
        resource_allocations: Canonical role-level effort allocation records.
        project_cost_items: Canonical infrastructure/external cost item records.
        project_ids: Optional complete project universe, including projects with no
            cost records.

    Returns:
        One row per project with component totals, engineering totals, and cost
        variance fields.

    Raises:
        ValueError: If cost values are negative or required columns are missing.
    """

    require_columns(
        project_cost_items,
        ["project_id", "estimated_cost", "actual_cost"],
        name="project_cost_items",
    )
    resource_costs = calculate_resource_costs(resource_allocations)
    items = project_cost_items.copy()
    estimated_items = numeric_series(items, "estimated_cost", name="project_cost_items")
    actual_items = numeric_series(items, "actual_cost", name="project_cost_items")
    for column, values in (
        ("estimated_cost", estimated_items),
        ("actual_cost", actual_items),
    ):
        negative = values.lt(0)
        if negative.any():
            raise ValueError(
                f"project_cost_items.{column} cannot be negative at rows "
                f"{items.index[negative].tolist()}"
            )
    items["estimated_cost"] = estimated_items
    items["actual_cost"] = actual_items

    resource_grouped = _group_costs(
        resource_costs,
        value_columns=["estimated_resource_cost", "actual_resource_cost"],
        output_columns=["estimated_resource_cost", "actual_resource_cost"],
    )
    item_grouped = _group_costs(
        items,
        value_columns=["estimated_cost", "actual_cost"],
        output_columns=["estimated_cost_items", "actual_cost_items"],
    )

    if project_ids is None:
        ordered_ids = pd.Index(
            pd.concat(
                [resource_allocations["project_id"], project_cost_items["project_id"]],
                ignore_index=True,
            ).drop_duplicates(),
            dtype="object",
        )
    else:
        ordered_ids = pd.Index(list(dict.fromkeys(project_ids)), dtype="object")
    result = pd.DataFrame({"project_id": ordered_ids})
    result = result.merge(resource_grouped, how="left", on="project_id", indicator="_resource")
    no_resource_rows = result.pop("_resource").eq("left_only")
    result.loc[no_resource_rows, ["estimated_resource_cost", "actual_resource_cost"]] = 0.0
    result = result.merge(item_grouped, how="left", on="project_id", indicator="_items")
    no_item_rows = result.pop("_items").eq("left_only")
    result.loc[no_item_rows, ["estimated_cost_items", "actual_cost_items"]] = 0.0

    result["estimated_engineering_cost"] = (
        result["estimated_resource_cost"] + result["estimated_cost_items"]
    )
    result["actual_engineering_cost"] = result["actual_resource_cost"] + result["actual_cost_items"]
    result["cost_variance"] = (
        result["actual_engineering_cost"] - result["estimated_engineering_cost"]
    )
    result["cost_variance_pct"] = safe_percentage(
        result["cost_variance"], result["estimated_engineering_cost"]
    )
    return result


def validate_project_product_allocations(
    mappings: pd.DataFrame,
    *,
    valid_project_ids: Iterable[str] | None = None,
    valid_product_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Validate and normalize many-to-many engineering-cost allocations.

    Percentages use the human-readable 0-to-100 scale. Partial allocation is valid,
    but a project's combined allocation above 100 percent is a hard error.

    Args:
        mappings: Canonical project/product mapping records.
        valid_project_ids: Optional known project identifiers for referential checks.
        valid_product_ids: Optional known product identifiers for referential checks.

    Returns:
        A validated copy with numeric ``allocation_percentage``.

    Raises:
        ValueError: If references, pairs, percentages, or project totals are invalid.
    """

    require_columns(
        mappings,
        ["project_id", "product_id", "allocation_percentage"],
        name="project_product_mappings",
    )
    result = mappings.copy()
    empty_project = result["project_id"].isna() | result["project_id"].astype(str).str.strip().eq(
        ""
    )
    empty_product = result["product_id"].isna() | result["product_id"].astype(str).str.strip().eq(
        ""
    )
    if empty_project.any() or empty_product.any():
        bad = result.index[empty_project | empty_product].tolist()
        raise ValueError(f"Project and product references are required at rows {bad}")

    duplicates = result.duplicated(["project_id", "product_id"], keep=False)
    if duplicates.any():
        pairs = result.loc[duplicates, ["project_id", "product_id"]].drop_duplicates()
        raise ValueError(f"Duplicate project/product mappings: {pairs.to_dict('records')}")

    percentage = numeric_series(result, "allocation_percentage", name="project_product_mappings")
    invalid_percentage = percentage.isna() | percentage.lt(0) | percentage.gt(100)
    if invalid_percentage.any():
        raise ValueError(
            "allocation_percentage must be between 0 and 100 at rows "
            f"{result.index[invalid_percentage].tolist()}"
        )
    result["allocation_percentage"] = percentage

    project_totals = result.groupby("project_id")["allocation_percentage"].sum()
    overallocated = project_totals.gt(100.0 + ALLOCATION_TOLERANCE)
    if overallocated.any():
        details = project_totals[overallocated].to_dict()
        raise ValueError(f"Project allocations exceed 100 percent: {details}")

    if valid_project_ids is not None:
        valid_projects = set(valid_project_ids)
        unknown = sorted(set(result["project_id"]).difference(valid_projects))
        if unknown:
            raise ValueError(f"Unknown project references: {unknown}")
    if valid_product_ids is not None:
        valid_products = set(valid_product_ids)
        unknown = sorted(set(result["product_id"]).difference(valid_products))
        if unknown:
            raise ValueError(f"Unknown product references: {unknown}")
    return result


def calculate_project_allocation_coverage(
    mappings: pd.DataFrame,
    *,
    project_ids: Iterable[str] | None = None,
) -> pd.DataFrame:
    """Show allocated and intentionally unallocated investment per project.

    Args:
        mappings: Valid project/product mapping records.
        project_ids: Optional complete project universe.

    Returns:
        Per-project allocated percentage, unallocated percentage, and full-allocation
        flag.
    """

    valid = validate_project_product_allocations(mappings)
    totals = (
        valid.groupby("project_id", as_index=False)["allocation_percentage"]
        .sum()
        .rename(columns={"allocation_percentage": "allocated_percentage"})
    )
    if project_ids is not None:
        base = pd.DataFrame({"project_id": list(dict.fromkeys(project_ids))})
        totals = base.merge(totals, how="left", on="project_id")
        totals["allocated_percentage"] = totals["allocated_percentage"].fillna(0.0)
    totals["unallocated_percentage"] = 100.0 - totals["allocated_percentage"]
    totals["is_fully_allocated"] = np.isclose(
        totals["allocated_percentage"], 100.0, atol=ALLOCATION_TOLERANCE
    )
    return totals


def allocate_engineering_costs(
    project_costs: pd.DataFrame,
    mappings: pd.DataFrame,
) -> pd.DataFrame:
    """Allocate project engineering cost to products at mapping-row granularity.

    Args:
        project_costs: Project totals from :func:`calculate_project_costs`.
        mappings: Canonical project/product allocation records.

    Returns:
        Mapping records augmented with allocated estimated and actual engineering
        cost.

    Raises:
        ValueError: If a mapping references a project without a cost row.
    """

    require_columns(
        project_costs,
        ["project_id", "estimated_engineering_cost", "actual_engineering_cost"],
        name="project_costs",
    )
    if project_costs["project_id"].duplicated().any():
        raise ValueError("project_costs must contain one row per project")
    valid = validate_project_product_allocations(
        mappings, valid_project_ids=project_costs["project_id"]
    )
    result = valid.merge(
        project_costs[["project_id", "estimated_engineering_cost", "actual_engineering_cost"]],
        how="left",
        on="project_id",
        validate="many_to_one",
    )
    fraction = result["allocation_percentage"] / 100.0
    result["allocated_estimated_engineering_cost"] = result["estimated_engineering_cost"] * fraction
    result["allocated_actual_engineering_cost"] = result["actual_engineering_cost"] * fraction
    return result


def summarize_product_allocations(allocated_costs: pd.DataFrame) -> pd.DataFrame:
    """Aggregate mapping-level allocated engineering cost by product.

    Args:
        allocated_costs: Output from :func:`allocate_engineering_costs`.

    Returns:
        One row per product with estimated and actual allocated engineering cost.
    """

    required = [
        "product_id",
        "allocated_estimated_engineering_cost",
        "allocated_actual_engineering_cost",
    ]
    require_columns(allocated_costs, required, name="allocated_costs")
    if allocated_costs.empty:
        return pd.DataFrame(columns=required)
    return allocated_costs.groupby("product_id", as_index=False, sort=False)[required[1:]].sum(
        min_count=1
    )
