from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_app_renders_login_without_live_api_call() -> None:
    app = AppTest.from_file(PROJECT_ROOT / "app.py", default_timeout=10).run()

    assert list(app.exception) == []
    assert {item.label for item in app.text_input} == {"Full Name", "OpenAI API Key"}
