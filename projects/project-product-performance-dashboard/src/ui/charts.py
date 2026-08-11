"""Plotly chart builders for the dashboard presentation layer."""

from __future__ import annotations

from collections.abc import Sequence

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from src.ui.theme import (
    AMBER,
    BLUE,
    GREEN,
    GRID,
    INK,
    MUTED,
    PURPLE,
    RED,
    SLATE,
    STATUS_COLORS,
    TEAL,
    style_figure,
)


def _empty(title: str, message: str = "No data for the current selection") -> go.Figure:
    figure = go.Figure()
    figure.add_annotation(
        text=message,
        x=0.5,
        y=0.5,
        xref="paper",
        yref="paper",
        showarrow=False,
        font=dict(color=MUTED, size=13),
    )
    figure.update_xaxes(visible=False)
    figure.update_yaxes(visible=False)
    figure.update_layout(title=title)
    return style_figure(figure, height=340, show_legend=False)


def _name_column(frame: pd.DataFrame, entity: str) -> str:
    candidates = (f"{entity}_name", "name", f"{entity}_id")
    return next(
        (candidate for candidate in candidates if candidate in frame.columns), candidates[-1]
    )


def _color(value: object) -> str:
    return STATUS_COLORS.get(_label(value), BLUE)


def _label(value: object) -> str:
    labels = {
        "on_time": "On time",
        "active_overdue": "Active – overdue",
        "active_on_track": "Active – on track",
        "in_progress": "Active – on track",
        "not_started": "Not started",
        "ready_for_release": "Ready for Release",
        "not_ready": "Not Ready",
        "operating_profitable": "Operating profitable",
        "profitable": "Profitable / broken even",
        "approaching_break_even": "Approaching break-even",
    }
    token = str(value).strip()
    normalized = "_".join(
        token.lower().replace("–", " ").replace("-", " ").replace("/", " ").split()
    )
    return labels.get(normalized, token.replace("_", " ").strip().title())


def delivery_outcomes(frame: pd.DataFrame, *, title: str = "Delivery outcomes") -> go.Figure:
    state_column = next(
        (
            column
            for column in ("delivery_outcome", "delivery_state", "outcome")
            if column in frame.columns
        ),
        None,
    )
    if frame.empty or state_column is None:
        return _empty(title)
    if "project_count" in frame.columns:
        summary = frame[[state_column, "project_count"]].copy()
    elif "count" in frame.columns and frame[state_column].is_unique:
        summary = frame[[state_column, "count"]].rename(columns={"count": "project_count"})
    else:
        summary = (
            frame.groupby(state_column, dropna=False).size().rename("project_count").reset_index()
        )
    order = [
        "Early",
        "On time",
        "Late",
        "Active – on track",
        "Active – overdue",
        "Not started",
        "Cancelled",
    ]
    summary[state_column] = summary[state_column].fillna("Not classified").map(_label)
    summary["sort"] = (
        summary[state_column].map({value: index for index, value in enumerate(order)}).fillna(99)
    )
    summary = summary.sort_values("sort")
    figure = go.Figure(
        go.Bar(
            x=summary[state_column],
            y=summary["project_count"],
            marker_color=[_color(value) for value in summary[state_column]],
            text=summary["project_count"],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:,} projects<extra></extra>",
        )
    )
    figure.update_layout(title=title, bargap=0.35)
    figure.update_xaxes(title=None)
    figure.update_yaxes(title="Projects", rangemode="tozero")
    return style_figure(figure, show_legend=False)


def schedule_cost_quadrant(
    frame: pd.DataFrame, *, title: str = "Schedule and cost variance"
) -> go.Figure:
    x_column = next(
        (c for c in ("schedule_variance_pct", "schedule_variance_percentage") if c in frame), None
    )
    y_column = next(
        (c for c in ("cost_variance_pct", "cost_variance_percentage") if c in frame), None
    )
    if frame.empty or not x_column or not y_column:
        return _empty(title)
    plot = frame.dropna(subset=[x_column, y_column]).copy()
    if plot.empty:
        return _empty(title, "Completed projects with comparable estimates will appear here")
    name_column = _name_column(plot, "project")
    color_column = "engineering_team" if "engineering_team" in plot else None
    size_column = next(
        (c for c in ("actual_engineering_cost", "actual_cost", "engineering_cost") if c in plot),
        None,
    )
    hover = [c for c in ("category", "delivery_outcome") if c in plot]
    figure = px.scatter(
        plot,
        x=x_column,
        y=y_column,
        color=color_column,
        size=size_column,
        hover_name=name_column,
        hover_data=hover,
        color_discrete_sequence=[TEAL, BLUE, PURPLE, AMBER, GREEN, RED],
        size_max=34,
    )
    figure.add_vline(x=0, line_color=SLATE, line_width=1)
    figure.add_hline(y=0, line_color=SLATE, line_width=1)
    figure.add_annotation(
        x=-1, y=-1, xref="paper", yref="paper", text="Early / under budget", showarrow=False
    )
    figure.update_layout(title=title)
    figure.update_xaxes(title="Schedule variance (%) · late →")
    figure.update_yaxes(title="Cost variance (%) · over budget →")
    return style_figure(figure, hovermode="closest")


def investment_profit_comparison(
    frame: pd.DataFrame, *, title: str = "Investment and cumulative profit"
) -> go.Figure:
    investment = next(
        (c for c in ("initial_investment", "allocated_engineering_investment") if c in frame), None
    )
    profit = next(
        (c for c in ("cumulative_profit", "latest_cumulative_profit") if c in frame), None
    )
    if frame.empty or not investment or not profit:
        return _empty(title)
    name = _name_column(frame, "product")
    plot = frame.sort_values(profit).copy()
    figure = go.Figure()
    figure.add_bar(
        y=plot[name],
        x=plot[investment],
        name="Initial investment",
        orientation="h",
        marker_color=SLATE,
        hovertemplate="%{y}<br>Investment: %{x:,.0f}<extra></extra>",
    )
    figure.add_bar(
        y=plot[name],
        x=plot[profit],
        name="Cumulative profit",
        orientation="h",
        marker_color=TEAL,
        hovertemplate="%{y}<br>Cumulative profit: %{x:,.0f}<extra></extra>",
    )
    figure.add_vline(x=0, line_color=INK, line_width=1)
    figure.update_layout(title=title, barmode="group")
    figure.update_xaxes(title="Amount")
    figure.update_yaxes(title=None)
    return style_figure(figure, height=max(360, len(plot) * 38 + 100))


def project_timeline(
    frame: pd.DataFrame, *, title: str = "Planned versus actual timeline"
) -> go.Figure:
    required = {"planned_start_date", "planned_completion_date"}
    if frame.empty or not required.issubset(frame.columns):
        return _empty(title)
    name = _name_column(frame, "project")
    rows: list[dict[str, object]] = []
    for _, project in frame.iterrows():
        rows.append(
            {
                "project": project[name],
                "track": "Planned",
                "start": project["planned_start_date"],
                "finish": project["planned_completion_date"],
            }
        )
        if (
            "actual_start_date" in frame
            and "actual_completion_date" in frame
            and pd.notna(project["actual_start_date"])
            and pd.notna(project["actual_completion_date"])
        ):
            rows.append(
                {
                    "project": project[name],
                    "track": "Actual",
                    "start": project["actual_start_date"],
                    "finish": project["actual_completion_date"],
                }
            )
    timeline = pd.DataFrame(rows).dropna(subset=["start", "finish"])
    if timeline.empty:
        return _empty(title)
    figure = px.timeline(
        timeline,
        x_start="start",
        x_end="finish",
        y="project",
        color="track",
        color_discrete_map={"Planned": "#B8C2CF", "Actual": TEAL},
        hover_data={"start": "|%d %b %Y", "finish": "|%d %b %Y", "track": True},
    )
    figure.update_layout(title=title, barmode="overlay")
    figure.update_xaxes(title=None)
    figure.update_yaxes(title=None, autorange="reversed")
    return style_figure(figure, height=max(420, timeline["project"].nunique() * 34 + 120))


def grouped_variance_bars(
    frame: pd.DataFrame,
    *,
    group_column: str,
    title: str,
) -> go.Figure:
    metrics = [c for c in ("schedule_variance_pct", "cost_variance_pct") if c in frame]
    if frame.empty or group_column not in frame or not metrics:
        return _empty(title)
    plot = (
        frame[[group_column, *metrics]]
        .melt(id_vars=group_column, var_name="metric", value_name="variance")
        .dropna(subset=["variance"])
    )
    plot["metric"] = plot["metric"].map(
        {"schedule_variance_pct": "Schedule variance", "cost_variance_pct": "Cost variance"}
    )
    figure = px.bar(
        plot,
        x=group_column,
        y="variance",
        color="metric",
        barmode="group",
        color_discrete_map={"Schedule variance": BLUE, "Cost variance": AMBER},
    )
    figure.add_hline(y=0, line_color=SLATE, line_width=1)
    figure.update_layout(title=title)
    figure.update_xaxes(title=None)
    figure.update_yaxes(title="Average variance (%)")
    return style_figure(figure)


def test_status_bars(frame: pd.DataFrame, *, title: str = "Test execution by project") -> go.Figure:
    statuses = [c for c in ("passed", "failed", "blocked", "not_run") if c in frame]
    if frame.empty or not statuses:
        return _empty(title)
    name = _name_column(frame, "project")
    plot = frame[[name, *statuses]].melt(id_vars=name, var_name="status", value_name="tests")
    labels = {"passed": "Passed", "failed": "Failed", "blocked": "Blocked", "not_run": "Not Run"}
    plot["status_label"] = plot["status"].map(labels)
    figure = px.bar(
        plot,
        y=name,
        x="tests",
        color="status_label",
        orientation="h",
        category_orders={"status_label": ["Passed", "Failed", "Blocked", "Not Run"]},
        color_discrete_map={
            key: STATUS_COLORS[key] for key in ("Passed", "Failed", "Blocked", "Not Run")
        },
    )
    figure.update_layout(title=title, barmode="stack")
    figure.update_xaxes(title="Test cases")
    figure.update_yaxes(title=None, autorange="reversed")
    return style_figure(figure, height=max(390, len(frame) * 34 + 120))


def coverage_heatmap(frame: pd.DataFrame, *, title: str = "Required test coverage") -> go.Figure:
    category = next((c for c in ("test_category", "category") if c in frame), None)
    value = next((c for c in ("execution_rate_pct", "execution_rate") if c in frame), None)
    if frame.empty or not category or not value:
        return _empty(title)
    name = _name_column(frame, "project")
    matrix = frame.pivot_table(index=name, columns=category, values=value, aggfunc="first")
    if matrix.empty:
        return _empty(title)
    figure = go.Figure(
        go.Heatmap(
            z=matrix.values,
            x=matrix.columns,
            y=matrix.index,
            zmin=0,
            zmax=100,
            colorscale=[[0, "#EEF1F5"], [0.01, "#F7D9D7"], [0.65, "#F7D89C"], [1, "#3A9B6A"]],
            colorbar=dict(title="Executed %"),
            hovertemplate="%{y}<br>%{x}<br>Executed: %{z:.1f}%<extra></extra>",
        )
    )
    figure.update_layout(title=title)
    figure.update_xaxes(title=None)
    figure.update_yaxes(title=None, autorange="reversed")
    return style_figure(figure, height=max(400, len(matrix) * 30 + 130), show_legend=False)


def defect_severity_bars(
    frame: pd.DataFrame, *, title: str = "Open defects by severity"
) -> go.Figure:
    severity = "severity" if "severity" in frame else None
    if frame.empty or not severity:
        return _empty(title)
    if "defect_count" in frame:
        plot = frame[[severity, "defect_count"]].copy()
    elif "count" in frame and frame[severity].is_unique:
        plot = frame[[severity, "count"]].rename(columns={"count": "defect_count"})
    else:
        plot = frame.groupby(severity, dropna=False).size().rename("defect_count").reset_index()
    order = ["Critical", "High", "Medium", "Low"]
    plot[severity] = plot[severity].astype(str).str.title()
    plot["sort"] = (
        plot[severity].map({value: index for index, value in enumerate(order)}).fillna(99)
    )
    plot = plot.sort_values("sort")
    palette = {"Critical": "#9F2633", "High": RED, "Medium": AMBER, "Low": BLUE}
    figure = go.Figure(
        go.Bar(
            x=plot[severity],
            y=plot["defect_count"],
            marker_color=[palette.get(v, SLATE) for v in plot[severity]],
            text=plot["defect_count"],
            textposition="outside",
            hovertemplate="%{x}<br>%{y:,} open defects<extra></extra>",
        )
    )
    figure.update_layout(title=title)
    figure.update_xaxes(title=None)
    figure.update_yaxes(title="Open defects", rangemode="tozero")
    return style_figure(figure, show_legend=False)


def readiness_distribution(frame: pd.DataFrame, *, title: str = "Release readiness") -> go.Figure:
    state = next((c for c in ("release_readiness", "readiness_state") if c in frame), None)
    if frame.empty or not state:
        return _empty(title)
    plot = frame.groupby(state, dropna=False).size().rename("projects").reset_index()
    plot[state] = plot[state].fillna("Not Ready").map(_label)
    figure = go.Figure(
        go.Bar(
            y=plot[state],
            x=plot["projects"],
            orientation="h",
            marker_color=[_color(value) for value in plot[state]],
            text=plot["projects"],
            textposition="outside",
            hovertemplate="%{y}<br>%{x:,} projects<extra></extra>",
        )
    )
    figure.update_layout(title=title)
    figure.update_xaxes(title="Projects", rangemode="tozero")
    figure.update_yaxes(title=None)
    return style_figure(figure, show_legend=False)


def product_trend(
    frame: pd.DataFrame,
    *,
    value_columns: Sequence[str],
    title: str,
    y_title: str,
    percent_axis: bool = False,
) -> go.Figure:
    available = [column for column in value_columns if column in frame]
    if frame.empty or "month" not in frame or not available:
        return _empty(title)
    name = _name_column(frame, "product")
    plot = (
        frame[[name, "month", *available]]
        .melt(id_vars=[name, "month"], var_name="metric", value_name="value")
        .dropna(subset=["value"])
    )
    labels = {
        "revenue": "Revenue",
        "operating_cost": "Operating cost",
        "monthly_profit": "Monthly profit",
        "adoption_rate_pct": "Adoption rate",
        "transaction_count": "Transactions",
        "transaction_value": "Transaction value",
        "cumulative_profit": "Cumulative profit",
    }
    plot["metric_label"] = plot["metric"].map(labels).fillna(plot["metric"])
    figure = px.line(
        plot,
        x="month",
        y="value",
        color=name,
        line_dash="metric_label" if len(available) > 1 else None,
        markers=False,
        color_discrete_sequence=[TEAL, BLUE, PURPLE, AMBER, GREEN, RED, "#32788C", "#B3588A"],
    )
    figure.update_layout(title=title)
    figure.update_xaxes(title=None)
    figure.update_yaxes(title=y_title, ticksuffix="%" if percent_axis else None)
    return style_figure(figure, hovermode="x unified")


def product_ranking(
    frame: pd.DataFrame,
    *,
    value_column: str,
    title: str,
    axis_title: str,
    status_column: str | None = None,
) -> go.Figure:
    if frame.empty or value_column not in frame:
        return _empty(title)
    name = _name_column(frame, "product")
    plot = frame.dropna(subset=[value_column]).sort_values(value_column).copy()
    colors = (
        [_color(value) for value in plot[status_column]]
        if status_column and status_column in plot
        else TEAL
    )
    figure = go.Figure(
        go.Bar(
            y=plot[name],
            x=plot[value_column],
            orientation="h",
            marker_color=colors,
            hovertemplate="%{y}<br>%{x:,.1f}<extra></extra>",
        )
    )
    if (plot[value_column] < 0).any():
        figure.add_vline(x=0, line_color=SLATE, line_width=1)
    figure.update_layout(title=title)
    figure.update_xaxes(title=axis_title)
    figure.update_yaxes(title=None)
    return style_figure(figure, height=max(360, len(plot) * 38 + 100), show_legend=False)


def cumulative_profit_curve(
    frame: pd.DataFrame, *, title: str = "Cumulative profit trajectory"
) -> go.Figure:
    if frame.empty or "month" not in frame or "cumulative_profit" not in frame:
        return _empty(title)
    name = _name_column(frame, "product")
    plot = frame.dropna(subset=["cumulative_profit"]).sort_values([name, "month"])
    figure = px.line(
        plot,
        x="month",
        y="cumulative_profit",
        color=name,
        color_discrete_sequence=[TEAL, BLUE, PURPLE, AMBER, GREEN, RED, "#32788C", "#B3588A"],
    )
    if "break_even_month" in plot:
        markers = plot.dropna(subset=["break_even_month"]).drop_duplicates(name, keep="last")
        for _, row in markers.iterrows():
            figure.add_vline(
                x=row["break_even_month"], line_color=GRID, line_dash="dot", line_width=1
            )
    figure.add_hline(y=0, line_color=INK, line_width=1.2)
    figure.update_layout(title=title)
    figure.update_xaxes(title=None)
    figure.update_yaxes(title="Cumulative profit")
    return style_figure(figure, height=470, hovermode="x unified")


def roi_break_even_scatter(
    frame: pd.DataFrame, *, title: str = "ROI and time to break-even"
) -> go.Figure:
    roi = next((c for c in ("roi_pct", "roi_percentage") if c in frame), None)
    months = "months_to_break_even" if "months_to_break_even" in frame else None
    if frame.empty or not roi or not months:
        return _empty(title)
    plot = frame.dropna(subset=[roi]).copy()
    if plot.empty:
        return _empty(title)
    name = _name_column(plot, "product")
    status = next((c for c in ("performance_status", "profitability_status") if c in plot), None)
    figure = px.scatter(
        plot,
        x=months,
        y=roi,
        hover_name=name,
        color=status,
        color_discrete_map=STATUS_COLORS,
        color_discrete_sequence=[TEAL, BLUE, PURPLE, AMBER, RED],
        size="initial_investment" if "initial_investment" in plot else None,
        size_max=34,
    )
    figure.add_hline(y=0, line_color=SLATE, line_width=1)
    figure.update_layout(title=title)
    figure.update_xaxes(title="Months to first break-even")
    figure.update_yaxes(title="ROI (%)")
    return style_figure(figure)
