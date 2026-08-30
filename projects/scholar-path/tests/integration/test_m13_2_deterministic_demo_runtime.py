"""Offline end-to-end proof for the guarded M13.2 demonstration composition."""

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    RuntimeProfile,
)
from scholarpath.domain import CandidateProfile
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRejectionReason,
    CandidateRejectResponse,
)
from scholarpath.ui import UiStage, create_deterministic_demo_application_service


def _synthetic_profile() -> CandidateProfile:
    return CandidateProfile(
        candidate_id="synthetic-demo-candidate-001",
        proposed_research_statement=(
            "Evaluate applied governance controls for traceable enterprise AI systems."
        ),
        research_topics=("enterprise architecture", "responsible AI governance"),
        preferred_regions=("United Kingdom", "Netherlands"),
        preferred_study_modes=("part-time", "online"),
        preferred_research_orientation="applied",
        methodological_interests=("design science", "case study evaluation"),
        exclusions=("foundational model pre-training",),
    )


def _demo_settings() -> ApplicationSettings:
    return ApplicationSettings(
        environment=Environment.TEST,
        runtime_profile=RuntimeProfile.DETERMINISTIC_DEMO,
        discovery_failure_mode=DiscoveryFailureMode.YOU_RETRYABLE_ERROR,
    )


def test_demo_runtime_falls_back_verifies_learns_and_requires_approval() -> None:
    """Exercise the real graph from intake through a Candidate-approved shortlist."""
    service = create_deterministic_demo_application_service(_demo_settings())
    thread_id = "m13-2-synthetic-demo-thread"

    first_review = service.start(_synthetic_profile(), thread_id)

    assert first_review.stage is UiStage.REVIEW_SUPERVISORS
    assert len(first_review.verified_supervisors) >= 5
    assert len(first_review.review_supervisors) == 5
    assert first_review.shortlisted_supervisors == ()
    assert first_review.shortlist_briefing is None
    assert first_review.discovery_diagnostics is not None
    assert first_review.discovery_diagnostics.fallback_search_used is True
    assert all(
        supervisor.verification_status.value == "verified"
        for supervisor in first_review.verified_supervisors
    )
    assert all(
        source.directly_supported
        for supervisor in first_review.verified_supervisors
        for source in supervisor.evidence_sources
    )

    rejected_id = first_review.review_supervisors[-1].supervisor_id
    second_review = service.resume(
        thread_id,
        first_review.checkpoint_token,
        CandidateRejectResponse(
            action="reject",
            rejections=(
                CandidateRejectionReason(
                    supervisor_id=rejected_id,
                    reason=("The demonstrated research direction is less applied than preferred."),
                ),
            ),
        ),
    )

    assert second_review.stage is UiStage.REVIEW_SUPERVISORS
    assert second_review.checkpoint_token != first_review.checkpoint_token
    assert rejected_id not in {
        supervisor.supervisor_id for supervisor in second_review.review_supervisors
    }
    assert second_review.shortlisted_supervisors == ()
    assert "learn_candidate_preferences" in {
        event.node_name for event in second_review.progress_events
    }
    assert "plan_supervisor_searches" in {
        event.node_name for event in second_review.progress_events
    }

    approved_ids = tuple(
        supervisor.supervisor_id for supervisor in second_review.review_supervisors
    )
    completed = service.resume(
        thread_id,
        second_review.checkpoint_token,
        CandidateApproveResponse(action="approve", supervisor_ids=approved_ids),
    )

    assert completed.stage is UiStage.SUPERVISOR_SHORTLIST
    assert (
        tuple(supervisor.supervisor_id for supervisor in completed.shortlisted_supervisors)
        == approved_ids
    )
    assert completed.shortlist_briefing is not None
    assert "Candidate-approved" in completed.shortlist_briefing


def test_demo_runtime_checkpoints_are_isolated_and_in_memory() -> None:
    """A separately constructed demo service cannot inspect another service's thread."""
    settings = _demo_settings()
    first_service = create_deterministic_demo_application_service(settings)
    second_service = create_deterministic_demo_application_service(settings)
    thread_id = "m13-2-isolated-demo-thread"

    first_service.start(_synthetic_profile(), thread_id)

    assert first_service.inspect(thread_id) is not None
    assert second_service.inspect(thread_id) is None
