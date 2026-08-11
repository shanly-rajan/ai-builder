"""Reusable Streamlit components for consistent dashboard pages."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass

import pandas as pd
import streamlit as st

from src.ui.formatting import date_label
from src.ui.theme import inject_css


@dataclass(frozen=True)
class MetricCard:
    label: str
    value: str
    delta: str | None = None
    help: str | None = None
    delta_color: str = "normal"


def configure_page() -> None:
    """Apply per-script styling after the app-level page configuration."""

    inject_css()


def page_header(
    title: str,
    subtitle: str,
    *,
    eyebrow: str,
    reporting_date: object,
    fictional: bool = True,
) -> None:
    st.markdown(f'<div class="dashboard-eyebrow">{eyebrow}</div>', unsafe_allow_html=True)
    st.title(title)
    st.markdown(f'<div class="dashboard-subtitle">{subtitle}</div>', unsafe_allow_html=True)
    notice = "Fictional sample data" if fictional else "Connected data"
    st.markdown(
        '<div class="dashboard-notice"><span class="dashboard-dot"></span>'
        f"<span><strong>{notice}</strong> · Metrics current through "
        f"{date_label(reporting_date)}</span></div>",
        unsafe_allow_html=True,
    )


def metric_grid(cards: Sequence[MetricCard], *, columns: int | None = None) -> None:
    if not cards:
        return
    width = columns or min(len(cards), 4)
    for start in range(0, len(cards), width):
        row = st.columns(width)
        for column, card in zip(row, cards[start : start + width], strict=False):
            with column:
                st.metric(
                    card.label,
                    card.value,
                    delta=card.delta,
                    help=card.help,
                    delta_color=card.delta_color,
                )


def section(title: str, description: str | None = None) -> None:
    st.subheader(title)
    if description:
        st.markdown(
            f'<div class="dashboard-section-kicker">{description}</div>', unsafe_allow_html=True
        )


def empty_state(message: str = "No records match the current filters.") -> None:
    st.markdown(f'<div class="dashboard-empty">{message}</div>', unsafe_allow_html=True)


def chart(figure: object, *, key: str, caption: str | None = None) -> None:
    """Render a chart with a concise text alternative beneath it."""

    st.plotly_chart(
        figure,
        width="stretch",
        key=key,
        config={"displayModeBar": False, "responsive": True},
    )
    if caption:
        st.caption(caption)


def dataframe(
    frame: pd.DataFrame,
    *,
    column_config: Mapping[str, object] | None = None,
    height: int = 390,
    key: str | None = None,
) -> None:
    if frame.empty:
        empty_state()
        return
    st.dataframe(
        frame,
        width="stretch",
        hide_index=True,
        column_config=dict(column_config or {}),
        height=height,
        key=key,
    )


def metric_definitions(definitions: Mapping[str, str]) -> None:
    with st.expander("Metric definitions and scope", expanded=False):
        for term, definition in definitions.items():
            st.markdown(f"**{term}**  \n{definition}")


def sidebar_scope_note(message: str) -> None:
    st.sidebar.markdown(
        f'<div class="dashboard-filter-caption">{message}</div>', unsafe_allow_html=True
    )


def active_filter_summary(labels: Iterable[str]) -> None:
    selected = [label for label in labels if label]
    if selected:
        st.caption("Filtered by " + " · ".join(selected))


def callout(message: str, *, kind: str = "info") -> None:
    renderer = {
        "info": st.info,
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
    }.get(kind, st.info)
    renderer(message)
