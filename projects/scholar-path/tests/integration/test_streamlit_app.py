"""Headless integration coverage for the M11 ScholarPath Streamlit application."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scholarpath.ui.app as ui_app
import scholarpath.ui.dependencies as ui_dependencies
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRejectResponse,
    CandidateRequestMoreResponse,
)
from scholarpath.ui import ScholarPathApplicationPort
from tests.fakes.ui import FakeScholarPathApplication

APP_PATH = Path(__file__).resolve().parents[2] / "streamlit_app.py"
THREAD_ID = "candidate-research-ui-thread-001"
CANDIDATE_ID = "candidate-ui-001"
RESEARCH_STATEMENT = "How can enterprise architecture support responsible digital transformation?"
RESEARCH_TOPICS = "enterprise architecture, responsible AI"
EXPECTED_STAGE_LABELS = (
    "1. Your Doctoral Research Profile",
    "2. Supervisor Search Progress",
    "3. Prospective Supervisors",
    "4. Verified Supervisors",
    "5. Review Supervisors",
    "6. Your Supervisor Shortlist",
)
EXPECTED_PROGRESS_NODES = (
    "load_candidate_preferences",
    "plan_supervisor_searches",
    "discover_prospective_supervisors",
    "extract_supervisor_evidence",
    "evaluate_research_fit",
    "candidate_review_gate",
)


@pytest.fixture(autouse=True)
def _clear_streamlit_resource_cache() -> Iterator[None]:
    """Prevent a cached fake service from crossing a pytest test boundary."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _configure_ui_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    service: FakeScholarPathApplication,
    *,
    thread_ids: tuple[str, ...] = (THREAD_ID,),
    candidate_ids: tuple[str, ...] = (CANDIDATE_ID,),
) -> None:
    """Install one deterministic service and opaque-ID sequence at the UI boundary."""
    thread_id_iterator = iter(thread_ids)
    candidate_id_iterator = iter(candidate_ids)

    def create_application_service() -> ScholarPathApplicationPort:
        return service

    def new_thread_id() -> str:
        return next(thread_id_iterator)

    def new_candidate_id() -> str:
        return next(candidate_id_iterator)

    monkeypatch.setattr(
        ui_dependencies,
        "create_application_service",
        create_application_service,
    )
    monkeypatch.setattr(ui_dependencies, "new_thread_id", new_thread_id)
    monkeypatch.setattr(ui_dependencies, "new_candidate_id", new_candidate_id)
    st.cache_resource.clear()


def _new_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=10).run()


def _submit_candidate_profile(
    app_test: AppTest,
    *,
    research_statement: str = RESEARCH_STATEMENT,
    research_topics: str = RESEARCH_TOPICS,
) -> None:
    """Complete and submit the keyed intake form in one simulated browser action."""
    app_test.text_area(key="profile_research_statement").input(research_statement)
    app_test.text_area(key="profile_research_topics").input(research_topics)
    app_test.text_input(key="profile_preferred_regions").input("South Africa, Netherlands")
    app_test.multiselect(key="profile_study_modes").set_value(["part-time", "hybrid"])
    app_test.selectbox(key="profile_research_orientation").set_value("applied")
    app_test.text_input(key="profile_methodological_interests").input("design science, case study")
    app_test.text_input(key="profile_exclusions").input("purely theoretical programmes")
    app_test.button(key="candidate_profile_submit").click().run()


def test_candidate_profile_form_renders_every_requested_control(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)

    app_test = _new_app()

    assert not app_test.exception
    assert app_test.title[0].value == "ScholarPath"
    assert [item.value for item in app_test.header] == [EXPECTED_STAGE_LABELS[0]]
    assert app_test.text_area(key="profile_research_statement").label == (
        "Proposed research statement *"
    )
    assert app_test.text_area(key="profile_research_topics").label == "Research topics *"
    assert app_test.text_input(key="profile_preferred_regions").label == "Preferred regions"
    assert app_test.multiselect(key="profile_study_modes").label == "Study mode"
    assert app_test.selectbox(key="profile_research_orientation").label == ("Research orientation")
    assert app_test.text_input(key="profile_methodological_interests").label == (
        "Methodological interests"
    )
    assert app_test.text_input(key="profile_exclusions").label == "Exclusions"
    assert app_test.button(key="candidate_profile_submit").label == ("Start Supervisor Research")
    assert service.start_calls == []
    assert service.inspect_calls == []


def test_candidate_profile_form_validates_required_fields_before_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    app_test.button(key="candidate_profile_submit").click().run()

    assert not app_test.exception
    assert [item.value for item in app_test.error] == [
        "Enter a proposed research statement and at least one research topic."
    ]
    assert service.start_calls == []
    assert "thread_id" not in app_test.session_state


def test_candidate_and_supervisor_labels_use_canonical_terminology(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)

    app_test = _new_app()

    navigation = app_test.caption[0].value
    for stage_label in EXPECTED_STAGE_LABELS:
        assert stage_label in navigation
    visible_labels = "\n".join(
        (
            navigation,
            *(item.label for item in app_test.text_area),
            *(item.label for item in app_test.text_input),
            *(item.label for item in app_test.multiselect),
            *(item.label for item in app_test.selectbox),
            *(item.label for item in app_test.button),
        )
    ).casefold()
    assert "supervisor candidate" not in visible_labels
    assert "approved candidate" not in visible_labels
    assert "prospective supervisors" in visible_labels
    assert "verified supervisors" in visible_labels
    assert "your supervisor shortlist" in visible_labels


def test_starting_research_run_maps_the_form_and_keeps_graph_state_out_of_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_candidate_profile(app_test)

    assert not app_test.exception
    assert len(service.start_calls) == 1
    start_call = service.start_calls[0]
    assert start_call.thread_id == THREAD_ID
    assert start_call.candidate_profile.candidate_id == CANDIDATE_ID
    assert start_call.candidate_profile.proposed_research_statement == RESEARCH_STATEMENT
    assert start_call.candidate_profile.research_topics == (
        "enterprise architecture",
        "responsible AI",
    )
    assert start_call.candidate_profile.preferred_regions == (
        "South Africa",
        "Netherlands",
    )
    assert start_call.candidate_profile.preferred_study_modes == ("part-time", "hybrid")
    assert start_call.candidate_profile.preferred_research_orientation == "applied"
    assert start_call.candidate_profile.methodological_interests == (
        "design science",
        "case study",
    )
    assert start_call.candidate_profile.exclusions == ("purely theoretical programmes",)
    assert app_test.session_state["thread_id"] == THREAD_ID
    for graph_state_key in (
        "candidate_profile",
        "prospective_supervisors",
        "verified_supervisors",
        "research_fit_assessments",
        "proposed_shortlist",
        "shortlisted_supervisors",
        "execution_log",
    ):
        assert graph_state_key not in app_test.session_state.filtered_state


def test_progress_state_shows_only_canonical_node_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    assert not app_test.exception
    assert len(app_test.status) == 1
    status = app_test.status[0]
    assert status.label == "Canonical LangGraph progress"
    assert status.state == "complete"
    assert [item.value for item in status.markdown] == [
        f"{sequence}. {node_name}"
        for sequence, node_name in enumerate(EXPECTED_PROGRESS_NODES, start=1)
    ]
    assert "chain-of-thought" not in repr(status).casefold()
    assert "raw_search_results" not in repr(status)


def test_verified_supervisor_evidence_and_review_fields_are_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    rendered_markdown = "\n".join(item.value for item in app_test.markdown)
    rendered_subheaders = [item.value for item in app_test.subheader]
    rendered_metrics = [(item.label, item.value) for item in app_test.metric]

    assert not app_test.exception
    assert EXPECTED_STAGE_LABELS[3] in [item.value for item in app_test.header]
    assert "Dr Amara Ndlovu" in rendered_subheaders
    assert "Professor Elias Hart" in rendered_subheaders
    assert "Institution: Southern Cape Institute of Technology" in rendered_markdown
    assert "Verification status: Verified" in rendered_markdown
    assert ("Research Fit Score", "87/100") in rendered_metrics
    assert "Fit explanation:" in rendered_markdown
    assert "Evidence confidence: Medium" in rendered_markdown
    assert "Availability status: Not stated" in rendered_markdown
    assert "Independent review status: Accepted" in rendered_markdown
    assert "Concerns:" in rendered_markdown
    assert "Evidence sources:" in rendered_markdown
    assert "https://evidence.scholarpath.example/supervisor-001/identity" in rendered_markdown
    assert "The profile names Dr Amara Ndlovu." in rendered_markdown


def test_approval_resumes_the_same_thread_and_renders_only_the_selected_shortlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    assert service.resume_calls == []
    assert EXPECTED_STAGE_LABELS[5] not in [item.value for item in app_test.header]
    app_test.multiselect(key="approve_supervisor_ids").set_value(["supervisor-002"])
    app_test.button(key="approve_supervisors_submit").click().run()

    assert not app_test.exception
    assert len(service.resume_calls) == 1
    resume_call = service.resume_calls[0]
    assert resume_call.thread_id == THREAD_ID
    assert resume_call.checkpoint_token == "ui-checkpoint-001"
    assert isinstance(resume_call.response, CandidateApproveResponse)
    assert resume_call.response.supervisor_ids == ("supervisor-002",)
    assert EXPECTED_STAGE_LABELS[5] in [item.value for item in app_test.header]
    assert [item.value for item in app_test.success] == [
        "These Verified Supervisors were explicitly approved and shortlisted."
    ]
    assert app_test.subheader[-1].value == "Professor Elias Hart"
    assert app_test.session_state["thread_id"] == THREAD_ID


def test_rejection_requires_a_reason_then_resumes_the_same_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    app_test.selectbox(key="reject_supervisor_id").set_value("supervisor-002")
    app_test.button(key="reject_supervisor_submit").click().run()

    assert [item.value for item in app_test.error] == [
        "Provide a reason before rejecting a Supervisor."
    ]
    assert service.resume_calls == []

    app_test.text_area(key="reject_supervisor_reason").input(
        "The methodological focus does not match the proposed study."
    )
    app_test.button(key="reject_supervisor_submit").click().run()

    assert not app_test.exception
    assert not app_test.error
    assert len(service.resume_calls) == 1
    resume_call = service.resume_calls[0]
    assert resume_call.thread_id == THREAD_ID
    assert resume_call.checkpoint_token == "ui-checkpoint-001"
    assert isinstance(resume_call.response, CandidateRejectResponse)
    assert resume_call.response.rejections[0].supervisor_id == "supervisor-002"
    assert resume_call.response.rejections[0].reason == (
        "The methodological focus does not match the proposed study."
    )
    assert any("Review iteration 2 of 2" in item.value for item in app_test.markdown)
    assert not app_test.success


def test_request_more_requires_a_revision_then_resumes_with_typed_preferences(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    app_test.button(key="request_more_submit").click().run()

    assert [item.value for item in app_test.error] == [
        "Enter at least one revised preference before requesting more research."
    ]
    assert service.resume_calls == []

    app_test.text_input(key="request_more_research_topics").input("AI governance")
    app_test.text_input(key="request_more_regions").input("Germany, Netherlands")
    app_test.multiselect(key="request_more_study_modes").set_value(["hybrid"])
    app_test.selectbox(key="request_more_orientation").set_value("applied")
    app_test.text_input(key="request_more_methods").input("action research")
    app_test.text_input(key="request_more_constraints").input("part-time programme")
    app_test.text_input(key="request_more_exclusions").input("pure theory")
    app_test.button(key="request_more_submit").click().run()

    assert not app_test.exception
    assert not app_test.error
    assert len(service.resume_calls) == 1
    resume_call = service.resume_calls[0]
    assert resume_call.thread_id == THREAD_ID
    assert resume_call.checkpoint_token == "ui-checkpoint-001"
    assert isinstance(resume_call.response, CandidateRequestMoreResponse)
    revision = resume_call.response.revised_preferences
    assert revision.research_topics == ("AI governance",)
    assert revision.preferred_regions == ("Germany", "Netherlands")
    assert revision.preferred_study_modes == ("hybrid",)
    assert revision.preferred_research_orientation == "applied"
    assert revision.methodological_interests == ("action research",)
    assert revision.constraints == ("part-time programme",)
    assert revision.exclusions == ("pure theory",)
    assert any("Review iteration 2 of 2" in item.value for item in app_test.markdown)


def test_existing_session_thread_is_reopened_without_starting_a_second_graph_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    first_session = _new_app()
    _submit_candidate_profile(first_session)

    reopened_session = AppTest.from_file(APP_PATH, default_timeout=10)
    reopened_session.session_state["thread_id"] = THREAD_ID
    reopened_session.run()

    assert not reopened_session.exception
    assert len(service.start_calls) == 1
    assert service.inspect_calls[-1] == THREAD_ID
    assert reopened_session.session_state["thread_id"] == THREAD_ID
    assert EXPECTED_STAGE_LABELS[1] in [item.value for item in reopened_session.header]
    assert "candidate_profile_submit" not in {button.key for button in reopened_session.button}


def test_api_failure_is_rendered_as_recoverable_without_a_stack_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    unsafe_provider_detail = "Provider transport failed at internal/private/provider.py:42"
    service = FakeScholarPathApplication(start_error=RuntimeError(unsafe_provider_detail))
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_candidate_profile(app_test)

    assert not app_test.exception
    assert [item.value for item in app_test.error] == [ui_app.RECOVERABLE_SERVICE_MESSAGE]
    assert unsafe_provider_detail not in repr(app_test)
    assert "Traceback" not in repr(app_test)
    assert "thread_id" not in app_test.session_state
    assert [item.value for item in app_test.header] == [EXPECTED_STAGE_LABELS[0]]


def test_provider_secrets_are_not_rendered_or_copied_to_session_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_sentinel = "sk-ui-secret-that-must-never-render"
    monkeypatch.setenv("OPENAI_API_KEY", secret_sentinel)
    monkeypatch.setenv("LANGSMITH_API_KEY", secret_sentinel)
    service = FakeScholarPathApplication(resume_error=RuntimeError(secret_sentinel))
    _configure_ui_dependencies(monkeypatch, service)
    app_test = AppTest.from_file(APP_PATH, default_timeout=10)
    app_test.secrets["OPENAI_API_KEY"] = secret_sentinel
    app_test.run()
    _submit_candidate_profile(app_test)

    app_test.multiselect(key="approve_supervisor_ids").set_value(["supervisor-001"])
    app_test.button(key="approve_supervisors_submit").click().run()

    assert not app_test.exception
    assert [item.value for item in app_test.error] == [ui_app.RECOVERABLE_SERVICE_MESSAGE]
    assert secret_sentinel not in repr(app_test.main)
    assert secret_sentinel not in repr(app_test.session_state.filtered_state)
    assert app_test.session_state["thread_id"] == THREAD_ID
    assert service.resume_calls == []


def test_candidate_data_and_thread_ids_do_not_leak_between_app_sessions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(
        monkeypatch,
        service,
        thread_ids=("candidate-research-thread-a", "candidate-research-thread-b"),
        candidate_ids=("candidate-a", "candidate-b"),
    )
    first_session = _new_app()
    _submit_candidate_profile(
        first_session,
        research_statement="Candidate A studies enterprise architecture governance.",
        research_topics="enterprise architecture",
    )

    second_session = _new_app()

    assert "thread_id" not in second_session.session_state
    assert second_session.text_area(key="profile_research_statement").value == ""
    assert second_session.text_area(key="profile_research_topics").value == ""
    assert "Candidate A studies enterprise architecture governance." not in repr(second_session)

    _submit_candidate_profile(
        second_session,
        research_statement="Candidate B studies responsible AI assurance.",
        research_topics="responsible AI",
    )

    assert [call.thread_id for call in service.start_calls] == [
        "candidate-research-thread-a",
        "candidate-research-thread-b",
    ]
    assert [call.candidate_profile.candidate_id for call in service.start_calls] == [
        "candidate-a",
        "candidate-b",
    ]
    assert service.start_calls[0].candidate_profile.proposed_research_statement != (
        service.start_calls[1].candidate_profile.proposed_research_statement
    )
    assert first_session.session_state["thread_id"] == "candidate-research-thread-a"
    assert second_session.session_state["thread_id"] == "candidate-research-thread-b"

    first_session.run()

    assert first_session.session_state["thread_id"] == "candidate-research-thread-a"
    assert service.inspect_calls[-1] == "candidate-research-thread-a"
    assert "Candidate B studies responsible AI assurance." not in repr(first_session)
