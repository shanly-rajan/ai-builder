"""Streamlit presentation coverage for the explicit deterministic-demo profile."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scholarpath.ui.app as ui_app
import scholarpath.ui.dependencies as ui_dependencies
from scholarpath.config import ApplicationSettings, Environment, RuntimeProfile
from scholarpath.ui import (
    ScholarPathApplicationPort,
    UiStage,
    create_deterministic_demo_application_service,
)
from tests.fakes.ui import FakeScholarPathApplication

APP_PATH = Path(__file__).resolve().parents[2] / "streamlit_app.py"
THREAD_ID = "candidate-research-deterministic-demo"
CANDIDATE_ID = "candidate-deterministic-demo"


@pytest.fixture(autouse=True)
def _clear_streamlit_resource_cache() -> Iterator[None]:
    """Keep the cached fake service inside one AppTest boundary."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _configure_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    service: FakeScholarPathApplication,
    *,
    deterministic_demo: bool,
) -> None:
    """Inject one service, runtime profile, and opaque identifier pair."""

    settings = ApplicationSettings(
        environment=Environment.TEST,
        runtime_profile=(
            RuntimeProfile.DETERMINISTIC_DEMO if deterministic_demo else RuntimeProfile.LIVE
        ),
    )

    def create_application_service(
        resolved_settings: ApplicationSettings | None = None,
    ) -> ScholarPathApplicationPort:
        assert resolved_settings is settings
        return service

    monkeypatch.setattr(
        ui_dependencies,
        "create_application_service",
        create_application_service,
    )
    monkeypatch.setattr(ui_dependencies, "configured_application_settings", lambda: settings)
    monkeypatch.setattr(ui_dependencies, "new_thread_id", lambda: THREAD_ID)
    monkeypatch.setattr(ui_dependencies, "new_candidate_id", lambda: CANDIDATE_ID)
    st.cache_resource.clear()


def _new_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=10).run()


def _submit_minimum_profile(app_test: AppTest) -> None:
    app_test.text_area(key="profile_research_statement").input(
        "Evaluate governance controls for complex digital systems."
    )
    app_test.text_area(key="profile_research_topics").input("digital governance")
    app_test.button(key="candidate_profile_submit").click().run()


def _demo_banners(app_test: AppTest) -> list[str]:
    return [
        warning.value
        for warning in app_test.warning
        if warning.value == ui_app.DETERMINISTIC_DEMO_BANNER
    ]


def test_deterministic_demo_banner_persists_from_intake_through_shortlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_dependencies(monkeypatch, service, deterministic_demo=True)

    app_test = _new_app()

    assert not app_test.exception
    assert _demo_banners(app_test) == [ui_app.DETERMINISTIC_DEMO_BANNER]

    _submit_minimum_profile(app_test)

    assert not app_test.exception
    assert _demo_banners(app_test) == [ui_app.DETERMINISTIC_DEMO_BANNER]
    assert app_test.session_state["thread_id"] == THREAD_ID

    app_test.multiselect(key="approve_supervisor_ids").set_value(["supervisor-001"])
    app_test.button(key="approve_supervisors_submit").click().run()

    assert not app_test.exception
    assert _demo_banners(app_test) == [ui_app.DETERMINISTIC_DEMO_BANNER]
    assert len(service.resume_calls) == 1
    assert service.resume_calls[0].thread_id == THREAD_ID


def test_runtime_banner_is_static_safe_text_and_absent_from_live_profile(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_sentinel = "sk-demo-secret-that-must-not-render"
    service = FakeScholarPathApplication()
    _configure_dependencies(monkeypatch, service, deterministic_demo=False)
    monkeypatch.setenv("OPENAI_API_KEY", secret_sentinel)

    app_test = _new_app()
    _submit_minimum_profile(app_test)

    assert not app_test.exception
    assert ui_app.DETERMINISTIC_DEMO_BANNER not in [item.value for item in app_test.warning]
    for forbidden in (
        secret_sentinel,
        "Dr Amara Ndlovu",
        "Southern Cape Institute of Technology",
        "https://",
    ):
        assert forbidden not in ui_app.DETERMINISTIC_DEMO_BANNER


def test_runtime_profile_and_warning_remain_bound_to_cached_composition(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Changing environment-backed settings cannot relabel a cached demo service as live."""
    service = FakeScholarPathApplication()
    _configure_dependencies(monkeypatch, service, deterministic_demo=True)
    app_test = _new_app()
    changed_settings = ApplicationSettings(
        environment=Environment.TEST,
        runtime_profile=RuntimeProfile.LIVE,
    )
    monkeypatch.setattr(
        ui_dependencies,
        "configured_application_settings",
        lambda: changed_settings,
    )

    app_test.run()

    assert not app_test.exception
    assert _demo_banners(app_test) == [ui_app.DETERMINISTIC_DEMO_BANNER]


def test_real_demo_composition_reaches_review_and_approved_shortlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Drive Streamlit over the real strict graph with only packaged offline ports."""
    settings = ApplicationSettings(
        environment=Environment.TEST,
        runtime_profile=RuntimeProfile.DETERMINISTIC_DEMO,
    )
    service = create_deterministic_demo_application_service(settings)
    monkeypatch.setattr(
        ui_dependencies,
        "create_application_service",
        lambda resolved_settings=None: service,
    )
    monkeypatch.setattr(ui_dependencies, "configured_application_settings", lambda: settings)
    monkeypatch.setattr(ui_dependencies, "new_thread_id", lambda: THREAD_ID)
    monkeypatch.setattr(ui_dependencies, "new_candidate_id", lambda: CANDIDATE_ID)
    st.cache_resource.clear()
    app_test = _new_app()

    _submit_minimum_profile(app_test)

    paused = service.inspect(THREAD_ID)
    assert not app_test.exception
    assert paused is not None
    assert paused.stage is UiStage.REVIEW_SUPERVISORS
    assert len(paused.verified_supervisors) >= 5
    assert len(paused.review_supervisors) == 5
    assert _demo_banners(app_test) == [ui_app.DETERMINISTIC_DEMO_BANNER]

    approved_ids = [supervisor.supervisor_id for supervisor in paused.review_supervisors]
    app_test.multiselect(key="approve_supervisor_ids").set_value(approved_ids)
    app_test.button(key="approve_supervisors_submit").click().run()

    completed = service.inspect(THREAD_ID)
    assert not app_test.exception
    assert completed is not None
    assert completed.stage is UiStage.SUPERVISOR_SHORTLIST
    assert len(completed.shortlisted_supervisors) == 5
    assert "6. Your Supervisor Shortlist" in [item.value for item in app_test.header]
    assert _demo_banners(app_test) == [ui_app.DETERMINISTIC_DEMO_BANNER]
