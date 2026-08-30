"""Streamlit presentation checks for the identity-only MVP evidence standard."""

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scholarpath.ui.app as ui_app
import scholarpath.ui.dependencies as ui_dependencies
from scholarpath.config import ApplicationSettings, Environment
from scholarpath.domain import VerificationEvidenceStandard, VerificationStatus
from scholarpath.ui import (
    EvidenceClaimTypeCountsView,
    EvidenceExtractionFailureCountsView,
    EvidenceVerificationDiagnosticsView,
    MissingRequiredEvidenceCountsView,
    ScholarPathApplicationPort,
)
from tests.fakes.ui import FakeScholarPathApplication, make_ui_review_snapshot

APP_PATH = Path(__file__).resolve().parents[2] / "streamlit_app.py"


@pytest.fixture(autouse=True)
def _clear_streamlit_resource_cache() -> Iterator[None]:
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def test_mvp_banner_and_evidence_limit_remain_visible_on_collapsed_results(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    base = make_ui_review_snapshot()
    limited = tuple(
        supervisor.model_copy(
            update={
                "verification_status": VerificationStatus.VERIFIED_WITH_CONCERNS,
                "verification_evidence_standard": (VerificationEvidenceStandard.IDENTITY_ONLY_MVP),
                "research_fit_score": 0,
                "research_fit_evidence_limited": True,
                "fit_explanation": (
                    "Research Fit is not established because research evidence is missing."
                ),
                "concerns": ("Current affiliation and research evidence remain deferred.",),
            }
        )
        for supervisor in base.review_supervisors
    )
    snapshot = base.model_copy(
        update={
            "verified_supervisors": limited,
            "review_supervisors": limited,
            "evidence_verification_diagnostics": EvidenceVerificationDiagnosticsView(
                primary_retrieval_attempt_count=3,
                primary_retrieval_success_count=3,
                primary_retrieval_failure_count=0,
                alternate_retrieval_attempt_count=0,
                alternate_retrieval_success_count=0,
                alternate_retrieval_failure_count=0,
                extraction_failure_counts=EvidenceExtractionFailureCountsView(),
                verification_evidence_standard=(VerificationEvidenceStandard.IDENTITY_ONLY_MVP),
                verification_record_count=3,
                completed_verification_record_count=3,
                partial_verification_record_count=0,
                retained_claim_counts=EvidenceClaimTypeCountsView(identity=3),
                directly_grounded_claim_counts=EvidenceClaimTypeCountsView(identity=3),
                missing_required_evidence_counts=MissingRequiredEvidenceCountsView(),
                deferred_evidence_gap_counts=MissingRequiredEvidenceCountsView(
                    current_affiliation=3,
                    research_interest_or_publication=3,
                ),
            ),
        }
    )
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    settings = ApplicationSettings(
        environment=Environment.TEST,
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )

    def create_service(
        resolved_settings: ApplicationSettings | None = None,
    ) -> ScholarPathApplicationPort:
        assert resolved_settings is settings
        return service

    monkeypatch.setattr(ui_dependencies, "configured_application_settings", lambda: settings)
    monkeypatch.setattr(ui_dependencies, "create_application_service", create_service)
    monkeypatch.setattr(ui_dependencies, "new_thread_id", lambda: "m13-7-ui-thread")
    monkeypatch.setattr(ui_dependencies, "new_candidate_id", lambda: "m13-7-candidate")

    app_test = AppTest.from_file(APP_PATH, default_timeout=10).run()
    assert ui_app.MVP_IDENTITY_ONLY_BANNER in [item.value for item in app_test.warning]

    app_test.text_area(key="profile_research_statement").input(
        "Evaluate governance controls for complex research systems."
    )
    app_test.text_area(key="profile_research_topics").input("research governance")
    app_test.button(key="candidate_profile_submit").click().run()

    assert not app_test.exception
    assert ui_app.MVP_IDENTITY_ONLY_BANNER in [item.value for item in app_test.warning]
    assert "at least 2 Verified Supervisors" in ui_app.MVP_IDENTITY_ONLY_BANNER
    assert "may propose up to 5" in ui_app.MVP_IDENTITY_ONLY_BANNER
    rendered_warnings = "\n".join(item.value for item in app_test.warning)
    assert "graph may continue with at least 2 Verified Supervisors" in rendered_warnings
    assert "proposed shortlist remains capped at 5" in rendered_warnings
    limited_expanders = [
        item for item in app_test.expander if "Research Fit: not established" in item.label
    ]
    assert len(limited_expanders) == 4
    assert all(item.proto.expanded is False for item in limited_expanders)
    rendered = "\n".join(item.value for item in app_test.markdown)
    assert "Discovered institution (not verified)" in rendered
    assert "Verification standard: MVP — identity only" in rendered
    assert "No unsupported points were awarded" in rendered_warnings
