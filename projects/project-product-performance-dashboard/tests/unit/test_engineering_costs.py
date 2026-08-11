"""Unit tests for engineering cost and allocation services."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.services.engineering_costs import (
    allocate_engineering_costs,
    calculate_project_allocation_coverage,
    calculate_project_costs,
    calculate_resource_costs,
    cost_variance,
    summarize_product_allocations,
    validate_project_product_allocations,
)


def _resources() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "allocation_id": "a1",
                "project_id": "P1",
                "estimated_person_days": 10,
                "actual_person_days": 12,
                "fictional_daily_rate": 100,
            },
            {
                "allocation_id": "a2",
                "project_id": "P1",
                "estimated_person_days": 5,
                "actual_person_days": 4,
                "fictional_daily_rate": 200,
            },
            {
                "allocation_id": "a3",
                "project_id": "P2",
                "estimated_person_days": 0,
                "actual_person_days": 1,
                "fictional_daily_rate": 100,
            },
        ]
    )


def _cost_items() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "cost_item_id": "c1",
                "project_id": "P1",
                "estimated_cost": 500,
                "actual_cost": 700,
            }
        ]
    )


def _mappings() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "mapping_id": "m1",
                "project_id": "P1",
                "product_id": "A",
                "allocation_percentage": 60,
            },
            {
                "mapping_id": "m2",
                "project_id": "P1",
                "product_id": "B",
                "allocation_percentage": 30,
            },
            {
                "mapping_id": "m3",
                "project_id": "P2",
                "product_id": "A",
                "allocation_percentage": 100,
            },
        ]
    )


def test_resource_and_project_costs_are_aggregated_from_person_days() -> None:
    resources = calculate_resource_costs(_resources()).set_index("allocation_id")
    assert resources.loc["a1", "estimated_resource_cost"] == 1_000
    assert resources.loc["a1", "actual_resource_cost"] == 1_200

    projects = calculate_project_costs(
        _resources(), _cost_items(), project_ids=["P1", "P2", "P3"]
    ).set_index("project_id")
    assert projects.loc["P1", "estimated_engineering_cost"] == 2_500
    assert projects.loc["P1", "actual_engineering_cost"] == 2_700
    assert projects.loc["P1", "cost_variance"] == 200
    assert projects.loc["P1", "cost_variance_pct"] == pytest.approx(8)
    assert projects.loc["P2", "estimated_engineering_cost"] == 0
    assert projects.loc["P2", "actual_engineering_cost"] == 100
    assert math.isnan(projects.loc["P2", "cost_variance_pct"])
    assert projects.loc["P3", "estimated_engineering_cost"] == 0
    assert projects.loc["P3", "actual_engineering_cost"] == 0


def test_scalar_cost_variance_handles_zero_estimate() -> None:
    variance, percentage = cost_variance(100, 0)
    assert variance == 100
    assert math.isnan(percentage)


def test_negative_effort_or_cost_is_rejected() -> None:
    resources = _resources()
    resources.loc[0, "actual_person_days"] = -1
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_resource_costs(resources)

    items = _cost_items()
    items.loc[0, "estimated_cost"] = -1
    with pytest.raises(ValueError, match="cannot be negative"):
        calculate_project_costs(_resources(), items)


def test_partial_and_many_to_many_allocations_are_visible_and_reconciled() -> None:
    valid = validate_project_product_allocations(
        _mappings(), valid_project_ids=["P1", "P2"], valid_product_ids=["A", "B"]
    )
    coverage = calculate_project_allocation_coverage(
        valid, project_ids=["P1", "P2", "P3"]
    ).set_index("project_id")
    assert coverage.loc["P1", "allocated_percentage"] == 90
    assert coverage.loc["P1", "unallocated_percentage"] == 10
    assert not coverage.loc["P1", "is_fully_allocated"]
    assert coverage.loc["P2", "is_fully_allocated"]
    assert coverage.loc["P3", "unallocated_percentage"] == 100

    costs = calculate_project_costs(_resources(), _cost_items())
    allocated = allocate_engineering_costs(costs, valid)
    p1_a = allocated.query("project_id == 'P1' and product_id == 'A'").iloc[0]
    assert p1_a["allocated_actual_engineering_cost"] == pytest.approx(1_620)
    products = summarize_product_allocations(allocated).set_index("product_id")
    assert products.loc["A", "allocated_actual_engineering_cost"] == pytest.approx(1_720)
    assert products.loc["B", "allocated_actual_engineering_cost"] == pytest.approx(810)


@pytest.mark.parametrize(
    "mappings,match",
    [
        (
            pd.DataFrame(
                [
                    {"project_id": "P1", "product_id": "A", "allocation_percentage": 60},
                    {"project_id": "P1", "product_id": "B", "allocation_percentage": 41},
                ]
            ),
            "exceed 100",
        ),
        (
            pd.DataFrame(
                [
                    {"project_id": "P1", "product_id": "A", "allocation_percentage": 50},
                    {"project_id": "P1", "product_id": "A", "allocation_percentage": 50},
                ]
            ),
            "Duplicate",
        ),
    ],
)
def test_invalid_allocations_are_hard_errors(mappings: pd.DataFrame, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        validate_project_product_allocations(mappings)


def test_unknown_allocation_references_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown product"):
        validate_project_product_allocations(_mappings(), valid_product_ids=["A"])
