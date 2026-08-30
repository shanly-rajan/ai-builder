"""Focused graph checks for the M13.8 MVP verified-cohort threshold."""

from typing import cast

from scholarpath.agents import StructuredEvidenceExtractionResult
from scholarpath.config import ApplicationSettings, Environment, LangSmithSettings, LogLevel
from scholarpath.domain import EvidenceClaimType, VerificationEvidenceStandard
from scholarpath.graph import (
    CandidateApproveResponse,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    VerificationPolicy,
    candidate_review_payload_from_graph_output,
    run_scholarpath_graph,
)
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_graph_evidence_outcomes,
)


def _evidence_model_for_verified_cohort(
    verified_count: int,
    *,
    standard: VerificationEvidenceStandard,
) -> FakeEvidenceVerificationModel:
    """Return complete or identity-only evidence for exactly the requested cohort."""
    outcomes: dict[str, StructuredEvidenceExtractionResult] = {}
    for index, (source_url, complete) in enumerate(make_graph_evidence_outcomes().items()):
        if index >= verified_count:
            outcomes[source_url] = StructuredEvidenceExtractionResult()
            continue
        claims = (
            [claim for claim in complete.claims if claim.claim_type is EvidenceClaimType.IDENTITY]
            if standard is VerificationEvidenceStandard.IDENTITY_ONLY_MVP
            else complete.claims
        )
        outcomes[source_url] = StructuredEvidenceExtractionResult(claims=claims)
    return FakeEvidenceVerificationModel(outcomes)


def _run_with_verified_cohort(
    verified_count: int,
    *,
    standard: VerificationEvidenceStandard,
    approved_supervisor_ids: tuple[str, ...] | None = None,
) -> tuple[ScholarPathState, FakeResearchFitModel, FakeSupervisorSearch]:
    fit_model = FakeResearchFitModel()
    alternate_search = FakeSupervisorSearch()
    result = run_scholarpath_graph(
        GraphFixtureConfig(
            verification_policy=VerificationPolicy(
                verification_evidence_standard=standard,
            )
        ),
        thread_id=f"m13-8-{standard.value}-{verified_count}",
        candidate_review_responses=(
            (
                CandidateApproveResponse(
                    action="approve",
                    supervisor_ids=approved_supervisor_ids,
                ),
            )
            if approved_supervisor_ids is not None
            else ()
        ),
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=_evidence_model_for_verified_cohort(
            verified_count,
            standard=standard,
        ),
        research_fit_model=fit_model,
        independent_review_model=FakeIndependentReviewModel(),
        candidate_preference_memory=FakeCandidatePreferenceMemory(),
        alternate_evidence_search=alternate_search,
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            log_level=LogLevel.ERROR,
            verification_evidence_standard=standard,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
    )
    return cast(ScholarPathState, result), fit_model, alternate_search


def test_two_identity_only_mvp_verified_supervisors_reach_candidate_review_without_retry() -> None:
    state, fit_model, alternate_search = _run_with_verified_cohort(
        2,
        standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )

    assert state["review_status"] is ReviewStatus.PROPOSED
    assert len(state["verified_supervisors"]) == 2
    assert state["proposed_shortlist"] is not None
    assert len(state["proposed_shortlist"].recommendations) == 2
    assert candidate_review_payload_from_graph_output(state) is not None
    assert state["retry_counts"]["evidence"] == 0
    assert "retry_alternate_evidence_source" not in state["execution_log"]
    assert alternate_search.calls == []
    assert fit_model.call_count == 0
    assert state["shortlisted_supervisors"] == []


def test_one_identity_only_mvp_verified_supervisor_retries_once_then_stops() -> None:
    state, fit_model, alternate_search = _run_with_verified_cohort(
        1,
        standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )

    assert state["review_status"] is ReviewStatus.EVIDENCE_INCOMPLETE
    assert len(state["verified_supervisors"]) == 1
    assert candidate_review_payload_from_graph_output(state) is None
    assert state["retry_counts"]["evidence"] == 1
    assert state["execution_log"].count("retry_alternate_evidence_source") == 1
    assert len(alternate_search.calls) == (
        len(state["prospective_supervisors"]) - len(state["verified_supervisors"])
    )
    assert fit_model.call_count == 0
    assert state["shortlisted_supervisors"] == []


def test_two_identity_only_mvp_supervisors_can_complete_after_explicit_approval() -> None:
    paused, _, _ = _run_with_verified_cohort(
        2,
        standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )
    payload = candidate_review_payload_from_graph_output(paused)
    assert payload is not None
    approved_ids = tuple(
        supervisor.supervisor_id for supervisor in payload.proposed_supervisor_shortlist
    )

    completed, fit_model, alternate_search = _run_with_verified_cohort(
        2,
        standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
        approved_supervisor_ids=approved_ids,
    )

    assert completed["review_status"] is ReviewStatus.COMPLETED
    assert len(completed["shortlisted_supervisors"]) == 2
    assert completed["supervisor_shortlist"] is not None
    assert len(completed["supervisor_shortlist"].shortlisted_supervisors) == 2
    assert completed["shortlist_briefing"] is not None
    assert completed["retry_counts"]["evidence"] == 0
    assert alternate_search.calls == []
    assert fit_model.call_count == 0


def test_strict_graph_stops_with_four_but_continues_with_five_after_bounded_retry() -> None:
    below_minimum, below_fit_model, below_alternate_search = _run_with_verified_cohort(
        4,
        standard=VerificationEvidenceStandard.STRICT,
    )
    at_minimum, _, at_minimum_alternate_search = _run_with_verified_cohort(
        5,
        standard=VerificationEvidenceStandard.STRICT,
    )

    assert below_minimum["review_status"] is ReviewStatus.EVIDENCE_INCOMPLETE
    assert below_minimum["retry_counts"]["evidence"] == 1
    assert len(below_alternate_search.calls) == 4
    assert below_fit_model.call_count == 0

    assert at_minimum["review_status"] is ReviewStatus.PROPOSED
    assert len(at_minimum["verified_supervisors"]) == 5
    assert candidate_review_payload_from_graph_output(at_minimum) is not None
    assert at_minimum["retry_counts"]["evidence"] == 1
    assert len(at_minimum_alternate_search.calls) == 3
