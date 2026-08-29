"""Graph scenarios for M8 independent Research Fit review and reconciliation."""

from scholarpath.agents.independent_review import (
    IndependentReviewModelInvocationError,
    IndependentReviewModelOutputError,
    IndependentReviewPolicy,
)
from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
    NebiusReviewSettings,
)
from scholarpath.domain import IndependentReviewStatus
from scholarpath.graph import (
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    run_scholarpath_graph,
)
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_revised_review,
)


def _run(
    review_model: FakeIndependentReviewModel | None,
    *,
    config: GraphFixtureConfig | None = None,
    nebius_review_settings: NebiusReviewSettings | None = None,
) -> ScholarPathState:
    return run_scholarpath_graph(
        config,
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=review_model,
        alternate_evidence_search=FakeSupervisorSearch(),
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.OFF,
        ),
        nebius_review_settings=nebius_review_settings,
        langsmith_settings=LangSmithSettings(tracing=False),
    )


def test_graph_uses_fake_reviewer_for_every_assessment() -> None:
    model = FakeIndependentReviewModel()

    final_state = _run(model)

    assert model.call_count == len(final_state["research_fit_assessments"])
    assert len(final_state["research_fit_review_records"]) == model.call_count
    assert all(
        record.review_status is IndependentReviewStatus.ACCEPTED
        for record in final_state["research_fit_review_records"]
    )
    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_valid_revision_updates_preliminary_shortlist_order_deterministically() -> None:
    baseline_model = FakeIndependentReviewModel()
    baseline = _run(baseline_model)
    baseline_proposal = baseline["proposed_shortlist"]
    assert baseline_proposal is not None
    target = baseline_proposal.recommendations[-1]
    target_input = next(
        item
        for item in baseline_model.inputs
        if item.initial_assessment.supervisor_id == target.supervisor.supervisor_id
    )
    revised = make_revised_review(
        target_input,
        recommended_score=95,
        critique="The supplied evidence supports a higher score after independent review.",
    )

    final_state = _run(FakeIndependentReviewModel({target.supervisor.supervisor_id: (revised,)}))
    proposal = final_state["proposed_shortlist"]

    assert proposal is not None
    assert proposal.recommendations[0].supervisor.supervisor_id == target.supervisor.supervisor_id
    assert [item.effective_score for item in proposal.recommendations] == [95, 87, 82, 75, 72]
    assert proposal.recommendations[0].assessment.overall_score == 68
    assert proposal.recommendations[0].independent_review is not None
    assert (
        tuple(supervisor.supervisor_id for supervisor in final_state["shortlisted_supervisors"])
        == final_state["candidate_feedback"][-1].supervisor_ids
    )


def test_unsupported_claim_is_removed_from_candidate_facing_strengths() -> None:
    baseline_model = FakeIndependentReviewModel()
    baseline = _run(baseline_model)
    target = baseline["research_fit_assessments"][0]
    target_input = next(
        item
        for item in baseline_model.inputs
        if item.initial_assessment.supervisor_id == target.supervisor_id
    )
    unsupported_id = target.breakdown.topic_alignment.supporting_evidence_ids[0]
    unsupported_rationale = target.breakdown.topic_alignment.rationale
    revised = make_revised_review(
        target_input,
        recommended_score=target.overall_score - 1,
        unsupported_claim_ids=(unsupported_id,),
        critique="The topic score requires revision after removing unsupported evidence.",
    )

    final_state = _run(FakeIndependentReviewModel({target.supervisor_id: (revised,)}))
    proposal = final_state["proposed_shortlist"]

    assert proposal is not None
    recommendation = next(
        item
        for item in proposal.recommendations
        if item.supervisor.supervisor_id == target.supervisor_id
    )
    assert unsupported_rationale not in recommendation.strengths
    assert recommendation.independent_review is not None
    assert unsupported_id not in recommendation.independent_review.effective_supporting_evidence_ids
    assert unsupported_id in recommendation.assessment.supporting_evidence_ids


def test_nebius_timeout_preserves_assessment_and_records_safe_error() -> None:
    baseline_model = FakeIndependentReviewModel()
    baseline = _run(baseline_model)
    target = baseline["research_fit_assessments"][0]
    sensitive_message = "nebius-secret candidate-private@example.test"
    model = FakeIndependentReviewModel(
        {target.supervisor_id: (IndependentReviewModelInvocationError(sensitive_message),)}
    )

    final_state = _run(model)
    record = next(
        item
        for item in final_state["research_fit_review_records"]
        if item.supervisor_id == target.supervisor_id
    )
    error = next(
        item
        for item in final_state["tool_errors"]
        if item.node == "review_fit_assessments"
        and item.code == "independent_review_model_invocation"
    )

    assert record.review_status is IndependentReviewStatus.UNAVAILABLE
    assert record.effective_score == target.overall_score
    assert record.effective_confidence is not target.confidence
    assert record.requires_candidate_attention is True
    assert sensitive_message not in error.message
    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_malformed_review_preserves_assessment_and_records_invalid_output() -> None:
    baseline = _run(FakeIndependentReviewModel())
    target = baseline["research_fit_assessments"][0]

    final_state = _run(
        FakeIndependentReviewModel(
            {
                target.supervisor_id: (
                    IndependentReviewModelOutputError("malformed provider payload"),
                )
            }
        )
    )

    record = next(
        item
        for item in final_state["research_fit_review_records"]
        if item.supervisor_id == target.supervisor_id
    )
    assert record.review_status is IndependentReviewStatus.UNAVAILABLE
    assert record.effective_score == target.overall_score
    assert any(
        error.code == "independent_review_invalid_output" for error in final_state["tool_errors"]
    )


def test_configured_disagreement_threshold_marks_candidate_attention() -> None:
    baseline_model = FakeIndependentReviewModel()
    baseline = _run(baseline_model)
    target = baseline["research_fit_assessments"][0]
    target_input = next(
        item
        for item in baseline_model.inputs
        if item.initial_assessment.supervisor_id == target.supervisor_id
    )
    revised = make_revised_review(
        target_input,
        recommended_score=target.overall_score - 6,
    )
    config = GraphFixtureConfig(
        independent_review_policy=IndependentReviewPolicy(disagreement_threshold=5)
    )

    final_state = _run(
        FakeIndependentReviewModel({target.supervisor_id: (revised,)}),
        config=config,
    )
    record = next(
        item
        for item in final_state["research_fit_review_records"]
        if item.supervisor_id == target.supervisor_id
    )

    assert record.requires_candidate_attention is True
    assert record.effective_confidence is not target.confidence


def test_missing_nebius_credentials_degrade_without_crashing_graph() -> None:
    final_state = _run(
        None,
        nebius_review_settings=NebiusReviewSettings(api_key=None),
    )

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["research_fit_review_records"]) == len(
        final_state["research_fit_assessments"]
    )
    assert all(
        record.review_status is IndependentReviewStatus.UNAVAILABLE
        for record in final_state["research_fit_review_records"]
    )
    assert all(
        error.code == "independent_review_model_invocation"
        for error in final_state["tool_errors"]
        if error.node == "review_fit_assessments"
    )
