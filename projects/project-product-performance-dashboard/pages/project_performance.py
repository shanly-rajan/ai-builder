"""Project delivery and engineering-cost performance page."""

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
from src.ui.filters import project_filters
from src.ui.formatting import currency, days, integer, percent
from src.ui.view_models import load_dashboard_context, scope_projects

configure_page()
context = load_dashboard_context()
selection = project_filters(context.projects, key_prefix="delivery_projects")
scope = scope_projects(context, selection.selected_ids)

page_header(
    "Delivery commitments and engineering investment",
    "Compare plan against outcome without turning team delivery measures into individual "
    "productivity scores.",
    eyebrow="Project performance",
    reporting_date=context.reporting_date,
    fictional=context.fictional_data,
)
active_filter_summary(selection.labels)

metric_grid(
    [
        MetricCard("Completed projects", integer(scope.summary.get("completed_projects"))),
        MetricCard("On-time delivery", percent(scope.summary.get("on_time_delivery_pct"))),
        MetricCard(
            "Median schedule variance",
            days(scope.summary.get("median_schedule_variance_days"), signed=True),
            help="Negative values mean early; positive values mean late.",
        ),
        MetricCard("Active overdue", integer(scope.summary.get("active_overdue_projects"))),
        MetricCard(
            "Estimated engineering cost",
            currency(scope.summary.get("estimated_engineering_cost"), context.currency),
        ),
        MetricCard(
            "Actual engineering cost",
            currency(scope.summary.get("actual_engineering_cost"), context.currency),
            help="Cost to date for incomplete projects.",
        ),
        MetricCard(
            "Cost variance",
            currency(scope.summary.get("cost_variance"), context.currency),
            delta=percent(scope.summary.get("cost_variance_pct"), signed=True),
            delta_color="inverse",
        ),
        MetricCard(
            "Actual effort",
            f"{integer(scope.summary.get('actual_person_days'))} days",
            delta=f"vs {integer(scope.summary.get('estimated_person_days'))} estimated",
            delta_color="off",
            help=(
                "Allocated person-days across fictional engineering roles. Effort is used "
                "for cost and estimation accuracy, never as an individual score."
            ),
        ),
    ],
    columns=4,
)

timeline_tab, variance_tab = st.tabs(["Timeline", "Variance analysis"])
with timeline_tab:
    chart(
        charts.project_timeline(scope.projects),
        key="delivery_timeline",
        caption=(
            "Actual bars are shown only for completed projects; incomplete work is not "
            "assigned a fabricated completion date."
        ),
    )
with variance_tab:
    chart(
        charts.schedule_cost_quadrant(scope.projects),
        key="delivery_quadrant",
        caption=(
            "Negative schedule variance means early; negative cost variance means under estimate."
        ),
    )

left, right = st.columns((1, 1.4), gap="large")
with left:
    chart(
        charts.delivery_outcomes(scope.projects),
        key="delivery_outcomes",
        caption=(
            "Cancelled projects retain sunk cost but are excluded from the delivery-rate "
            "denominator."
        ),
    )
with right:
    breakdown = (
        st.segmented_control(
            "Break variance down by",
            options=["Engineering team", "Project category"],
            default="Engineering team",
            key="delivery_variance_breakdown",
        )
        or "Engineering team"
    )
    variance_frame = (
        scope.variance_by_team if breakdown == "Engineering team" else scope.variance_by_category
    )
    group_column = "engineering_team" if breakdown == "Engineering team" else "category"
    chart(
        charts.grouped_variance_bars(
            variance_frame, group_column=group_column, title=f"Variance by {breakdown.lower()}"
        ),
        key="delivery_variance_grouped",
        caption="Portfolio averages are calculated from completed projects with valid estimates.",
    )

section("Project detail", "Sort, scan, or download the scoped delivery and cost evidence.")
detail = scope.project_table
column_config = {
    "Planned start": st.column_config.DateColumn(format="DD MMM YYYY"),
    "Actual start": st.column_config.DateColumn(format="DD MMM YYYY"),
    "Planned completion": st.column_config.DateColumn(format="DD MMM YYYY"),
    "Actual completion": st.column_config.DateColumn(format="DD MMM YYYY"),
    "Planned duration": st.column_config.NumberColumn(format="%.0f days"),
    "Actual duration": st.column_config.NumberColumn(format="%.0f days"),
    "Schedule variance": st.column_config.NumberColumn(format="%.0f days"),
    "Estimated effort": st.column_config.NumberColumn(format="%.1f days"),
    "Actual effort": st.column_config.NumberColumn(format="%.1f days"),
    "Cost variance %": st.column_config.NumberColumn(format="%.1f%%"),
    "Estimated cost": st.column_config.NumberColumn(format=f"{context.currency} %,.0f"),
    "Actual cost": st.column_config.NumberColumn(format=f"{context.currency} %,.0f"),
}
dataframe(detail, column_config=column_config, height=470, key="delivery_project_table")

metric_definitions(
    {
        "Planned duration": (
            "Inclusive calendar days from planned start through planned completion."
        ),
        "Actual duration": (
            "Inclusive calendar days from actual start through actual completion; "
            "unavailable while incomplete."
        ),
        "Schedule variance": (
            "Actual completion minus planned completion. Negative is early; positive is late."
        ),
        "Cost variance": "Actual engineering cost minus estimated engineering cost.",
        "Cost variance %": (
            "Cost variance divided by estimated engineering cost; N/A when the estimate is zero."
        ),
    }
)
