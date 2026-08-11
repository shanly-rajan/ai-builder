"""Investment recovery, break-even, and ROI page."""

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
from src.ui.filters import product_filters
from src.ui.formatting import currency, integer, percent
from src.ui.view_models import load_dashboard_context, scope_products

configure_page()
context = load_dashboard_context()
selection = product_filters(context.products, key_prefix="roi_products")
scope = scope_products(context, selection.selected_ids)

page_header(
    "Investment recovery and return",
    "See the observed path to break-even and distinguish current operating profit from "
    "lifetime financial return.",
    eyebrow="Break-even & ROI",
    reporting_date=context.reporting_date,
    fictional=context.fictional_data,
)
active_filter_summary(selection.labels)

metric_grid(
    [
        MetricCard(
            "Initial investment",
            currency(scope.summary.get("initial_investment"), context.currency),
        ),
        MetricCard(
            "Cumulative revenue",
            currency(scope.summary.get("cumulative_revenue"), context.currency),
        ),
        MetricCard(
            "Cumulative operating cost",
            currency(scope.summary.get("cumulative_operating_cost"), context.currency),
        ),
        MetricCard(
            "Cumulative profit", currency(scope.summary.get("cumulative_profit"), context.currency)
        ),
        MetricCard(
            "Portfolio ROI",
            percent(scope.summary.get("portfolio_roi_pct"), signed=True),
            help="Cumulative profit divided by initial investment for the selected scope.",
        ),
        MetricCard("At break-even", integer(scope.summary.get("break_even_products"))),
    ],
    columns=3,
)

chart(
    charts.cumulative_profit_curve(scope.monthly),
    key="roi_cumulative_curve",
    caption=(
        "The zero line marks investment recovery. Dotted vertical markers indicate each "
        "product's first observed break-even month."
    ),
)

left, right = st.columns((1.15, 1), gap="large")
with left:
    chart(
        charts.roi_break_even_scatter(scope.products),
        key="roi_break_even_scatter",
        caption=(
            "Products without an observed break-even month remain absent from the "
            "horizontal scale but stay visible in the table."
        ),
    )
with right:
    chart(
        charts.product_ranking(
            scope.products,
            value_column="roi_pct",
            title="ROI by product",
            axis_title="ROI (%)",
            status_column="performance_status",
        ),
        key="roi_ranking",
    )

section(
    "Product investment ledger",
    "First crossing is preserved even if a product later dips below zero; current status "
    "is reported separately.",
)
financial_column_config = {
    column: st.column_config.NumberColumn(format=f"{context.currency} %,.0f")
    for column in (
        "Allocated engineering",
        "Launch cost",
        "Setup cost",
        "Initial investment",
        "Cumulative revenue",
        "Cumulative operating cost",
        "Cumulative profit",
    )
}
financial_column_config.update(
    {
        "ROI %": st.column_config.NumberColumn(format="%.1f%%"),
        "First break-even month": st.column_config.DateColumn(format="MMM YYYY"),
        "Months to break-even": st.column_config.NumberColumn(format="%d"),
        "Currently at break-even": st.column_config.CheckboxColumn(),
    }
)
dataframe(
    scope.financial_table,
    column_config=financial_column_config,
    height=480,
    key="roi_financial_table",
)

st.info(
    "Approaching break-even is a simple run-rate indicator: a mature product with positive "
    "trailing-three-month profit "
    "and projected payback within six months. It is not a forecast model."
)

metric_definitions(
    {
        "Initial investment": (
            "Allocated actual engineering cost plus additional launch cost and third-party "
            "setup cost."
        ),
        "Cumulative profit": (
            "Cumulative revenue minus cumulative operating cost minus initial investment."
        ),
        "ROI": (
            "Cumulative profit divided by initial investment; N/A when initial investment is zero."
        ),
        "Break-even month": (
            "First observed month-end when cumulative profit is zero or positive."
        ),
        "Months to break-even": (
            "Inclusive month count from launch to the first observed break-even month."
        ),
    }
)
