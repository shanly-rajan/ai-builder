"""Focused AppTest coverage for M13.1 evidence-verification diagnostics."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import scholarpath.ui.dependencies as ui_dependencies
from scholarpath.ui import (
    EvidenceClaimTypeCountsView,
    EvidenceExtractionFailureCountsView,
    EvidenceVerificationDiagnosticsView,
    MissingRequiredEvidenceCountsView,
    ScholarPathApplicationPort,
    UiRunSnapshot,
    UiStage,
)
from tests.fakes.ui import FakeScholarPathApplication
from tests.fixtures import make_candidate_profile

APP_PATH = Path(__file__).resolve().parents[2] / "streamlit_app.py"
THREAD_ID = "evidence-diagnostics-thread-001"
NAME_SENTINEL = "Dr Private Name Sentinel"
URL_SENTINEL = "https://private.example/supervisor-profile"
EXCERPT_SENTINEL = "Private source excerpt that must not render"
QUERY_SENTINEL = '"private research query" official profile'
CANDIDATE_CONTENT_SENTINEL = "Private Candidate research statement that must not render"
CREDENTIAL_SENTINEL = "sk-private-credential-that-must-not-render"


@pytest.fixture(autouse=True)
def _clear_streamlit_resource_cache() -> Iterator[None]:
    """Keep the cached fake application isolated to each focused AppTest."""
    st.cache_resource.clear()
    yield
    st.cache_resource.clear()


def _diagnostics() -> EvidenceVerificationDiagnosticsView:
    return EvidenceVerificationDiagnosticsView(
        primary_retrieval_attempt_count=2,
        primary_retrieval_success_count=1,
        primary_retrieval_failure_count=1,
        alternate_retrieval_attempt_count=2,
        alternate_retrieval_success_count=1,
        alternate_retrieval_failure_count=1,
        extraction_failure_counts=EvidenceExtractionFailureCountsView(
            timeout=1,
            response_contract=1,
        ),
        verification_record_count=2,
        completed_verification_record_count=0,
        partial_verification_record_count=2,
        retained_claim_counts=EvidenceClaimTypeCountsView(
            identity=2,
            current_affiliation=2,
            research_interest=1,
            methodology=2,
            publication=1,
            project=2,
            availability=1,
        ),
        directly_grounded_claim_counts=EvidenceClaimTypeCountsView(
            identity=1,
            current_affiliation=1,
            research_interest=1,
            methodology=2,
            publication=0,
            project=2,
            availability=1,
        ),
        missing_required_evidence_counts=MissingRequiredEvidenceCountsView(
            identity=1,
            current_affiliation=1,
            research_interest_or_publication=1,
        ),
    )


def _run_existing_thread(
    monkeypatch: pytest.MonkeyPatch,
    snapshot: UiRunSnapshot,
) -> tuple[AppTest, FakeScholarPathApplication]:
    service = FakeScholarPathApplication(start_snapshot=snapshot)
    private_profile = make_candidate_profile(
        candidate_id="private-candidate-runtime-id",
        proposed_research_statement=CANDIDATE_CONTENT_SENTINEL,
        research_topics=(
            NAME_SENTINEL,
            URL_SENTINEL,
            EXCERPT_SENTINEL,
            QUERY_SENTINEL,
        ),
    )
    service.start(private_profile, THREAD_ID)

    def create_application_service() -> ScholarPathApplicationPort:
        return service

    monkeypatch.setattr(
        ui_dependencies,
        "create_application_service",
        create_application_service,
    )
    st.cache_resource.clear()
    app_test = AppTest.from_file(APP_PATH, default_timeout=10)
    app_test.session_state["thread_id"] = THREAD_ID
    app_test.secrets["OPENAI_API_KEY"] = CREDENTIAL_SENTINEL
    app_test.run()
    return app_test, service


def test_current_round_evidence_diagnostics_render_complete_aggregate_taxonomy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_checkpoint = " | ".join(
        (
            NAME_SENTINEL,
            URL_SENTINEL,
            EXCERPT_SENTINEL,
            QUERY_SENTINEL,
            CANDIDATE_CONTENT_SENTINEL,
            CREDENTIAL_SENTINEL,
        )
    )
    snapshot = UiRunSnapshot(
        stage=UiStage.STOPPED,
        checkpoint_token=private_checkpoint,
        evidence_verification_diagnostics=_diagnostics(),
    )

    app_test, service = _run_existing_thread(monkeypatch, snapshot)

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
    assert "Privacy-safe evidence-verification diagnostics" in rendered
    assert "Retrieval success is not verification" in rendered
    assert (
        "Primary pages retrieved (retrieval success, not verification)",
        "1",
    ) in metrics
    assert (
        "Alternate pages retrieved (retrieval success, not verification)",
        "1",
    ) in metrics
    assert ("Primary retrieval attempts", "2") in metrics
    assert ("Primary retrieval failures", "1") in metrics
    assert ("Alternate retrieval attempts", "2") in metrics
    assert ("Alternate retrieval failures", "1") in metrics
    assert ("Verification records", "2") in metrics
    assert ("Completed verification records", "0") in metrics
    assert ("Partially verified records", "2") in metrics

    for expected_failure_count in (
        "Timeout: 1",
        "Transport: 0",
        "Authentication: 0",
        "Rate limit: 0",
        "Quota: 0",
        "Invalid request: 0",
        "Provider: 0",
        "Response contract: 1",
        "Extraction failed: 0",
    ):
        assert expected_failure_count in rendered

    for expected_claim_count in (
        "Identity: 2 retained; 1 directly grounded.",
        "Current affiliation: 2 retained; 1 directly grounded.",
        "Research interest: 1 retained; 1 directly grounded.",
        "Methodology: 2 retained; 2 directly grounded.",
        "Publication: 1 retained; 0 directly grounded.",
        "Project: 2 retained; 2 directly grounded.",
        "Availability: 1 retained; 1 directly grounded.",
    ):
        assert expected_claim_count in rendered

    assert "Missing required evidence gates" in rendered
    assert "Identity: 1" in rendered
    assert "Current affiliation: 1" in rendered
    assert "Research interest or publication: 1" in rendered
    assert "one record may be missing more than one required gate" in rendered

    rendered_main = repr(app_test.main)
    for private_value in (
        NAME_SENTINEL,
        URL_SENTINEL,
        EXCERPT_SENTINEL,
        QUERY_SENTINEL,
        CANDIDATE_CONTENT_SENTINEL,
        CREDENTIAL_SENTINEL,
    ):
        assert private_value not in rendered_main

    assert service.inspect_calls == [THREAD_ID]
    assert len(service.start_calls) == 1
    assert service.resume_calls == []
    assert "candidate_profile_submit" not in {button.key for button in app_test.button}


def test_legacy_snapshot_without_evidence_diagnostics_keeps_the_panel_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = UiRunSnapshot(
        stage=UiStage.STOPPED,
        checkpoint_token="legacy-evidence-diagnostics-checkpoint",
    )

    app_test, service = _run_existing_thread(monkeypatch, snapshot)

    assert not app_test.exception
    assert "Privacy-safe evidence-verification diagnostics" not in {
        item.value for item in app_test.subheader
    }
    assert not any(
        "retrieval success, not verification" in metric.label for metric in app_test.metric
    )
    assert service.inspect_calls == [THREAD_ID]
    assert len(service.start_calls) == 1
    assert service.resume_calls == []
