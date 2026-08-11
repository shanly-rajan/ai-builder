"""Smoke tests for every Streamlit entry point."""

from pathlib import Path
from unittest.mock import patch

import pytest
from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("relative_path", "expected_title", "minimum_metrics"),
    [
        ("app.py", "From delivery to durable value", 11),
        ("pages/executive_overview.py", "From delivery to durable value", 11),
        (
            "pages/project_performance.py",
            "Delivery commitments and engineering investment",
            8,
        ),
        ("pages/testing_quality.py", "Release evidence, not a composite score", 7),
        ("pages/product_performance.py", "Adoption and operating performance", 8),
        ("pages/roi_break_even.py", "Investment recovery and return", 6),
    ],
)
def test_streamlit_page_renders(
    relative_path: str,
    expected_title: str,
    minimum_metrics: int,
) -> None:
    """Each page renders its main content without a Streamlit exception."""
    app = AppTest.from_file(str(PROJECT_ROOT / relative_path), default_timeout=30).run()

    assert not app.exception
    assert expected_title in [title.value for title in app.title]
    assert len(app.metric) >= minimum_metrics


def test_project_page_handles_cleared_variance_breakdown() -> None:
    """A temporarily empty segmented control falls back without crashing the page."""
    page = PROJECT_ROOT / "pages" / "project_performance.py"

    with patch("streamlit.segmented_control", return_value=None):
        app = AppTest.from_file(str(page), default_timeout=30).run()

    assert not app.exception
    assert "Delivery commitments and engineering investment" in [title.value for title in app.title]
    assert len(app.get("plotly_chart")) == 4
