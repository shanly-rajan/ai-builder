"""Testing evidence and release readiness page."""

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
from src.ui.formatting import integer, percent
from src.ui.view_models import load_dashboard_context, scope_projects

configure_page()
context = load_dashboard_context()
selection = project_filters(context.projects, key_prefix="quality_projects")
scope = scope_projects(context, selection.selected_ids)

page_header(
    "Release evidence, not a composite score",
    "Trace every readiness decision to required tests, UAT evidence, and release-blocking defects.",
    eyebrow="Testing & quality",
    reporting_date=context.reporting_date,
    fictional=context.fictional_data,
)
active_filter_summary(selection.labels)

metric_grid(
    [
        MetricCard("Total test cases", integer(scope.summary.get("total_test_cases"))),
        MetricCard(
            "Execution rate",
            percent(scope.summary.get("execution_rate_pct")),
            help="Passed, failed, and blocked tests divided by total tests.",
        ),
        MetricCard(
            "Pass rate",
            percent(scope.summary.get("pass_rate_pct")),
            help=(
                "Passed tests divided by executed tests. Blocked tests count as executed "
                "but unsuccessful."
            ),
        ),
        MetricCard("Release ready", integer(scope.summary.get("release_ready_projects"))),
        MetricCard("Open defects", integer(scope.summary.get("open_defects"))),
        MetricCard("Resolved defects", integer(scope.summary.get("resolved_defects"))),
        MetricCard(
            "Blocking defects",
            integer(scope.summary.get("open_release_blocking_defects")),
            help="Open critical or high-severity defects explicitly marked as release blocking.",
        ),
    ],
    columns=4,
)

left, right = st.columns((1.45, 1), gap="large")
with left:
    chart(
        charts.test_status_bars(scope.test_status_by_project),
        key="quality_test_status",
        caption=(
            "Blocked means attempted but unsuccessful; not-run tests remain outside the "
            "executed denominator."
        ),
    )
with right:
    chart(
        charts.readiness_distribution(scope.release_readiness),
        key="quality_readiness",
        caption=(
            "Released projects can still carry a release-exception warning when recorded "
            "evidence does not satisfy the gate."
        ),
    )

left, right = st.columns((1.5, 1), gap="large")
with left:
    chart(
        charts.coverage_heatmap(scope.test_coverage),
        key="quality_coverage",
        caption=(
            "Blank cells indicate non-applicable or missing test evidence rather than a zero score."
        ),
    )
with right:
    chart(
        charts.defect_severity_bars(scope.open_defects),
        key="quality_defects",
        caption="Only defects still open as of the reporting date are shown.",
    )

section(
    "Gate evidence",
    "Every not-ready or exception state includes its explicit failed or missing gate.",
)
dataframe(
    scope.quality_table,
    column_config={
        "Execution rate %": st.column_config.NumberColumn(format="%.1f%%"),
        "Pass rate %": st.column_config.NumberColumn(format="%.1f%%"),
        "Blocking defects": st.column_config.NumberColumn(format="%d"),
        "Exception warning": st.column_config.CheckboxColumn(),
    },
    height=480,
    key="quality_gate_table",
)

metric_definitions(
    {
        "Executed": "Passed + failed + blocked tests.",
        "Execution rate": "Executed tests divided by total tests.",
        "Pass rate": "Passed tests divided by executed tests.",
        "Ready for release": (
            "All applicable required tests passed, UAT passed where applicable, and no "
            "open critical/high release-blocking defect."
        ),
        "Released with exception": (
            "An actual release exists, but recorded gate evidence is incomplete or "
            "contains a blocking failure."
        ),
    }
)
