"""Product adoption and operating performance page."""

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
selection = product_filters(context.products, key_prefix="product_products")
scope = scope_products(context, selection.selected_ids)

page_header(
    "Adoption and operating performance",
    "Follow product usage and economics after launch, independently of which engineering "
    "team contributed delivery work.",
    eyebrow="Product performance",
    reporting_date=context.reporting_date,
    fictional=context.fictional_data,
)
active_filter_summary(selection.labels)

metric_grid(
    [
        MetricCard("Active customers", integer(scope.summary.get("latest_active_customers"))),
        MetricCard("Adoption rate", percent(scope.summary.get("latest_adoption_rate_pct"))),
        MetricCard("Transactions", integer(scope.summary.get("latest_transaction_count"))),
        MetricCard(
            "Transaction value",
            currency(scope.summary.get("latest_transaction_value"), context.currency),
        ),
        MetricCard(
            "Latest revenue", currency(scope.summary.get("latest_month_revenue"), context.currency)
        ),
        MetricCard(
            "Latest profit", currency(scope.summary.get("latest_month_profit"), context.currency)
        ),
        MetricCard("Operating margin", percent(scope.summary.get("latest_margin_pct"))),
        MetricCard(
            "Revenue growth", percent(scope.summary.get("latest_revenue_growth_pct"), signed=True)
        ),
    ],
    columns=4,
)

financial_tab, adoption_tab, transaction_tab = st.tabs(
    ["Revenue & profit", "Adoption", "Transactions"]
)
with financial_tab:
    chart(
        charts.product_trend(
            scope.monthly,
            value_columns=("revenue", "operating_cost", "monthly_profit"),
            title="Monthly operating economics",
            y_title="Amount",
        ),
        key="product_financial_trend",
        caption=(
            "Monthly profit excludes initial investment; lifetime profitability is shown "
            "on the Break-even & ROI page."
        ),
    )
with adoption_tab:
    chart(
        charts.product_trend(
            scope.monthly,
            value_columns=("adoption_rate_pct",),
            title="Customer adoption",
            y_title="Adoption rate",
            percent_axis=True,
        ),
        key="product_adoption_trend",
        caption=(
            "Active customers divided by eligible customers; zero or missing denominators "
            "display as N/A."
        ),
    )
with transaction_tab:
    metric = st.radio(
        "Transaction measure",
        options=["Count", "Value"],
        horizontal=True,
        key="product_transaction_metric",
    )
    column = "transaction_count" if metric == "Count" else "transaction_value"
    chart(
        charts.product_trend(
            scope.monthly,
            value_columns=(column,),
            title=f"Monthly transaction {metric.lower()}",
            y_title=f"Transaction {metric.lower()}",
        ),
        key="product_transaction_trend",
    )

left, right = st.columns(2, gap="large")
with left:
    chart(
        charts.product_ranking(
            scope.products,
            value_column="latest_revenue",
            title="Revenue ranking",
            axis_title="Latest-month revenue",
        ),
        key="product_revenue_ranking",
    )
with right:
    chart(
        charts.product_ranking(
            scope.products,
            value_column="latest_monthly_profit",
            title="Operating-profit ranking",
            axis_title="Latest-month profit",
            status_column="performance_status",
        ),
        key="product_profit_ranking",
        caption=(
            "A product may be operationally profitable this month without having recovered "
            "its initial investment."
        ),
    )

section(
    "Latest product snapshot", "Current operating state and lifetime status are shown separately."
)
dataframe(
    scope.product_table,
    column_config={
        "Launch date": st.column_config.DateColumn(format="DD MMM YYYY"),
        "Latest month": st.column_config.DateColumn(format="MMM YYYY"),
        "Active customers": st.column_config.NumberColumn(format="%d"),
        "Adoption rate %": st.column_config.NumberColumn(format="%.1f%%"),
        "Transactions": st.column_config.NumberColumn(format="%d"),
        "Revenue": st.column_config.NumberColumn(format=f"{context.currency} %,.0f"),
        "Monthly profit": st.column_config.NumberColumn(format=f"{context.currency} %,.0f"),
        "Margin %": st.column_config.NumberColumn(format="%.1f%%"),
        "Operating profitable": st.column_config.CheckboxColumn(),
    },
    height=480,
    key="product_snapshot_table",
)

metric_definitions(
    {
        "Adoption rate": "Active customers divided by eligible customers for the month.",
        "Monthly profit": "Monthly revenue minus monthly operating cost.",
        "Operating margin": "Monthly profit divided by monthly revenue.",
        "Revenue growth": (
            "Current-month revenue minus prior-month revenue, divided by prior-month revenue."
        ),
        "Operating profitable": (
            "Latest observed monthly profit is positive; this does not imply the initial "
            "investment has been recovered."
        ),
    }
)
