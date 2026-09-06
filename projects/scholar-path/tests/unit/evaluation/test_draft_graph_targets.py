"""Additive fake graph cases for the separate draft evaluation catalog."""

import pytest

from scholarpath.domain import CandidateReviewAction, EvidenceConfidence, IndependentReviewStatus
from scholarpath.evaluation.fakes import StaticPlanningModel
from scholarpath.evaluation.models import GraphTargetOutput
from scholarpath.evaluation.scenarios import evaluation_dataset_inputs, evaluation_scenario_by_id
from scholarpath.evaluation.targets import fake_end_to_end_target
from scholarpath.graph import ReviewStatus, build_walking_skeleton_fixtures, default_review_decision


def _inputs(graph_case: str) -> dict[str, object]:
    scenario = evaluation_scenario_by_id("approval-required-before-persistence").model_copy(
        update={"scenario_id": f"draft-{graph_case}", "config": {"graph_case": graph_case}}
    )
    return evaluation_dataset_inputs(scenario)


@pytest.mark.parametrize(
    "graph_case",
    [
        "approve_one",
        "approve_subset",
        "request_more",
        "reject_then_approve",
        "review_timeout",
        "review_malformed",
    ],
)
def test_additive_case_executes_the_fake_graph_with_exact_outcomes(graph_case: str) -> None:
    output = GraphTargetOutput.model_validate(fake_end_to_end_target(_inputs(graph_case)))
    proposal_ids = default_review_decision().supervisor_ids
    supervisor_ids = tuple(
        supervisor.supervisor_id
        for supervisor in build_walking_skeleton_fixtures().raw_search_results
    )
    completed = graph_case in {"approve_one", "approve_subset", "reject_then_approve"}
    expected_proposal_ids = (
        (*proposal_ids[1:], supervisor_ids[5])
        if graph_case == "reject_then_approve"
        else proposal_ids
    )
    expected_shortlisted_ids = {
        "approve_one": proposal_ids[:1],
        "approve_subset": proposal_ids[:2],
        "reject_then_approve": proposal_ids[1:3],
    }.get(graph_case, ())
    expected_actions = {
        "approve_one": ((CandidateReviewAction.APPROVE, proposal_ids[:1]),),
        "approve_subset": ((CandidateReviewAction.APPROVE, proposal_ids[:2]),),
        "request_more": ((CandidateReviewAction.REQUEST_MORE, proposal_ids),),
        "reject_then_approve": (
            (CandidateReviewAction.REJECT, proposal_ids[:1]),
            (CandidateReviewAction.APPROVE, proposal_ids[1:3]),
        ),
    }.get(graph_case, ())
    expected_error_codes = {
        "review_timeout": ("independent_review_model_invocation",),
        "review_malformed": ("independent_review_invalid_output",),
    }.get(graph_case, ())
    expected_calls = {
        "approve_one": 39,
        "approve_subset": 39,
        "request_more": 76,
        "reject_then_approve": 40,
        "review_timeout": 38,
        "review_malformed": 38,
    }

    assert "synthesize_supervisor_shortlist" in output.execution_log
    assert output.measurements.port_invocations == expected_calls[graph_case]
    assert output.scenario_id == f"draft-{graph_case}"
    assert output.review_status is (ReviewStatus.COMPLETED if completed else ReviewStatus.PROPOSED)
    assert output.interrupted is not completed
    assert output.prospective_supervisor_ids == supervisor_ids
    assert output.proposed_supervisor_ids == expected_proposal_ids
    assert output.shortlisted_supervisor_ids == expected_shortlisted_ids
    assert output.rejected_supervisor_ids == (
        proposal_ids[:1] if graph_case == "reject_then_approve" else ()
    )
    assert tuple((item.action, item.supervisor_ids) for item in output.candidate_reviews) == (
        expected_actions
    )
    assert output.tool_error_codes == expected_error_codes
    assert output.fallback_search_used is False
    assert len(output.verification_records) == 8
    assert all(item.verified_supervisor_present for item in output.verification_records)
    assert len(output.assessments) == len(output.independent_reviews) == 8
    first_review = output.independent_reviews[0]
    assert first_review.supervisor_id == supervisor_ids[0]
    assert first_review.effective_score == 87
    assert first_review.review_status is (
        IndependentReviewStatus.UNAVAILABLE
        if expected_error_codes
        else IndependentReviewStatus.ACCEPTED
    )
    assert first_review.effective_confidence is (
        EvidenceConfidence.MEDIUM if expected_error_codes else EvidenceConfidence.HIGH
    )
    assert first_review.requires_candidate_attention is bool(expected_error_codes)
    assert (
        "save_shortlisted_supervisors" in output.execution_log
        if completed
        else ("save_shortlisted_supervisors" not in output.execution_log)
    )
    if completed:
        assert output.execution_log[-1] == "generate_shortlist_briefing"
    else:
        assert output.execution_log[-1] == "synthesize_supervisor_shortlist"


def test_request_more_changes_next_planning_input_and_pauses_again(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    planning = StaticPlanningModel()
    monkeypatch.setattr("scholarpath.evaluation.targets.StaticPlanningModel", lambda: planning)

    output = GraphTargetOutput.model_validate(fake_end_to_end_target(_inputs("request_more")))

    assert len(planning.inputs) == 2
    assert planning.inputs[0].target_regions == ("South Africa", "United Kingdom", "Netherlands")
    assert planning.inputs[1].target_regions == ("Germany",)
    assert planning.inputs[1].remembered_candidate_preferences[-1].preferred_regions == ("Germany",)
    assert output.execution_log.count("plan_supervisor_searches") == 2
    assert output.execution_log.count("synthesize_supervisor_shortlist") == 2
    assert output.interrupted is True
    assert output.shortlisted_supervisor_ids == ()


@pytest.mark.parametrize("graph_case", ["review_timeout", "review_malformed"])
def test_unavailable_review_preserves_all_original_assessments_and_evidence(
    graph_case: str,
) -> None:
    baseline = GraphTargetOutput.model_validate(fake_end_to_end_target(_inputs("approval_pause")))
    output = GraphTargetOutput.model_validate(fake_end_to_end_target(_inputs(graph_case)))

    assert output.assessments == baseline.assessments
    assert output.verification_records == baseline.verification_records
    assert output.proposed_supervisor_ids == baseline.proposed_supervisor_ids
    assert output.independent_reviews[1:] == baseline.independent_reviews[1:]
    assert output.independent_reviews[0].effective_rationale == (
        baseline.independent_reviews[0].effective_rationale
    )
    assert output.independent_reviews[0].effective_score == (
        baseline.independent_reviews[0].effective_score
    )
    assert output.independent_reviews[0].unsupported_claim_ids == ()
    assert output.independent_reviews[0].overlooked_evidence_ids == ()
    assert output.shortlisted_supervisor_ids == ()


def test_rejection_is_recorded_before_approval_without_reintroducing_supervisor() -> None:
    output = GraphTargetOutput.model_validate(
        fake_end_to_end_target(_inputs("reject_then_approve"))
    )
    rejected_id = default_review_decision().supervisor_ids[0]

    assert output.candidate_reviews[0].action is CandidateReviewAction.REJECT
    assert output.candidate_reviews[0].supervisor_ids == (rejected_id,)
    assert output.candidate_reviews[1].action is CandidateReviewAction.APPROVE
    assert rejected_id not in output.candidate_reviews[1].supervisor_ids
    assert rejected_id not in output.proposed_supervisor_ids
    assert rejected_id not in output.shortlisted_supervisor_ids
    assert output.execution_log.count("learn_candidate_preferences") == 2
    assert output.execution_log.count("save_shortlisted_supervisors") == 1


def test_unknown_graph_case_still_fails_explicitly() -> None:
    with pytest.raises(ValueError, match="Unknown fake graph evaluation case"):
        fake_end_to_end_target(_inputs("not-a-real-case"))
