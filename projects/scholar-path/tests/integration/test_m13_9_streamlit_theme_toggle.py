"""Focused AppTest coverage for the interface-only light and dark appearance toggle."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scholarpath.ui.dependencies as ui_dependencies
from scholarpath.config import ApplicationSettings, Environment
from scholarpath.domain import VerificationEvidenceStandard
from scholarpath.ui import ScholarPathApplicationPort
from scholarpath.ui.theme import (
    DARK_THEME_STYLES,
    LIGHT_THEME_PALETTE,
    LIGHT_THEME_STYLES,
    THEME_TOGGLE_KEY,
)
from tests.fakes.ui import FakeScholarPathApplication

APP_PATH = Path(__file__).resolve().parents[2] / "streamlit_app.py"
THREAD_ID = "candidate-research-m13-9-theme"
CANDIDATE_ID = "candidate-m13-9-theme"


@pytest.fixture(autouse=True)
def _clear_streamlit_resource_cache() -> Iterator[None]:
    """Keep each AppTest inside one isolated service and appearance session."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _configure_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    service: FakeScholarPathApplication,
    verification_standard: VerificationEvidenceStandard = VerificationEvidenceStandard.STRICT,
) -> None:
    settings = ApplicationSettings(
        environment=Environment.TEST,
        verification_evidence_standard=verification_standard,
    )

    def create_application_service(
        resolved_settings: ApplicationSettings | None = None,
    ) -> ScholarPathApplicationPort:
        assert resolved_settings is settings
        return service

    monkeypatch.setattr(ui_dependencies, "configured_application_settings", lambda: settings)
    monkeypatch.setattr(ui_dependencies, "create_application_service", create_application_service)
    monkeypatch.setattr(ui_dependencies, "new_thread_id", lambda: THREAD_ID)
    monkeypatch.setattr(ui_dependencies, "new_candidate_id", lambda: CANDIDATE_ID)
    st.cache_resource.clear()


def _rendered_theme_styles(app_test: AppTest) -> str:
    return "\n".join(
        item.value for item in app_test.markdown if "data-scholarpath-theme" in item.value
    )


def test_dark_is_default_and_toggle_renders_the_light_palette(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_dependencies(monkeypatch, service)
    app_test = AppTest.from_file(APP_PATH, default_timeout=10).run()

    appearance_toggle = app_test.toggle(key=THEME_TOGGLE_KEY)
    assert not app_test.exception
    assert appearance_toggle.label == "Light mode"
    assert appearance_toggle.help == "Switch between ScholarPath's dark and light appearance."
    assert appearance_toggle.value is False
    assert not bool(app_test.session_state[THEME_TOGGLE_KEY])
    assert 'data-scholarpath-theme="dark"' in _rendered_theme_styles(app_test)
    assert 'data-scholarpath-theme="light"' not in _rendered_theme_styles(app_test)

    appearance_toggle.set_value(True).run()

    assert not app_test.exception
    assert app_test.toggle(key=THEME_TOGGLE_KEY).value is True
    assert bool(app_test.session_state[THEME_TOGGLE_KEY])
    assert 'data-scholarpath-theme="light"' in _rendered_theme_styles(app_test)
    assert 'data-scholarpath-theme="dark"' not in _rendered_theme_styles(app_test)
    assert service.start_calls == []
    assert service.resume_calls == []


def test_theme_reruns_preserve_candidate_inputs_and_the_checkpoint_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_dependencies(monkeypatch, service)
    app_test = AppTest.from_file(APP_PATH, default_timeout=10).run()
    research_statement = "Evaluate assurance controls for research software."
    research_topics = "software assurance, responsible AI"

    app_test.text_area(key="profile_research_statement").input(research_statement)
    app_test.text_area(key="profile_research_topics").input(research_topics)
    app_test.toggle(key=THEME_TOGGLE_KEY).set_value(True).run()

    assert app_test.text_area(key="profile_research_statement").value == research_statement
    assert app_test.text_area(key="profile_research_topics").value == research_topics
    assert service.start_calls == []
    assert service.resume_calls == []
    assert "thread_id" not in app_test.session_state

    app_test.button(key="candidate_profile_submit").click().run()
    assert app_test.session_state["thread_id"] == THREAD_ID
    assert len(service.start_calls) == 1
    assert service.start_calls[0].candidate_profile.proposed_research_statement == (
        research_statement
    )

    app_test.toggle(key=THEME_TOGGLE_KEY).set_value(False).run()

    assert app_test.session_state["thread_id"] == THREAD_ID
    assert app_test.session_state[THEME_TOGGLE_KEY] is False
    assert len(service.start_calls) == 1
    assert service.resume_calls == []
    assert service.inspect_calls[-1] == THREAD_ID


def test_theme_css_is_fixed_and_contains_no_remote_or_script_content() -> None:
    for styles in (DARK_THEME_STYLES, LIGHT_THEME_STYLES):
        normalized = styles.casefold()
        assert normalized.strip().startswith("<style data-scholarpath-theme=")
        for unsafe_token in ("@import", "url(", "<script", "javascript:"):
            assert unsafe_token not in normalized


def test_light_mode_renders_readable_form_and_warning_contracts_without_service_calls(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_dependencies(
        monkeypatch,
        service,
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )
    app_test = AppTest.from_file(APP_PATH, default_timeout=10).run()

    app_test.toggle(key=THEME_TOGGLE_KEY).set_value(True).run()

    rendered_styles = _rendered_theme_styles(app_test)
    assert not app_test.exception
    assert app_test.warning
    assert "MVP identity-only verification is active" in app_test.warning[0].value
    assert app_test.text_area(key="profile_research_statement")
    assert app_test.text_input(key="profile_preferred_regions")
    assert app_test.selectbox(key="profile_research_orientation")
    assert app_test.multiselect(key="profile_study_modes")
    assert 'data-testid="stTextAreaRootElement"' in rendered_styles
    assert 'data-testid="stTextInputRootElement"' in rendered_styles
    assert 'data-testid="stAlertContentWarning"' in rendered_styles
    assert LIGHT_THEME_PALETTE.text in rendered_styles
    assert LIGHT_THEME_PALETTE.warning_text in rendered_styles
    assert service.start_calls == []
    assert service.resume_calls == []
