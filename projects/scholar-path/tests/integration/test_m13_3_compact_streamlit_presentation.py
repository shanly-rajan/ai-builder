"""Focused AppTest coverage for the compact research-degree presentation slice."""

from __future__ import annotations

import ast
from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scholarpath.ui.app as ui_app
import scholarpath.ui.dependencies as ui_dependencies
from scholarpath.config import ApplicationSettings, Environment
from scholarpath.graph import AlternateSourceRejectionCounts
from scholarpath.tools import SearchProvider
from scholarpath.ui import (
    AlternateSourceDiagnosticsView,
    DiscoveryAttemptView,
    DiscoveryDiagnosticsView,
    EvidenceClaimTypeCountsView,
    EvidenceExtractionFailureCountsView,
    EvidenceVerificationDiagnosticsView,
    MissingRequiredEvidenceCountsView,
    ScholarPathApplicationPort,
    UiDiscoveryRoute,
    UiRunSnapshot,
)
from tests.fakes.ui import FakeScholarPathApplication, make_ui_review_snapshot

APP_PATH = Path(__file__).resolve().parents[2] / "streamlit_app.py"
APP_SOURCE_PATH = Path(ui_app.__file__)
THREAD_ID = "candidate-research-m13-3-compact"
CANDIDATE_ID = "candidate-m13-3-compact"


@pytest.fixture(autouse=True)
def _clear_streamlit_resource_cache() -> Iterator[None]:
    """Keep each presentation scenario inside one cached-service boundary."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _configure_dependencies(
    monkeypatch: pytest.MonkeyPatch,
    service: FakeScholarPathApplication,
) -> None:
    settings = ApplicationSettings(environment=Environment.TEST)

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


def _new_app() -> AppTest:
    return AppTest.from_file(APP_PATH, default_timeout=10).run()


def _submit_profile(app_test: AppTest) -> None:
    app_test.text_area(key="profile_research_statement").input(
        "Evaluate governance controls for complex research systems."
    )
    app_test.text_area(key="profile_research_topics").input("research governance")
    app_test.button(key="candidate_profile_submit").click().run()


def _diagnostic_snapshot() -> UiRunSnapshot:
    discovery = DiscoveryDiagnosticsView(
        attempts=(
            DiscoveryAttemptView(
                provider=SearchProvider.YOU,
                attempt_number=1,
                raw_result_count=2,
                plausible_supervisor_count=2,
                route=UiDiscoveryRoute.PRIMARY,
            ),
        ),
        raw_result_count=2,
        plausible_supervisor_count=2,
        retained_prospective_supervisor_count=2,
        fallback_search_used=False,
        route=UiDiscoveryRoute.PRIMARY,
    )
    alternate = AlternateSourceDiagnosticsView(
        attempted_supervisor_count=1,
        result_count=0,
        eligible_result_count=0,
        selected_source_count=0,
        no_results_count=1,
        rejected_all_count=0,
        provider_error_count=0,
        not_configured_count=0,
        rejection_counts=AlternateSourceRejectionCounts(),
    )
    evidence = EvidenceVerificationDiagnosticsView(
        primary_retrieval_attempt_count=1,
        primary_retrieval_success_count=1,
        primary_retrieval_failure_count=0,
        alternate_retrieval_attempt_count=0,
        alternate_retrieval_success_count=0,
        alternate_retrieval_failure_count=0,
        extraction_failure_counts=EvidenceExtractionFailureCountsView(),
        verification_record_count=1,
        completed_verification_record_count=1,
        partial_verification_record_count=0,
        retained_claim_counts=EvidenceClaimTypeCountsView(
            identity=1,
            current_affiliation=1,
            research_interest=1,
        ),
        directly_grounded_claim_counts=EvidenceClaimTypeCountsView(
            identity=1,
            current_affiliation=1,
            research_interest=1,
        ),
        missing_required_evidence_counts=MissingRequiredEvidenceCountsView(),
    )
    return make_ui_review_snapshot().model_copy(
        update={
            "discovery_diagnostics": discovery,
            "alternate_source_diagnostics": alternate,
            "evidence_verification_diagnostics": evidence,
        }
    )


def test_academic_cap_hero_page_icon_and_research_degree_language(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_dependencies(monkeypatch, service)

    app_test = _new_app()

    rendered = "\n".join(
        (
            *(item.value for item in app_test.title),
            *(item.value for item in app_test.markdown),
            *(item.value for item in app_test.header),
            *(item.value for item in app_test.caption),
        )
    )
    assert not app_test.exception
    assert ui_app.PAGE_ICON == "🎓"
    assert [item.value for item in app_test.title] == ["🎓 ScholarPath"]
    assert ui_app.HERO_SUBTITLE in rendered
    assert "1. Your Research Degree Profile" in rendered
    assert "Describe your postgraduate research direction and practical preferences" in rendered
    assert "Your Doctoral Research Profile" not in rendered
    normalized_styles = ui_app.APP_STYLES.casefold()
    assert normalized_styles.strip().startswith("<style>")
    for unsafe_css_token in ("@import", "url(", "<script", "javascript:"):
        assert unsafe_css_token not in normalized_styles

    source_tree = ast.parse(APP_SOURCE_PATH.read_text(encoding="utf-8"))
    page_config_call = next(
        node
        for node in ast.walk(source_tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "set_page_config"
    )
    page_icon = next(
        keyword.value for keyword in page_config_call.keywords if keyword.arg == "page_icon"
    )
    assert isinstance(page_icon, ast.Name)
    assert page_icon.id == "PAGE_ICON"


def test_all_supervisor_outcomes_and_completed_progress_start_collapsed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = FakeScholarPathApplication()
    _configure_dependencies(monkeypatch, service)
    app_test = _new_app()

    _submit_profile(app_test)

    assert not app_test.exception
    progress = next(
        item for item in app_test.status if item.label == "Canonical LangGraph progress"
    )
    assert progress.state == "complete"
    assert progress.proto.expanded is False

    prospective_label = "Dr Amara Ndlovu — Southern Cape Institute of Technology"
    scored_label = f"{prospective_label} · Research Fit: 87/100"
    all_outcome_expanders = [item for item in app_test.expander if " — " in item.label]
    assert len(all_outcome_expanders) == 6
    assert all(item.proto.expanded is False for item in all_outcome_expanders)
    outcome_expanders = [
        item for item in app_test.expander if item.label in {prospective_label, scored_label}
    ]
    assert [item.label for item in outcome_expanders].count(prospective_label) == 1
    assert [item.label for item in outcome_expanders].count(scored_label) == 2
    assert all(item.proto.expanded is False for item in outcome_expanders)

    app_test.multiselect(key="approve_supervisor_ids").set_value(["supervisor-001"])
    app_test.button(key="approve_supervisors_submit").click().run()

    assert not app_test.exception
    assert len(service.resume_calls) == 1
    assert [item.value for item in app_test.header] == [
        "2. Supervisor Search Progress",
        "6. Your Supervisor Shortlist",
    ]
    final_outcome_expanders = [item for item in app_test.expander if " — " in item.label]
    assert len(final_outcome_expanders) == 1
    assert all(item.proto.expanded is False for item in final_outcome_expanders)
    final_scored_expanders = [item for item in app_test.expander if item.label == scored_label]
    assert len(final_scored_expanders) == 1
    assert all(item.proto.expanded is False for item in final_scored_expanders)


def test_outer_diagnostics_are_exact_collapsed_panels_and_do_not_render_secrets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret_sentinel = "sk-m13-3-private-sentinel"
    snapshot = _diagnostic_snapshot().model_copy(update={"checkpoint_token": secret_sentinel})
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    _configure_dependencies(monkeypatch, service)
    monkeypatch.setenv("OPENAI_API_KEY", secret_sentinel)
    app_test = AppTest.from_file(APP_PATH, default_timeout=10)
    app_test.secrets["OPENAI_API_KEY"] = secret_sentinel
    app_test.run()

    _submit_profile(app_test)

    diagnostics_labels = {
        "Discovery diagnostics",
        "Alternate-source diagnostics",
        "Evidence-verification diagnostics",
    }
    diagnostic_expanders = [item for item in app_test.expander if item.label in diagnostics_labels]
    assert not app_test.exception
    assert {item.label for item in diagnostic_expanders} == diagnostics_labels
    assert all(item.proto.expanded is False for item in diagnostic_expanders)
    assert secret_sentinel not in repr(app_test.main)
    assert secret_sentinel not in repr(app_test.session_state.filtered_state)
    assert secret_sentinel not in ui_app.APP_STYLES
