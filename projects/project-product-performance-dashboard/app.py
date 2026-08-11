"""Streamlit entry point for the standalone performance dashboard."""

from __future__ import annotations

import sys
from pathlib import Path

import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

st.set_page_config(
    page_title="Project & Product Performance",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

from src.ui.theme import inject_css  # noqa: E402

inject_css()
st.sidebar.markdown("## Project & Product")
st.sidebar.caption("Performance dashboard · fictional sample data")

navigation = st.navigation(
    {
        "Portfolio": [
            st.Page(
                "pages/executive_overview.py",
                title="Executive overview",
                icon=":material/dashboard:",
                default=True,
            ),
        ],
        "Delivery & quality": [
            st.Page(
                "pages/project_performance.py",
                title="Project performance",
                icon=":material/view_timeline:",
            ),
            st.Page(
                "pages/testing_quality.py",
                title="Testing & quality",
                icon=":material/fact_check:",
            ),
        ],
        "Product value": [
            st.Page(
                "pages/product_performance.py",
                title="Product performance",
                icon=":material/trending_up:",
            ),
            st.Page(
                "pages/roi_break_even.py",
                title="Break-even & ROI",
                icon=":material/savings:",
            ),
        ],
    },
    position="sidebar",
    expanded=True,
)
navigation.run()
