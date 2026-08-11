"""Executive portfolio overview page."""

from __future__ import annotations

import streamlit as st

from src.ui import charts
from src.ui.components import (
    MetricCard,
    active_filter_summary,
    chart,
    configure_page,
    dataframe,
    metric_definitions,
    metric_grid,
    page_header,
    section,
)
from src.ui.filters import product_filters, project_filters
from src.ui.formatting import currency, days, integer, percent
from src.ui.view_models import load_dashboard_context, scope_products, scope_projects

configure_page()
context = load_dashboard_context()

page_header(
    "From delivery to durable value",
    "A connected view of commitments, engineering investment, release evidence, "
    "adoption, and financial return.",
    eyebrow="Executive overview",
    reporting_date=context.reporting_date,
    fictional=context.fictional_data,
)

project_filter = project_filters(context.projects, key_prefix="exec_projects")
product_filter = product_filters(context.products, key_prefix="exec_products")
active_filter_summary((*project_filter.labels, *product_filter.labels))

project_scope = scope_projects(context, project_filter.selected_ids)
product_scope = scope_products(context, product_filter.selected_ids)

metric_grid(
    [
        MetricCard(
            "Active projects",
            integer(project_scope.summary.get("active_projects")),
            help="Projects whose current status is In Progress or Testing.",
        ),
        MetricCard(
            "Completed projects",
            integer(project_scope.summary.get("completed_projects")),
            help="Completed non-cancelled projects with an observed actual completion.",
        ),
        MetricCard(
            "On-time delivery",
            percent(project_scope.summary.get("on_time_delivery_pct")),
            help=(
                "Completed non-cancelled projects delivered on or before the planned "
                "completion date."
            ),
        ),
        MetricCard(
            "Delayed projects",
            integer(project_scope.summary.get("delayed_projects")),
            help=(
                f"{integer(project_scope.summary.get('late_projects'))} completed late · "
                f"{integer(project_scope.summary.get('active_overdue_projects'))} active overdue."
            ),
            delta="Needs attention"
            if project_scope.summary.get("delayed_projects", 0)
            else "No delayed work",
            delta_color="inverse",
        ),
        MetricCard(
            "Average schedule variance",
            days(project_scope.summary.get("average_schedule_variance_days"), signed=True),
            help=(
                "Average across completed, non-cancelled projects. Negative means early; "
                "positive means late."
            ),
        ),
        MetricCard(
            "Engineering investment",
            currency(project_scope.summary.get("actual_engineering_cost"), context.currency),
            help=(
                "Actual engineering resource, infrastructure, and external cost; active "
                "work is cost to date."
            ),
        ),
        MetricCard(
            "Failing release criteria",
            integer(project_scope.summary.get("projects_failing_release_criteria")),
            help=(
                "Projects with a failed or incomplete release gate; released exceptions "
                "remain included."
            ),
        ),
        MetricCard(
            "Total product revenue",
            currency(product_scope.summary.get("cumulative_revenue"), context.currency),
            help="Cumulative observed revenue through the reporting date.",
        ),
        MetricCard(
            "Total product profit",
            currency(product_scope.summary.get("cumulative_profit"), context.currency),
            help="Cumulative revenue less cumulative operating cost and initial investment.",
        ),
        MetricCard(
            "Profitable products",
            integer(product_scope.summary.get("profitable_products")),
            help="Products whose latest cumulative profit is non-negative.",
        ),
        MetricCard(
            "Not yet at break-even",
            integer(product_scope.summary.get("not_yet_break_even_products")),
            help="Products that have not reached a non-negative cumulative-profit month.",
        ),
    ],
    columns=4,
)

section(
    "Portfolio signals",
    "Directionally scan delivery predictability and value realization; select a point for detail.",
)
left, right = st.columns((1, 1.45), gap="large")
with left:
    chart(
        charts.delivery_outcomes(project_scope.projects),
        key="executive_delivery_outcomes",
        caption=(
            "Counts are mutually exclusive. Active-overdue projects are separate from "
            "projects completed late."
        ),
    )
with right:
    chart(
        charts.schedule_cost_quadrant(project_scope.projects),
        key="executive_variance_quadrant",
        caption=(
            "Each point is a completed project with comparable estimates; bubble size "
            "represents actual engineering cost."
        ),
    )

chart(
    charts.investment_profit_comparison(product_scope.products),
    key="executive_investment_profit",
    caption=(
        "Cumulative profit already includes the selected product's allocated engineering "
        "investment and setup costs."
    ),
)

section(
    "Priority exceptions",
    "Transparent triggers surface overdue delivery, cost overruns, failed release gates, "
    "and product underperformance.",
)
dataframe(
    project_scope.exceptions,
    column_config={
        "Cost variance %": st.column_config.NumberColumn(format="%.1f%%"),
    },
    height=300,
    key="executive_project_exceptions",
)
if not product_scope.exceptions.empty:
    st.caption("Product value exceptions")
    dataframe(
        product_scope.exceptions,
        column_config={
            "Latest-month profit": st.column_config.NumberColumn(
                format=f"{context.currency} %,.0f"
            ),
            "Cumulative profit": st.column_config.NumberColumn(format=f"{context.currency} %,.0f"),
            "Run-rate months to break-even": st.column_config.NumberColumn(format="%.1f"),
        },
        height=260,
        key="executive_product_exceptions",
    )

metric_definitions(
    {
        "On-time delivery": (
            "Completed non-cancelled projects delivered early or exactly on the planned "
            "completion date, divided by completed non-cancelled projects."
        ),
        "Engineering cost": (
            "Development resource cost plus engineering infrastructure and external "
            "engineering/integration cost. For active work, actual means cost to date."
        ),
        "Release ready": (
            "All applicable required tests passed, UAT passed where applicable, and no "
            "open critical or high release-blocking defect."
        ),
        "Cumulative profit": (
            "Cumulative revenue minus cumulative operating cost minus initial investment."
        ),
        "Break-even": "The first observed month-end when cumulative profit is zero or positive.",
    }
)
