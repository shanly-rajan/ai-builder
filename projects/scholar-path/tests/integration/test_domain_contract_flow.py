"""Offline integration test for the M1 domain-contract approval path."""

from scholarpath.domain import (
    CandidateReviewAction,
    CandidateReviewDecision,
    SupervisorLifecycleStatus,
    SupervisorShortlist,
    create_supervisor_shortlist,
)
from tests.fixtures import (
    FIXED_RETRIEVED_AT,
    make_candidate_profile,
    make_research_fit_assessments,
    make_verified_supervisors,
)


def test_fixture_cohort_can_cross_approval_gate_and_round_trip() -> None:
    candidate = make_candidate_profile()
    verified = make_verified_supervisors()
    assessments = make_research_fit_assessments()
    approved_ids = tuple(item.supervisor_id for item in assessments)
    decision = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=approved_ids,
        reason="The Candidate approved all five evidence-backed recommendations.",
    )

    shortlist = create_supervisor_shortlist(
        candidate.candidate_id,
        verified,
        decision,
        generated_at=FIXED_RETRIEVED_AT,
        briefing="Five approved recommendations with preserved verification evidence.",
    )
    restored = SupervisorShortlist.model_validate_json(shortlist.model_dump_json())

    assert restored == shortlist
    assert len(restored.shortlisted_supervisors) == 5
    assert all(
        supervisor.status is SupervisorLifecycleStatus.SHORTLISTED
        for supervisor in restored.shortlisted_supervisors
    )
