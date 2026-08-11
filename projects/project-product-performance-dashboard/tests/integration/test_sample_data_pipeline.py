"""Integration coverage for the canonical fictional sample-data pipeline."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal

from src.data.csv_source import CsvDashboardDataSource
from src.data.generator import (
    DEFAULT_SEED,
    generate_sample_data,
    write_sample_data,
)
from src.data.validation import DataValidationError, validate_dashboard_data
from src.models.dataset import DashboardDataBundle
from src.services.delivery_metrics import calculate_delivery_metrics
from src.services.engineering_costs import (
    allocate_engineering_costs,
    calculate_project_costs,
    summarize_product_allocations,
)
from src.services.financial_metrics import (
    calculate_financial_metrics,
    calculate_initial_investments,
    summarize_financials,
)
from src.services.product_metrics import classify_product_performance
from src.services.quality_metrics import assess_release_readiness

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA_DIRECTORY = PROJECT_ROOT / "data" / "sample"


@pytest.fixture(scope="module")
def sample_bundle() -> DashboardDataBundle:
    """Load the committed CSV fixture once for integration tests."""
    return CsvDashboardDataSource(SAMPLE_DATA_DIRECTORY).load()


def test_committed_fixture_matches_canonical_scope(
    sample_bundle: DashboardDataBundle,
) -> None:
    """The committed fixture has the intended entities and reporting window."""
    bundle = sample_bundle
    assert bundle.metadata.seed == DEFAULT_SEED == 20260811
    assert bundle.metadata.reporting_date == pd.Timestamp("2025-12-31")
    assert bundle.metadata.window_start == pd.Timestamp("2024-01-01")
    assert bundle.metadata.window_end == pd.Timestamp("2025-12-01")
    assert bundle.metadata.currency == "USD"
    assert bundle.metadata.fictional_data is True

    configured_months = pd.period_range(
        bundle.metadata.window_start, bundle.metadata.window_end, freq="M"
    )
    assert len(configured_months) == 24
    assert len(bundle.projects) == 24
    assert len(bundle.products) == 10
    assert bundle.projects["engineering_team"].nunique() == 5
    assert set(bundle.resource_allocations["role"]) == {
        "Backend Engineer",
        "Frontend Engineer",
        "QA Engineer",
        "DevOps Engineer",
        "Data Engineer",
        "Product Designer",
        "Security Engineer",
        "Technical Lead",
        "Engineering Lead",
        "Solution Architect",
    }
    assert {
        "project_owner",
        "engineering_lead",
        "product_owner",
    }.issubset(bundle.projects.columns)
    assert bundle.product_monthly_metrics["month"].min() == bundle.metadata.window_start
    assert bundle.product_monthly_metrics["month"].max() == bundle.metadata.window_end

    expected_test_categories = {
        "Unit",
        "Integration",
        "System",
        "Regression",
        "Performance",
        "Security",
        "UAT",
        "Production Validation",
    }
    assert set(bundle.project_test_requirements["test_category"]) == (expected_test_categories)
    assert set(bundle.test_cases["test_category"]) == expected_test_categories
    requirement_counts = bundle.project_test_requirements.groupby("project_id").size()
    assert requirement_counts.eq(8).all()

    assert set(bundle.defects["status"]) <= {"Open", "In Progress", "Resolved"}
    assert bundle.defects["status"].eq("Resolved").any()
    assert bundle.defects["status"].isin(["Open", "In Progress"]).any()


def test_generator_is_deterministic() -> None:
    """The same seed produces byte-equivalent in-memory canonical tables."""
    first = generate_sample_data(DEFAULT_SEED)
    second = generate_sample_data(DEFAULT_SEED)
    assert first.metadata == second.metadata
    for table_name, first_frame in first.iter_tables():
        assert_frame_equal(first_frame, second.tables()[table_name])


def test_csv_round_trip_preserves_canonical_bundle(tmp_path: Path) -> None:
    """The committed fixture is reproducible and survives a typed CSV round trip."""
    generated = generate_sample_data(DEFAULT_SEED)
    write_sample_data(generated, tmp_path)
    loaded = CsvDashboardDataSource(tmp_path).load()

    assert loaded.metadata == generated.metadata
    for table_name, generated_frame in generated.iter_tables():
        assert_frame_equal(generated_frame, loaded.tables()[table_name])
    for committed_path in sorted(SAMPLE_DATA_DIRECTORY.glob("*.csv")):
        regenerated_path = tmp_path / committed_path.name
        assert regenerated_path.read_bytes() == committed_path.read_bytes()


def test_core_validator_accepts_non_sample_window(
    sample_bundle: DashboardDataBundle,
) -> None:
    """Canonical validation remains reusable for shorter future snapshots."""
    shortened = sample_bundle.copy()
    shortened.metadata = replace(
        shortened.metadata,
        window_start=shortened.metadata.window_end,
    )
    shortened.product_monthly_metrics = shortened.product_monthly_metrics.loc[
        shortened.product_monthly_metrics["month"].eq(shortened.metadata.window_end)
    ].reset_index(drop=True)
    validate_dashboard_data(shortened)


def test_validator_rejects_project_overallocation(
    sample_bundle: DashboardDataBundle,
) -> None:
    """Combined project-to-product percentages cannot exceed 100 percent."""
    corrupted = sample_bundle.copy()
    project_rows = corrupted.project_product_mappings["project_id"].eq("PRJ-001")
    corrupted.project_product_mappings.loc[project_rows, "allocation_percentage"] = [80.0, 30.0]

    with pytest.raises(DataValidationError, match="exceed 100%"):
        validate_dashboard_data(corrupted)


def test_validator_reports_bad_types_without_relational_crashes(
    sample_bundle: DashboardDataBundle,
) -> None:
    """Malformed direct inputs produce a validation error instead of an attribute error."""
    corrupted = sample_bundle.copy()
    corrupted.products["launch_date"] = corrupted.products["launch_date"].dt.strftime("%Y-%m-%d")

    with pytest.raises(DataValidationError, match="launch_date must use logical type date"):
        validate_dashboard_data(corrupted)


def test_delivery_cost_and_mapping_archetypes_are_present(
    sample_bundle: DashboardDataBundle,
) -> None:
    """Delivery and allocation data covers every required comparison scenario."""
    delivery = calculate_delivery_metrics(
        sample_bundle.projects,
        as_of=sample_bundle.metadata.reporting_date,
    )
    completed_variance = delivery["schedule_variance_days"].dropna()
    assert completed_variance.lt(0).any()
    assert completed_variance.eq(0).any()
    assert completed_variance.gt(0).any()

    incomplete = delivery[delivery["actual_completion_date"].isna()]
    assert incomplete["days_overdue"].gt(0).any()
    assert incomplete["days_overdue"].eq(0).any()

    project_costs = calculate_project_costs(
        sample_bundle.resource_allocations,
        sample_bundle.project_cost_items,
        project_ids=sample_bundle.projects["project_id"],
    )
    completed_ids = set(
        sample_bundle.projects.loc[sample_bundle.projects["status"].eq("Complete"), "project_id"]
    )
    completed_costs = project_costs[project_costs["project_id"].isin(completed_ids)]
    assert completed_costs["cost_variance"].lt(0).any()
    assert completed_costs["cost_variance"].gt(0).any()

    cancelled_id = sample_bundle.projects.loc[
        sample_bundle.projects["status"].eq("Cancelled"), "project_id"
    ].item()
    cancelled_cost = project_costs.set_index("project_id").loc[
        cancelled_id, "actual_engineering_cost"
    ]
    assert cancelled_cost > 0

    mappings = sample_bundle.project_product_mappings
    assert mappings.groupby("project_id")["product_id"].nunique().gt(1).any()
    assert mappings.groupby("product_id")["project_id"].nunique().gt(1).any()
    allocation_totals = mappings.groupby("project_id")["allocation_percentage"].sum()
    assert allocation_totals.lt(100).any()
    assert allocation_totals.eq(100).any()


def test_quality_fixture_includes_clean_blocked_and_exception_releases(
    sample_bundle: DashboardDataBundle,
) -> None:
    """Quality records exercise transparent readiness and exception branches."""
    readiness = assess_release_readiness(
        sample_bundle.project_test_requirements,
        sample_bundle.test_cases,
        sample_bundle.defects,
        sample_bundle.release_assessments,
        project_ids=sample_bundle.projects["project_id"],
    )
    assert {"Released", "Ready for Release", "Not Ready", "Testing"}.issubset(
        set(readiness["release_readiness"])
    )

    released = readiness[readiness["release_readiness"].eq("Released")]
    assert released["release_gate_passed"].any()
    exception_releases = released[released["release_exception_warning"]]
    assert not exception_releases.empty
    assert exception_releases["release_exception_approved"].all()
    assert exception_releases["required_failed_count"].gt(0).all()
    assert readiness["required_blocked_count"].gt(0).any()
    assert readiness["open_release_blocker_count"].gt(0).any()


def test_product_financial_archetypes_reconcile_end_to_end(
    sample_bundle: DashboardDataBundle,
) -> None:
    """Product histories yield profitable, approaching, weak, and new states."""
    project_costs = calculate_project_costs(
        sample_bundle.resource_allocations,
        sample_bundle.project_cost_items,
        project_ids=sample_bundle.projects["project_id"],
    )
    mapping_costs = allocate_engineering_costs(
        project_costs, sample_bundle.project_product_mappings
    )
    product_allocations = summarize_product_allocations(mapping_costs)
    investments = calculate_initial_investments(
        product_allocations,
        sample_bundle.product_investment_items,
        product_ids=sample_bundle.products["product_id"],
    )
    financials = calculate_financial_metrics(sample_bundle.product_monthly_metrics, investments)
    summary = summarize_financials(financials, products=sample_bundle.products)
    classified = classify_product_performance(
        sample_bundle.products,
        summary,
        sample_bundle.product_monthly_metrics,
        as_of=sample_bundle.metadata.reporting_date,
    )

    expected_statuses = {
        "PRD-001": "Profitable",
        "PRD-002": "Profitable",
        "PRD-003": "Profitable",
        "PRD-004": "Approaching Break-even",
        "PRD-005": "Underperforming",
        "PRD-006": "Profitable",
        "PRD-007": "Approaching Break-even",
        "PRD-008": "Underperforming",
        "PRD-009": "New",
        "PRD-010": "New",
    }
    actual_statuses = classified.set_index("product_id")["performance_status"].to_dict()
    assert actual_statuses == expected_statuses

    summary_by_product = summary.set_index("product_id")
    profitable = {"PRD-001", "PRD-002", "PRD-003", "PRD-006"}
    assert summary_by_product.loc[list(profitable), "ever_broken_even"].all()
    never_broke_even = set(summary_by_product.index) - profitable
    assert not summary_by_product.loc[list(never_broke_even), "ever_broken_even"].any()
    assert investments["initial_investment"].gt(0).all()
