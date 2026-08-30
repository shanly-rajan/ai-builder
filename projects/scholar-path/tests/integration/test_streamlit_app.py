"""Headless integration coverage for the M11 ScholarPath Streamlit application."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scholarpath.ui.app as ui_app
import scholarpath.ui.dependencies as ui_dependencies
from scholarpath.config import ApplicationSettings, Environment
from scholarpath.domain import SearchResultRejectionCounts
from scholarpath.graph import (
    AlternateSourceRejectionCounts,
    CandidateApproveResponse,
    CandidateRejectResponse,
    CandidateRequestMoreResponse,
)
from scholarpath.tools import SearchProvider
from scholarpath.ui import (
    AlternateSourceDiagnosticsView,
    DiscoveryAttemptView,
    DiscoveryDiagnosticsView,
    GraphProgressEvent,
    RecoverableUiError,
    ScholarPathApplicationError,
    ScholarPathApplicationPort,
    UiDiscoveryRoute,
    UiRunSnapshot,
    UiStage,
)
from tests.fakes.ui import FakeScholarPathApplication

APP_PATH = Path(__file__).resolve().parents[2] / "streamlit_app.py"
THREAD_ID = "candidate-research-ui-thread-001"
CANDIDATE_ID = "candidate-ui-001"
RESEARCH_STATEMENT = "How can enterprise architecture support responsible digital transformation?"
RESEARCH_TOPICS = "enterprise architecture, responsible AI"
EXPECTED_STAGE_LABELS = (
    "1. Your Research Degree Profile",
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

    settings = ApplicationSettings(environment=Environment.TEST)

    def create_application_service(
        resolved_settings: ApplicationSettings | None = None,
    ) -> ScholarPathApplicationPort:
        assert resolved_settings is settings
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
    monkeypatch.setattr(
        ui_dependencies,
        "configured_application_settings",
        lambda: settings,
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
    assert app_test.title[0].value == "🎓 ScholarPath"
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


def test_zero_retained_results_show_accurate_privacy_safe_discovery_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = DiscoveryDiagnosticsView(
        attempts=(
            DiscoveryAttemptView(
                provider=SearchProvider.YOU,
                attempt_number=1,
                raw_result_count=0,
                plausible_supervisor_count=0,
                route=UiDiscoveryRoute.PRIMARY,
            ),
            DiscoveryAttemptView(
                provider=SearchProvider.TAVILY,
                attempt_number=1,
                raw_result_count=40,
                plausible_supervisor_count=0,
                route=UiDiscoveryRoute.FALLBACK,
            ),
        ),
        raw_result_count=40,
        plausible_supervisor_count=0,
        retained_prospective_supervisor_count=0,
        fallback_search_used=True,
        route=UiDiscoveryRoute.STOPPED_RECOVERABLY,
    )
    snapshot = UiRunSnapshot(
        stage=UiStage.STOPPED,
        checkpoint_token="ui-stopped-checkpoint",
        progress_events=(
            GraphProgressEvent(sequence=1, node_name="discover_prospective_supervisors"),
            GraphProgressEvent(sequence=2, node_name="fallback_supervisor_search"),
            GraphProgressEvent(sequence=3, node_name="enough_supervisors_found"),
        ),
        discovery_diagnostics=diagnostics,
        errors=(
            RecoverableUiError(
                code="supervisor_discovery_incomplete",
                message="Legacy partial-results wording must not be rendered.",
                recoverable=True,
            ),
        ),
    )
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_candidate_profile(app_test)

    rendered = "\n".join(
        (
            *(item.value for item in app_test.markdown),
            *(item.value for item in app_test.info),
            *(item.value for item in app_test.warning),
            *(item.value for item in app_test.caption),
        )
    )
    assert not app_test.exception
    assert ("Raw provider results", "40") in [
        (metric.label, metric.value) for metric in app_test.metric
    ]
    assert ("Plausible profiles before deduplication", "0") in [
        (metric.label, metric.value) for metric in app_test.metric
    ]
    assert ("Retained Prospective Supervisors", "0") in [
        (metric.label, metric.value) for metric in app_test.metric
    ]
    assert "Fallback search used: Yes" in rendered
    assert "Discovery route: Stopped recoverably" in rendered
    assert "Why raw results were excluded" in rendered
    assert "Rejection breakdown unavailable" in rendered
    assert "earlier persisted run without recorded category counts" in rendered
    assert "does not infer zeros" in rendered
    assert "Search providers returned 40 raw results" in rendered
    assert "none passed the plausible person-and-institution checks" in rendered
    assert "partial results" not in rendered.casefold()
    assert "Legacy partial-results wording" not in rendered
    assert "private query" not in rendered


def test_typed_discovery_rejection_breakdown_is_rendered_without_sensitive_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rejection_counts = SearchResultRejectionCounts(
        person_not_established=2,
        academic_context_not_established=1,
        identity_conflict=1,
        institution_not_established=2,
        incomplete_institution=1,
    )
    diagnostics = DiscoveryDiagnosticsView(
        attempts=(
            DiscoveryAttemptView(
                provider=SearchProvider.YOU,
                attempt_number=1,
                raw_result_count=9,
                plausible_supervisor_count=2,
                rejection_counts=rejection_counts,
                route=UiDiscoveryRoute.PRIMARY,
            ),
        ),
        raw_result_count=9,
        plausible_supervisor_count=2,
        retained_prospective_supervisor_count=2,
        rejection_counts=rejection_counts,
        fallback_search_used=False,
        route=UiDiscoveryRoute.STOPPED_RECOVERABLY,
    )
    snapshot = UiRunSnapshot(
        stage=UiStage.STOPPED,
        checkpoint_token="ui-rejection-breakdown-checkpoint",
        progress_events=(
            GraphProgressEvent(sequence=1, node_name="discover_prospective_supervisors"),
        ),
        discovery_diagnostics=diagnostics,
        errors=(
            RecoverableUiError(
                code="supervisor_discovery_incomplete",
                message="The search stopped safely.",
                recoverable=True,
            ),
        ),
    )
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_candidate_profile(app_test)

    rendered = "\n".join(
        (
            *(item.value for item in app_test.markdown),
            *(item.value for item in app_test.info),
            *(item.value for item in app_test.caption),
        )
    )
    assert not app_test.exception
    assert "Why raw results were excluded" in rendered
    assert "Deterministic exclusion categories account for 7 raw provider results" in rendered
    assert "Person not established: 2" in rendered
    assert "Academic context not established: 1" in rendered
    assert "Identity conflict: 1" in rendered
    assert "Institution not established: 2" in rendered
    assert "Incomplete institution: 1" in rendered
    assert "Rejection breakdown unavailable" not in rendered
    assert "private query" not in rendered
    assert "Candidate research statement" not in rendered


def test_alternate_source_rejection_breakdown_is_rendered_without_sensitive_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    diagnostics = AlternateSourceDiagnosticsView(
        attempted_supervisor_count=11,
        result_count=47,
        eligible_result_count=1,
        selected_source_count=1,
        no_results_count=2,
        rejected_all_count=8,
        provider_error_count=0,
        not_configured_count=0,
        rejection_counts=AlternateSourceRejectionCounts(
            query_mismatch=1,
            same_url=3,
            https_or_host_invalid=2,
            exact_person_text_missing=12,
            exact_institution_text_missing=14,
            singular_route_mismatch=8,
            academic_host_mismatch=5,
            source_kind_unsupported=1,
        ),
    )
    snapshot = UiRunSnapshot(
        stage=UiStage.STOPPED,
        checkpoint_token="ui-alternate-source-diagnostics-checkpoint",
        alternate_source_diagnostics=diagnostics,
    )
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_candidate_profile(app_test)

    rendered = "\n".join(
        (
            *(item.value for item in app_test.subheader),
            *(item.value for item in app_test.markdown),
            *(item.value for item in app_test.caption),
            *(item.value for item in app_test.info),
        )
    )
    metrics = [(metric.label, metric.value) for metric in app_test.metric]
    assert not app_test.exception
    assert ("Prospective Supervisors searched", "11") in metrics
    assert ("Alternate search results", "47") in metrics
    assert ("Eligible official profiles", "1") in metrics
    assert ("Selected official sources", "1") in metrics
    assert "Privacy-safe alternate-source diagnostics" in rendered
    assert "Why alternate results were excluded" in rendered
    assert "First-failed selector gates account for 46 alternate search results" in rendered
    assert "Exact person text missing: 12" in rendered
    assert "Exact institution text missing: 14" in rendered
    assert "Singular person-profile route missing: 8" in rendered
    assert "Academic institution host mismatch: 5" in rendered
    assert "Search queries, result text, URLs, Supervisor identities" in rendered
    for private_value in (
        "private query",
        "https://private.example/profile",
        "returned page content",
        RESEARCH_STATEMENT,
        "secret-token",
    ):
        assert private_value not in rendered


def test_repeated_recoverable_errors_render_once_with_an_occurrence_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    repeated_message = "No alternate official Supervisor source could be selected."
    single_message = "A Supervisor source page could not be extracted."
    snapshot = UiRunSnapshot(
        stage=UiStage.STOPPED,
        checkpoint_token="ui-grouped-errors-checkpoint",
        errors=(
            RecoverableUiError(
                code="alternate_source_unavailable",
                message=repeated_message,
                recoverable=True,
                occurrence_count=5,
            ),
            RecoverableUiError(
                code="page_extraction_failed",
                message=single_message,
                recoverable=True,
            ),
        ),
    )
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_candidate_profile(app_test)

    warnings = [item.value for item in app_test.warning]
    rendered = "\n".join(warnings)
    assert not app_test.exception
    assert sum(repeated_message in warning for warning in warnings) == 1
    assert rendered.count(repeated_message) == 1
    assert "recorded 5 times in the current run" in rendered
    assert sum(single_message in warning for warning in warnings) == 1
    assert "recorded 1 time" not in rendered


def test_invalid_independent_review_revision_does_not_suggest_repeating_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    message = (
        "Independent Research Fit review completed, but its proposed evidence revision was not "
        "safely applicable; the original assessment was preserved with reduced confidence."
    )
    snapshot = UiRunSnapshot(
        stage=UiStage.STOPPED,
        checkpoint_token="ui-independent-review-reference-checkpoint",
        errors=(
            RecoverableUiError(
                code="independent_review_invalid_evidence_reference",
                message=message,
                recoverable=True,
            ),
        ),
    )
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_candidate_profile(app_test)

    warnings = [item.value for item in app_test.warning]
    assert not app_test.exception
    review_warning = next(item for item in warnings if message in item)
    assert "workflow can continue with the preserved assessment" in review_warning
    assert "revise the search" not in review_warning


def test_verified_supervisor_evidence_and_review_fields_are_rendered(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    rendered_markdown = "\n".join(item.value for item in app_test.markdown)
    rendered_expanders = [item.label for item in app_test.expander]
    rendered_metrics = [(item.label, item.value) for item in app_test.metric]

    assert not app_test.exception
    assert EXPECTED_STAGE_LABELS[3] in [item.value for item in app_test.header]
    assert any(
        label.startswith("Dr Amara Ndlovu — Southern Cape Institute of Technology")
        for label in rendered_expanders
    )
    assert any(
        label.startswith("Professor Elias Hart — Northbridge University")
        for label in rendered_expanders
    )
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
    rendered_headers = [item.value for item in app_test.header]
    assert rendered_headers == [EXPECTED_STAGE_LABELS[1], EXPECTED_STAGE_LABELS[5]]
    assert [item.value for item in app_test.success] == [
        "These Verified Supervisors were explicitly approved and shortlisted."
    ]
    assert any(
        item.label == "Professor Elias Hart — Northbridge University · Research Fit: 82/100"
        for item in app_test.expander
    )
    assert app_test.session_state["thread_id"] == THREAD_ID


def test_rejection_requires_a_reason_then_resumes_the_same_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    app_test.multiselect(key="approve_supervisor_ids").set_value(["supervisor-002"])
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
    approval_options = app_test.multiselect(key="approve_supervisor_ids")
    assert approval_options.options == ["Dr Amara Ndlovu — Southern Cape Institute of Technology"]
    assert approval_options.value == []
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


def test_stale_review_displays_the_sanitized_service_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    safe_message = "This Candidate review is no longer current. Reload the saved thread."
    service = FakeScholarPathApplication(
        resume_error=ScholarPathApplicationError("stale_candidate_review", safe_message)
    )
    _configure_ui_dependencies(monkeypatch, service)
    app_test = _new_app()
    _submit_candidate_profile(app_test)

    app_test.multiselect(key="approve_supervisor_ids").set_value(["supervisor-001"])
    app_test.button(key="approve_supervisors_submit").click().run()

    assert not app_test.exception
    assert [item.value for item in app_test.error] == [safe_message]
    assert ui_app.RECOVERABLE_SERVICE_MESSAGE not in repr(app_test.main)
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
