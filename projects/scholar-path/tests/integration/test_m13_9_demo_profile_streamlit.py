"""AppTest coverage for the opt-in, editable ScholarPath demonstration profile."""

import pytest

from scholarpath.ui.app import (
    DEMO_PROFILE_METHODOLOGICAL_INTERESTS,
    DEMO_PROFILE_RESEARCH_STATEMENT,
    DEMO_PROFILE_RESEARCH_TOPICS,
    DEMO_PROFILE_TOGGLE_KEY,
)
from tests.fakes.ui import FakeScholarPathApplication
from tests.integration.test_streamlit_app import (
    _configure_ui_dependencies,
    _new_app,
)


def test_demo_toggle_populates_exact_editable_values_without_starting_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    demo_toggle = app_test.toggle(key=DEMO_PROFILE_TOGGLE_KEY)
    assert demo_toggle.label == "Use demo research profile"
    assert demo_toggle.value is False

    demo_toggle.set_value(True).run()

    assert not app_test.exception
    assert app_test.text_area(key="profile_research_statement").value == (
        DEMO_PROFILE_RESEARCH_STATEMENT
    )
    assert app_test.text_area(key="profile_research_topics").value == DEMO_PROFILE_RESEARCH_TOPICS
    assert app_test.text_input(key="profile_preferred_regions").value == ""
    assert app_test.multiselect(key="profile_study_modes").value == []
    assert app_test.selectbox(key="profile_research_orientation").value == "No preference"
    assert app_test.text_input(key="profile_methodological_interests").value == (
        DEMO_PROFILE_METHODOLOGICAL_INTERESTS
    )
    assert app_test.text_input(key="profile_exclusions").value == ""
    assert service.start_calls == []
    assert "thread_id" not in app_test.session_state

    revised_statement = "A reviewer-edited machine-learning research statement."
    app_test.text_area(key="profile_research_statement").input(revised_statement).run()

    assert app_test.text_area(key="profile_research_statement").value == revised_statement
    assert service.start_calls == []


def test_demo_profile_starts_only_after_explicit_form_submission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    app_test.toggle(key=DEMO_PROFILE_TOGGLE_KEY).set_value(True).run()
    assert service.start_calls == []

    app_test.button(key="candidate_profile_submit").click().run()

    assert not app_test.exception
    assert len(service.start_calls) == 1
    profile = service.start_calls[0].candidate_profile
    assert profile.proposed_research_statement == DEMO_PROFILE_RESEARCH_STATEMENT
    assert profile.research_topics == (
        "Machine Learning",
        "Artificial Intelligence",
        "Software Engineering",
        "Data Science",
        "Computer Science",
    )
    assert profile.preferred_regions == ()
    assert profile.preferred_study_modes == ()
    assert profile.preferred_research_orientation is None
    assert profile.methodological_interests == (
        "Empirical studies",
        "quantitative analysis",
        "benchmark evaluation",
    )
    assert profile.exclusions == ()


def test_disabling_demo_profile_clears_only_unchanged_sample_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    app_test.toggle(key=DEMO_PROFILE_TOGGLE_KEY).set_value(True).run()
    revised_statement = "A reviewer-edited machine-learning research statement."
    app_test.text_area(key="profile_research_statement").input(revised_statement).run()

    app_test.toggle(key=DEMO_PROFILE_TOGGLE_KEY).set_value(False).run()

    assert not app_test.exception
    assert app_test.text_area(key="profile_research_statement").value == revised_statement
    assert app_test.text_area(key="profile_research_topics").value == ""
    assert app_test.text_input(key="profile_methodological_interests").value == ""
    assert app_test.selectbox(key="profile_research_orientation").value == "No preference"
    assert service.start_calls == []
