"""End-to-end routing checks for the explicit M13.7 MVP evidence standard."""

from typing import cast

from scholarpath.agents import StructuredEvidenceExtractionResult
from scholarpath.config import ApplicationSettings, Environment, LangSmithSettings, LogLevel
from scholarpath.domain import (
    EvidenceClaimType,
    VerificationEvidenceStandard,
    VerificationStatus,
)
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


def _identity_only_evidence_model() -> FakeEvidenceVerificationModel:
    outcomes = {
        source_url: StructuredEvidenceExtractionResult(
            claims=[
                claim for claim in response.claims if claim.claim_type is EvidenceClaimType.IDENTITY
            ]
        )
        for source_url, response in make_graph_evidence_outcomes().items()
    }
    return FakeEvidenceVerificationModel(outcomes)


def _run(
    standard: VerificationEvidenceStandard,
    *,
    approved_supervisor_ids: tuple[str, ...] | None = None,
    derive_policy_from_application_settings: bool = False,
) -> tuple[ScholarPathState | dict[str, object], FakeResearchFitModel]:
    config = (
        None
        if derive_policy_from_application_settings
        else GraphFixtureConfig(
            verification_policy=VerificationPolicy(
                verification_evidence_standard=standard,
            )
        )
    )
    fit_model = FakeResearchFitModel()
    responses = (
        (
            CandidateApproveResponse(
                action="approve",
                supervisor_ids=approved_supervisor_ids,
            ),
        )
        if approved_supervisor_ids is not None
        else ()
    )
    result = run_scholarpath_graph(
        config,
        thread_id=f"m13-7-{standard.value}-{approved_supervisor_ids is not None}",
        candidate_review_responses=responses,
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=_identity_only_evidence_model(),
        research_fit_model=fit_model,
        independent_review_model=FakeIndependentReviewModel(),
        candidate_preference_memory=FakeCandidatePreferenceMemory(),
        alternate_evidence_search=FakeSupervisorSearch(),
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            log_level=LogLevel.ERROR,
            verification_evidence_standard=standard,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
    )
    return result, fit_model


def test_strict_standard_stops_but_mvp_identity_standard_reaches_candidate_review() -> None:
    strict_result, strict_fit_model = _run(
        VerificationEvidenceStandard.STRICT,
    )
    strict_state = cast(ScholarPathState, strict_result)

    assert strict_state["review_status"] is ReviewStatus.EVIDENCE_INCOMPLETE
    assert not strict_state["verified_supervisors"]
    assert strict_fit_model.call_count == 0

    mvp_result, mvp_fit_model = _run(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )
    mvp_state = cast(ScholarPathState, mvp_result)

    assert candidate_review_payload_from_graph_output(mvp_result) is not None
    assert mvp_state["review_status"] is ReviewStatus.PROPOSED
    assert len(mvp_state["verified_supervisors"]) == 8
    assert len(mvp_state["research_fit_assessments"]) == 8
    assert not mvp_state["shortlisted_supervisors"]
    assert mvp_fit_model.call_count == 0
    assert all(
        supervisor.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS
        for supervisor in mvp_state["verified_supervisors"]
    )
    assert all(
        assessment.overall_score == 0 for assessment in mvp_state["research_fit_assessments"]
    )


def test_mvp_identity_standard_still_requires_explicit_approval_before_persistence() -> None:
    paused, _ = _run(VerificationEvidenceStandard.IDENTITY_ONLY_MVP)
    payload = candidate_review_payload_from_graph_output(paused)
    assert payload is not None
    approved_ids = tuple(item.supervisor_id for item in payload.proposed_supervisor_shortlist)

    result, fit_model = _run(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
        approved_supervisor_ids=approved_ids,
    )
    state = cast(ScholarPathState, result)

    assert state["review_status"] is ReviewStatus.COMPLETED
    assert len(state["shortlisted_supervisors"]) == 5
    assert state["supervisor_shortlist"] is not None
    assert fit_model.call_count == 0


def test_application_setting_configures_the_default_graph_verification_standard() -> None:
    result, _ = _run(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
        derive_policy_from_application_settings=True,
    )
    state = cast(ScholarPathState, result)

    assert candidate_review_payload_from_graph_output(result) is not None
    assert state["review_status"] is ReviewStatus.PROPOSED
    assert all(
        supervisor.verification_evidence_standard is VerificationEvidenceStandard.IDENTITY_ONLY_MVP
        for supervisor in state["verified_supervisors"]
    )
