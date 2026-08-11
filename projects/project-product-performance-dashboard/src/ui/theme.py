"""Dashboard-wide visual tokens and Plotly defaults."""

from __future__ import annotations

from typing import Final

import plotly.graph_objects as go
import streamlit as st

INK: Final = "#10233F"
MUTED: Final = "#5F6F85"
TEAL: Final = "#087E8B"
BLUE: Final = "#2E6FDC"
GREEN: Final = "#248A55"
AMBER: Final = "#B86E00"
RED: Final = "#C43C46"
PURPLE: Final = "#7557C6"
SLATE: Final = "#8A97A8"
GRID: Final = "#E3E9F1"
SURFACE: Final = "#F7F9FC"

STATUS_COLORS: Final[dict[str, str]] = {
    "Early": GREEN,
    "On time": BLUE,
    "Late": RED,
    "Active – on track": TEAL,
    "Active – overdue": AMBER,
    "Cancelled": SLATE,
    "Not started": SLATE,
    "Not Ready": RED,
    "Testing": AMBER,
    "Ready for Release": GREEN,
    "Released": BLUE,
    "Passed": GREEN,
    "Failed": RED,
    "Blocked": AMBER,
    "Not Run": SLATE,
    "Operating profitable": TEAL,
    "Profitable / broken even": GREEN,
    "Approaching break-even": BLUE,
    "Underperforming": RED,
    "New": PURPLE,
}

SEQUENTIAL_TEAL: Final = ["#E7F4F5", "#B8DEE1", "#72BCC2", "#2B979F", TEAL]


def inject_css() -> None:
    """Apply restrained, accessible visual polish to native Streamlit widgets."""

    st.markdown(
        """
        <style>
        :root {
            --dashboard-ink: #10233F;
            --dashboard-muted: #5F6F85;
            --dashboard-border: #E3E9F1;
            --dashboard-surface: #F7F9FC;
            --dashboard-accent: #087E8B;
        }
        .stApp { background: #FFFFFF; }
        [data-testid="stHeader"] { background: rgba(255,255,255,.94); }
        [data-testid="stSidebar"] { border-right: 1px solid var(--dashboard-border); }
        [data-testid="stSidebar"] > div:first-child { background: #F7F9FC; }
        .block-container { max-width: 1480px; padding-top: 2.4rem; padding-bottom: 4rem; }
        h1, h2, h3 { color: var(--dashboard-ink); letter-spacing: -0.025em; }
        h1 { font-size: clamp(2rem, 3vw, 3rem) !important; line-height: 1.05 !important; }
        h2 { margin-top: 1.35rem !important; }
        p, li { color: #33445B; }
        .dashboard-eyebrow {
            color: var(--dashboard-accent); font-size: .76rem; font-weight: 750;
            letter-spacing: .11em; text-transform: uppercase; margin-bottom: .45rem;
        }
        .dashboard-subtitle {
            color: var(--dashboard-muted); font-size: 1.06rem; line-height: 1.55;
            max-width: 850px; margin: .25rem 0 1.25rem;
        }
        .dashboard-notice {
            align-items: center; background: #EEF7F8; border: 1px solid #CBE5E7;
            border-radius: 10px; color: #315A60; display: flex; font-size: .86rem;
            gap: .55rem; margin: .35rem 0 1.35rem; padding: .62rem .82rem;
        }
        .dashboard-dot {
            background: #087E8B; border-radius: 50%; height: .5rem; width: .5rem;
            flex: 0 0 auto;
        }
        [data-testid="stMetric"] {
            background: #FFFFFF; border: 1px solid var(--dashboard-border);
            border-radius: 12px; min-height: 120px; padding: 1rem 1.05rem;
            box-shadow: 0 4px 18px rgba(25,47,78,.045);
        }
        [data-testid="stMetricLabel"] { color: var(--dashboard-muted); font-weight: 650; }
        [data-testid="stMetricValue"] { color: var(--dashboard-ink); letter-spacing: -.035em; }
        [data-testid="stMetricDelta"] svg { display: none; }
        div[data-testid="stExpander"] {
            border: 1px solid var(--dashboard-border); border-radius: 10px;
        }
        div[data-testid="stDataFrame"] {
            border: 1px solid var(--dashboard-border); border-radius: 10px;
            overflow: hidden;
        }
        .dashboard-section-kicker {
            color: var(--dashboard-muted); font-size: .9rem; margin-top: -.4rem;
            margin-bottom: .65rem;
        }
        .dashboard-empty {
            background: var(--dashboard-surface); border: 1px dashed #BBC7D6; border-radius: 10px;
            color: var(--dashboard-muted); padding: 2rem; text-align: center;
        }
        .dashboard-footnote {
            color: var(--dashboard-muted); font-size: .8rem; line-height: 1.45;
        }
        .dashboard-filter-caption {
            color: var(--dashboard-muted); font-size: .78rem; margin: -.15rem 0 .8rem;
        }
        @media (max-width: 640px) {
            .block-container { padding-left: 1rem; padding-right: 1rem; padding-top: 1.4rem; }
            [data-testid="stMetric"] { min-height: 104px; }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def style_figure(
    figure: go.Figure,
    *,
    height: int = 390,
    show_legend: bool = True,
    hovermode: str | None = None,
) -> go.Figure:
    """Apply the shared chart style without changing chart semantics."""

    figure.update_layout(
        height=height,
        margin=dict(l=18, r=18, t=38, b=18),
        paper_bgcolor="#FFFFFF",
        plot_bgcolor="#FFFFFF",
        font=dict(family="Inter, ui-sans-serif, system-ui, sans-serif", color=INK, size=12),
        title=dict(font=dict(size=16, color=INK), x=0),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.01,
            xanchor="right",
            x=1,
            title=None,
            font=dict(size=11),
        ),
        showlegend=show_legend,
        hoverlabel=dict(bgcolor="#FFFFFF", bordercolor=GRID, font=dict(color=INK)),
        hovermode=hovermode,
    )
    figure.update_xaxes(
        showgrid=False, linecolor=GRID, tickfont=dict(color=MUTED), title_font=dict(color=MUTED)
    )
    figure.update_yaxes(
        gridcolor=GRID,
        zerolinecolor="#AEB9C7",
        tickfont=dict(color=MUTED),
        title_font=dict(color=MUTED),
    )
    return figure
