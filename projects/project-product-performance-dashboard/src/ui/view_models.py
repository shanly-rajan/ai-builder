"""Presentation facade joining canonical data with pure metric services.

This module is the only UI module that knows about service signatures. Pages consume
stable view models and contain no domain calculations.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from src.data.csv_source import CsvDashboardDataSource
from src.services.delivery_metrics import calculate_delivery_metrics, summarize_delivery
from src.services.engineering_costs import calculate_project_costs, cost_variance
from src.services.quality_metrics import (
    assess_release_readiness,
    calculate_defect_metrics,
    calculate_quality_metrics,
    calculate_quality_rates,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SAMPLE_DATA_PATH = PROJECT_ROOT / "data" / "sample"


@dataclass(frozen=True)
class DashboardContext:
    reporting_date: pd.Timestamp
    currency: str
    fictional_data: bool
    projects: pd.DataFrame
    products: pd.DataFrame
    monthly: pd.DataFrame
    resource_allocations: pd.DataFrame
    test_status_by_project: pd.DataFrame
    test_coverage: pd.DataFrame
    open_defects: pd.DataFrame
    release_readiness: pd.DataFrame


@dataclass(frozen=True)
class ProjectScope:
    projects: pd.DataFrame
    summary: dict[str, Any]
    variance_by_team: pd.DataFrame
    variance_by_category: pd.DataFrame
    test_status_by_project: pd.DataFrame
    test_coverage: pd.DataFrame
    open_defects: pd.DataFrame
    release_readiness: pd.DataFrame
    exceptions: pd.DataFrame
    project_table: pd.DataFrame
    quality_table: pd.DataFrame


@dataclass(frozen=True)
class ProductScope:
    products: pd.DataFrame
    monthly: pd.DataFrame
    summary: dict[str, Any]
    exceptions: pd.DataFrame
    product_table: pd.DataFrame
    financial_table: pd.DataFrame


def _build_project_views(bundle: Any) -> tuple[pd.DataFrame, ...]:
    project_ids = bundle.projects["project_id"].astype(str).tolist()
    delivery = calculate_delivery_metrics(bundle.projects, as_of=bundle.metadata.reporting_date)
    costs = calculate_project_costs(
        bundle.resource_allocations,
        bundle.project_cost_items,
        project_ids=project_ids,
    )
    project_quality = calculate_quality_metrics(bundle.test_cases)
    coverage_quality = calculate_quality_metrics(
        bundle.test_cases,
        group_columns=("project_id", "test_category"),
    )
    readiness = assess_release_readiness(
        bundle.project_test_requirements,
        bundle.test_cases,
        bundle.defects,
        bundle.release_assessments,
        project_ids=project_ids,
    )
    defect_metrics = calculate_defect_metrics(bundle.defects)

    effort = (
        bundle.resource_allocations.groupby("project_id", as_index=False)[
            ["estimated_person_days", "actual_person_days"]
        ]
        .sum(min_count=1)
        .copy()
    )
    projects = (
        delivery.merge(costs, on="project_id", how="left", validate="one_to_one")
        .merge(project_quality, on="project_id", how="left", validate="one_to_one")
        .merge(defect_metrics, on="project_id", how="left", validate="one_to_one")
        .merge(readiness, on="project_id", how="left", validate="one_to_one")
        .merge(effort, on="project_id", how="left", validate="one_to_one")
    )
    count_columns = [
        "passed",
        "failed",
        "blocked",
        "not_run",
        "total",
        "executed",
        "open_defects",
        "resolved_defects",
        "open_critical_defects",
        "open_high_defects",
        "open_medium_defects",
        "open_low_defects",
    ]
    projects[count_columns] = projects[count_columns].fillna(0).astype(int)

    test_status = project_quality.merge(
        bundle.projects[["project_id", "project_name"]],
        on="project_id",
        how="left",
        validate="one_to_one",
    )

    required = bundle.project_test_requirements.copy()
    required = required[required["applicable"] & required["required"]]
    coverage = (
        required[["project_id", "test_category"]]
        .drop_duplicates()
        .merge(
            coverage_quality,
            on=["project_id", "test_category"],
            how="left",
            validate="one_to_one",
        )
    )
    coverage = coverage.merge(
        bundle.projects[["project_id", "project_name"]],
        on="project_id",
        how="left",
        validate="many_to_one",
    )

    defect_status = bundle.defects["status"].astype(str).str.lower().str.replace(" ", "_")
    open_defects = bundle.defects[defect_status.isin({"open", "in_progress"})].copy()
    open_defects = open_defects.merge(
        bundle.projects[["project_id", "project_name"]],
        on="project_id",
        how="left",
        validate="many_to_one",
    )
    readiness_named = readiness.merge(
        bundle.projects[["project_id", "project_name"]],
        on="project_id",
        how="left",
        validate="one_to_one",
    )
    return projects, test_status, coverage, open_defects, readiness_named


def _build_product_views(
    bundle: Any, project_costs: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Call the product and finance services, keeping their signatures localized."""

    from src.services.engineering_costs import (  # noqa: PLC0415
        allocate_engineering_costs,
    )
    from src.services.financial_metrics import (  # noqa: PLC0415
        calculate_financial_metrics,
        calculate_initial_investments,
        summarize_financials,
    )
    from src.services.product_metrics import (  # noqa: PLC0415
        calculate_product_metrics,
        classify_product_performance,
        latest_product_metrics,
    )

    allocated = allocate_engineering_costs(project_costs, bundle.project_product_mappings)
    investments = calculate_initial_investments(
        allocated,
        bundle.product_investment_items,
        product_ids=bundle.products["product_id"].astype(str).tolist(),
    )
    product_metrics = calculate_product_metrics(bundle.product_monthly_metrics)
    financial_metrics = calculate_financial_metrics(product_metrics, investments)
    financial_summary = summarize_financials(financial_metrics, products=bundle.products)
    products = classify_product_performance(
        bundle.products,
        financial_summary,
        bundle.product_monthly_metrics,
        as_of=bundle.metadata.reporting_date,
    )
    products = products.merge(
        investments[
            [
                "product_id",
                "allocated_actual_engineering_cost",
                "additional_launch_cost",
                "third_party_setup_cost",
            ]
        ],
        on="product_id",
        how="left",
        validate="one_to_one",
    )
    latest = latest_product_metrics(
        bundle.product_monthly_metrics,
        as_of=bundle.metadata.reporting_date,
    ).rename(
        columns={
            "active_customers": "latest_active_customers",
            "eligible_customers": "latest_eligible_customers",
            "adoption_rate_pct": "latest_adoption_rate_pct",
            "transaction_count": "latest_transaction_count",
            "transaction_value": "latest_transaction_value",
            "revenue": "latest_revenue",
            "operating_cost": "latest_operating_cost",
            "margin_pct": "latest_margin_pct",
            "revenue_growth_pct": "latest_revenue_growth_pct",
        }
    )
    latest_columns = [
        "product_id",
        "latest_active_customers",
        "latest_eligible_customers",
        "latest_adoption_rate_pct",
        "latest_transaction_count",
        "latest_transaction_value",
        "latest_revenue",
        "latest_operating_cost",
        "latest_margin_pct",
        "latest_revenue_growth_pct",
    ]
    products = products.merge(
        latest[latest_columns],
        on="product_id",
        how="left",
        validate="one_to_one",
    )
    monthly = financial_metrics.merge(
        products[["product_id", "product_name"]],
        on="product_id",
        how="left",
        validate="many_to_one",
    )
    monthly = monthly.merge(
        financial_summary[["product_id", "break_even_month"]],
        on="product_id",
        how="left",
        validate="many_to_one",
    )
    return products, monthly


@st.cache_data(show_spinner="Loading fictional portfolio data…")
def load_dashboard_context() -> DashboardContext:
    """Load, validate, and calculate the complete cached dashboard view."""

    bundle = CsvDashboardDataSource(SAMPLE_DATA_PATH).load()
    projects, test_status, coverage, open_defects, readiness = _build_project_views(bundle)
    project_cost_columns = [
        "project_id",
        "estimated_engineering_cost",
        "actual_engineering_cost",
        "cost_variance",
        "cost_variance_pct",
    ]
    products, monthly = _build_product_views(bundle, projects[project_cost_columns])
    return DashboardContext(
        reporting_date=bundle.metadata.reporting_date,
        currency=bundle.metadata.currency,
        fictional_data=bundle.metadata.fictional_data,
        projects=projects,
        products=products,
        monthly=monthly,
        resource_allocations=bundle.resource_allocations,
        test_status_by_project=test_status,
        test_coverage=coverage,
        open_defects=open_defects,
        release_readiness=readiness,
    )


def _ids(frame: pd.DataFrame, column: str, selected_ids: tuple[str, ...]) -> pd.DataFrame:
    if not selected_ids:
        return frame.iloc[0:0].copy()
    return frame[frame[column].astype(str).isin(selected_ids)].copy()


def _project_variance(frame: pd.DataFrame, group_column: str) -> pd.DataFrame:
    completed = frame[frame["delivery_outcome"].isin({"early", "on_time", "late"})]
    return (
        completed.groupby(group_column, as_index=False)[
            ["schedule_variance_pct", "cost_variance_pct"]
        ]
        .mean()
        .reset_index(drop=True)
    )


def _project_exceptions(frame: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for _, project in frame.iterrows():
        concerns: list[str] = []
        outcome = project.get("delivery_outcome")
        if outcome == "late":
            concerns.append(f"completed {int(project['schedule_variance_days'])} days late")
        elif outcome == "active_overdue":
            concerns.append(f"active {int(project['days_overdue'])} days overdue")
        if pd.notna(project.get("cost_variance")) and project["cost_variance"] > 0:
            concerns.append("engineering cost above estimate")
        if project.get("release_gate_passed") is False or project.get("release_gate_passed") == 0:
            concerns.append(str(project.get("readiness_reason", "release criteria not met")))
        if concerns:
            rows.append(
                {
                    "Project": project.get("project_name", project.get("project_id")),
                    "Team": project.get("engineering_team"),
                    "Delivery": str(outcome).replace("_", " ").title(),
                    "Cost variance %": project.get("cost_variance_pct"),
                    "Release state": project.get("release_readiness"),
                    "Why it is surfaced": "; ".join(concerns),
                }
            )
    return pd.DataFrame(rows)


def _project_detail(frame: pd.DataFrame) -> pd.DataFrame:
    columns = {
        "project_name": "Project",
        "project_owner": "Project owner",
        "engineering_lead": "Engineering lead",
        "product_owner": "Product owner",
        "engineering_team": "Team",
        "category": "Category",
        "status": "Status",
        "delivery_outcome": "Delivery outcome",
        "planned_start_date": "Planned start",
        "actual_start_date": "Actual start",
        "planned_completion_date": "Planned completion",
        "actual_completion_date": "Actual completion",
        "planned_duration_days": "Planned duration",
        "actual_duration_days": "Actual duration",
        "schedule_variance_days": "Schedule variance",
        "estimated_person_days": "Estimated effort",
        "actual_person_days": "Actual effort",
        "estimated_engineering_cost": "Estimated cost",
        "actual_engineering_cost": "Actual cost",
        "cost_variance_pct": "Cost variance %",
    }
    return frame[[column for column in columns if column in frame]].rename(columns=columns)


def _quality_detail(frame: pd.DataFrame) -> pd.DataFrame:
    columns = {
        "project_name": "Project",
        "engineering_team": "Team",
        "total": "Tests",
        "execution_rate_pct": "Execution rate %",
        "pass_rate_pct": "Pass rate %",
        "uat_status": "UAT",
        "open_defects": "Open defects",
        "resolved_defects": "Resolved defects",
        "open_critical_defects": "Open critical",
        "open_high_defects": "Open high",
        "open_release_blocker_count": "Blocking defects",
        "release_readiness": "Release state",
        "release_exception_warning": "Exception warning",
        "readiness_reason": "Gate evidence",
    }
    return frame[[column for column in columns if column in frame]].rename(columns=columns)


def scope_projects(context: DashboardContext, selected_ids: tuple[str, ...]) -> ProjectScope:
    projects = _ids(context.projects, "project_id", selected_ids)
    delivery_summary = dict(summarize_delivery(projects))
    estimate = projects["estimated_engineering_cost"].sum(min_count=1)
    actual = projects["actual_engineering_cost"].sum(min_count=1)
    variance, variance_pct = cost_variance(actual, estimate)

    count_columns = ["passed", "failed", "blocked", "not_run"]
    test_counts = {
        column: int(projects[column].sum()) if column in projects else 0 for column in count_columns
    }
    quality_summary = calculate_quality_rates(**test_counts)
    outcomes = projects.get("delivery_outcome", pd.Series(index=projects.index, dtype=str))
    normalized_status = (
        projects.get("status", pd.Series(index=projects.index, dtype=str))
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )
    cancelled = normalized_status.isin({"cancelled", "canceled"})
    gate_passed = projects.get(
        "release_gate_passed", pd.Series(False, index=projects.index, dtype=bool)
    ).fillna(False)
    active_projects = int(normalized_status.isin({"in_progress", "testing"}).sum())
    delayed_projects = int(outcomes.isin({"late", "active_overdue"}).sum())
    summary = {
        **delivery_summary,
        **quality_summary,
        "total_test_cases": quality_summary["total"],
        "executed_test_cases": quality_summary["executed"],
        "active_projects": active_projects,
        "delayed_projects": delayed_projects,
        "estimated_engineering_cost": estimate,
        "actual_engineering_cost": actual,
        "cost_variance": variance,
        "cost_variance_pct": variance_pct,
        "estimated_person_days": projects.get("estimated_person_days", pd.Series(dtype=float)).sum(
            min_count=1
        ),
        "actual_person_days": projects.get("actual_person_days", pd.Series(dtype=float)).sum(
            min_count=1
        ),
        "release_ready_projects": int(gate_passed.sum()),
        "projects_failing_release_criteria": int((~gate_passed & ~cancelled).sum()),
        "open_release_blocking_defects": int(
            projects.get("open_release_blocker_count", pd.Series(dtype=float)).sum()
        ),
        "open_defects": int(projects.get("open_defects", pd.Series(dtype=float)).sum()),
        "resolved_defects": int(projects.get("resolved_defects", pd.Series(dtype=float)).sum()),
    }

    test_status = _ids(context.test_status_by_project, "project_id", selected_ids)
    coverage = _ids(context.test_coverage, "project_id", selected_ids)
    defects = _ids(context.open_defects, "project_id", selected_ids)
    readiness = _ids(context.release_readiness, "project_id", selected_ids)
    return ProjectScope(
        projects=projects,
        summary=summary,
        variance_by_team=_project_variance(projects, "engineering_team"),
        variance_by_category=_project_variance(projects, "category"),
        test_status_by_project=test_status,
        test_coverage=coverage,
        open_defects=defects,
        release_readiness=readiness,
        exceptions=_project_exceptions(projects),
        project_table=_project_detail(projects),
        quality_table=_quality_detail(projects),
    )


def scope_products(context: DashboardContext, selected_ids: tuple[str, ...]) -> ProductScope:
    """Build a product scope after product/financial services add canonical metrics."""

    products = _ids(context.products, "product_id", selected_ids)
    monthly = _ids(context.monthly, "product_id", selected_ids)
    return _scope_products_from_calculated(products, monthly)


def _scope_products_from_calculated(products: pd.DataFrame, monthly: pd.DataFrame) -> ProductScope:
    """Presentation aggregation over service-calculated product rows."""

    from src.services._utils import safe_percentage  # noqa: PLC0415
    from src.services.portfolio_metrics import weighted_rate_from_counts  # noqa: PLC0415

    def numeric_sum(column: str) -> float:
        if column not in products:
            return float("nan")
        return float(pd.to_numeric(products[column], errors="coerce").sum(min_count=1))

    latest_profit = numeric_sum("latest_monthly_profit")
    latest_revenue = numeric_sum("latest_revenue")
    initial_investment = numeric_sum("initial_investment")
    cumulative_profit = numeric_sum("cumulative_profit")
    current_break_even = products.get(
        "currently_at_or_above_break_even",
        pd.Series(False, index=products.index, dtype=bool),
    ).fillna(False)
    ever_break_even = products.get(
        "ever_broken_even", pd.Series(False, index=products.index, dtype=bool)
    ).fillna(False)
    summary = {
        "latest_active_customers": numeric_sum("latest_active_customers"),
        "latest_adoption_rate_pct": weighted_rate_from_counts(
            products.get("latest_active_customers", pd.Series(dtype=float)),
            products.get("latest_eligible_customers", pd.Series(dtype=float)),
        ),
        "latest_transaction_count": numeric_sum("latest_transaction_count"),
        "latest_transaction_value": numeric_sum("latest_transaction_value"),
        "latest_month_revenue": latest_revenue,
        "latest_month_profit": latest_profit,
        "latest_margin_pct": float(safe_percentage(latest_profit, latest_revenue)),
        "latest_revenue_growth_pct": float(
            pd.to_numeric(
                products.get("latest_revenue_growth_pct", pd.Series(dtype=float)),
                errors="coerce",
            ).mean()
        ),
        "initial_investment": initial_investment,
        "cumulative_revenue": numeric_sum("cumulative_revenue"),
        "cumulative_operating_cost": numeric_sum("cumulative_operating_cost"),
        "cumulative_profit": cumulative_profit,
        "portfolio_roi_pct": float(safe_percentage(cumulative_profit, initial_investment)),
        "break_even_products": int(ever_break_even.sum()),
        "profitable_products": int(current_break_even.sum()),
        "not_yet_break_even_products": int((~ever_break_even).sum()),
    }
    exception_rows = products[
        products.get("performance_status", pd.Series(index=products.index, dtype=str)).eq(
            "Underperforming"
        )
    ]
    exception_columns = {
        "product_name": "Product",
        "product_owner": "Product owner",
        "performance_status": "Performance status",
        "latest_monthly_profit": "Latest-month profit",
        "cumulative_profit": "Cumulative profit",
        "projected_months_to_break_even": "Run-rate months to break-even",
    }
    exceptions = exception_rows[
        [column for column in exception_columns if column in exception_rows]
    ].rename(columns=exception_columns)

    product_columns = {
        "product_name": "Product",
        "product_owner": "Product owner",
        "category": "Category",
        "lifecycle_status": "Lifecycle",
        "launch_date": "Launch date",
        "latest_month": "Latest month",
        "latest_active_customers": "Active customers",
        "latest_adoption_rate_pct": "Adoption rate %",
        "latest_transaction_count": "Transactions",
        "latest_revenue": "Revenue",
        "latest_monthly_profit": "Monthly profit",
        "latest_margin_pct": "Margin %",
        "operating_profitable": "Operating profitable",
        "performance_status": "Lifetime status",
    }
    product_table = products[[column for column in product_columns if column in products]].rename(
        columns=product_columns
    )

    finance_columns = {
        "product_name": "Product",
        "allocated_actual_engineering_cost": "Allocated engineering",
        "additional_launch_cost": "Launch cost",
        "third_party_setup_cost": "Setup cost",
        "initial_investment": "Initial investment",
        "cumulative_revenue": "Cumulative revenue",
        "cumulative_operating_cost": "Cumulative operating cost",
        "cumulative_profit": "Cumulative profit",
        "roi_pct": "ROI %",
        "break_even_month": "First break-even month",
        "months_to_break_even": "Months to break-even",
        "currently_at_or_above_break_even": "Currently at break-even",
        "performance_status": "Performance status",
    }
    financial_table = products[[column for column in finance_columns if column in products]].rename(
        columns=finance_columns
    )
    return ProductScope(
        products=products,
        monthly=monthly,
        summary=summary,
        exceptions=exceptions,
        product_table=product_table,
        financial_table=financial_table,
    )
