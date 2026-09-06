"""Approved performance scopes supplement the unchanged whole-case measurement.

Boundary examples below are synthetic unit-test inputs, not new frozen scenarios.
"""

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholarpath.domain import CandidateReviewAction
from scholarpath.evaluation.interaction_budget import (
    InteractionBudgetReport,
    InteractionCaseMeasurement,
    InvocationPortUsage,
)
from scholarpath.evaluation.interaction_policy import (
    ApprovedInteractionPolicy,
    InteractionPolicyDecision,
    evaluate_interaction_case,
)
from scholarpath.evaluation.measurements import GraphPortInvocationCounts, RuntimeBudget
from scholarpath.graph import ReviewStatus

APPROVE = CandidateReviewAction.APPROVE
REJECT = CandidateReviewAction.REJECT
MORE = CandidateReviewAction.REQUEST_MORE


@pytest.fixture(scope="module")
def historical_report() -> InteractionBudgetReport:
    path = (
        Path(__file__).resolve().parents[3]
        / "docs/evaluation/week4-interaction-measurements-2026-09-06.json"
    )
    return InteractionBudgetReport.model_validate_json(path.read_text())


def _case(
    calls: tuple[int, ...] = (38,),
    actions: tuple[CandidateReviewAction, ...] = (),
    *,
    planning: tuple[int, ...] | None = None,
    interrupted: bool = True,
    status: ReviewStatus = ReviewStatus.PROPOSED,
    reached_first_review: bool = True,
) -> InteractionCaseMeasurement:
    """Make internally consistent count-only synthetic boundary observations."""
    plan_counts = planning if planning is not None else (1,) + (0,) * (len(calls) - 1)
    cumulative = dict.fromkeys(GraphPortInvocationCounts.model_fields, 0)
    invocations: list[InvocationPortUsage] = []
    for index, (total, plans) in enumerate(zip(calls, plan_counts, strict=True)):
        delta = dict.fromkeys(GraphPortInvocationCounts.model_fields, 0)
        delta.update(planning=plans, primary_search=total - plans)
        cumulative = {name: value + delta[name] for name, value in cumulative.items()}
        invocations.append(
            InvocationPortUsage(
                invocation_index=index,
                at_candidate_review=index < len(calls) - 1 or interrupted,
                cumulative_counts=GraphPortInvocationCounts.model_validate(cumulative),
                invocation_counts=GraphPortInvocationCounts.model_validate(delta),
                invocation_calls=total,
            )
        )
    return InteractionCaseMeasurement(
        scenario_id="approval-required-before-persistence",
        invocations=tuple(invocations),
        first_review_calls=calls[0] if reached_first_review else None,
        complete_scripted_interaction_calls=sum(calls),
        final_review_status=status,
        final_interrupted=interrupted,
        candidate_actions=actions,
        candidate_action_count=len(actions),
        expected_behavior_passed=True,
        legacy_whole_case_budget_passed=sum(calls) <= 40,
    )


def test_frozen_request_more_is_within_new_budget_so_far_not_a_completed_pass(
    historical_report: InteractionBudgetReport,
) -> None:
    case = next(
        item for item in historical_report.cases if item.scenario_id == "draft-graph-request-more"
    )
    result = evaluate_interaction_case(case)
    assert result.first_review_calls == 38
    assert result.interaction_calls == 76
    assert result.first_review_status == "passed"
    assert result.interaction_status == "within_budget_so_far"
    assert result.research_revisions == result.candidate_action_count == 1
    assert result.scope_reason == "within_scope"
    assert result.legacy_whole_case_budget_passed is False


def test_approved_policy_has_explicit_version_and_exact_authorized_limits() -> None:
    policy = ApprovedInteractionPolicy()
    assert policy.version == "week4-interaction-policy-v1"
    assert policy.first_review_limit == 40
    assert policy.full_interaction_limit == 80
    assert policy.max_research_revisions == 1
    assert policy.max_candidate_actions == 2


@pytest.mark.parametrize(
    ("scenario_id", "total"),
    (("draft-graph-approve-one", 39), ("draft-graph-reject-then-approve", 40)),
)
def test_frozen_approved_cases_complete_within_both_scopes(
    scenario_id: str, total: int, historical_report: InteractionBudgetReport
) -> None:
    case = next(item for item in historical_report.cases if item.scenario_id == scenario_id)
    result = evaluate_interaction_case(case)
    assert result.first_review_calls == 38
    assert result.interaction_calls == total
    assert result.first_review_status == result.interaction_status == "passed"
    assert result.legacy_whole_case_budget_passed is True


@pytest.mark.parametrize(("first", "status"), ((40, "passed"), (41, "exceeded")))
def test_first_review_limit_is_inclusive(first: int, status: str) -> None:
    assert evaluate_interaction_case(_case((first,))).first_review_status == status


@pytest.mark.parametrize(("total", "status"), ((80, "passed"), (81, "exceeded")))
def test_completed_interaction_limit_is_inclusive(total: int, status: str) -> None:
    case = _case((40, total - 40), (APPROVE,), interrupted=False, status=ReviewStatus.COMPLETED)
    result = evaluate_interaction_case(case)
    assert result.first_review_status == "passed"
    assert result.interaction_status == status
    assert result.legacy_whole_case_budget_passed is False


def test_paused_interaction_over_limit_is_exceeded_not_within_budget_so_far() -> None:
    assert evaluate_interaction_case(_case((38, 43), (MORE,))).interaction_status == "exceeded"


def test_no_first_review_is_neither_a_first_result_nor_a_completed_interaction() -> None:
    case = _case(
        (20,),
        interrupted=False,
        status=ReviewStatus.EVIDENCE_INCOMPLETE,
        reached_first_review=False,
    )
    result = evaluate_interaction_case(case)
    assert result.first_review_status == "not_reached"
    assert result.interaction_status == "not_completed"


@pytest.mark.parametrize("actions", ((REJECT,), (MORE,)))
def test_completed_status_without_explicit_approval_never_passes(
    actions: tuple[CandidateReviewAction, ...],
) -> None:
    case = _case((38, 1), actions, interrupted=False, status=ReviewStatus.COMPLETED)
    assert evaluate_interaction_case(case).interaction_status == "not_completed"


def test_approval_cannot_be_counted_as_success_while_still_paused() -> None:
    result = evaluate_interaction_case(_case((38, 1), (APPROVE,)))
    assert result.interaction_status == "not_applicable"
    assert result.scope_reason == "invalid_action_sequence"


@pytest.mark.parametrize(
    ("actions", "planning", "reason"),
    (
        ((REJECT, REJECT, APPROVE), (1, 0, 0, 0), "too_many_actions"),
        ((REJECT, APPROVE), (1, 1, 1), "too_many_revisions"),
        ((MORE, MORE), (1, 0, 0), "too_many_revisions"),
        ((APPROVE, REJECT), (1, 0, 0), "invalid_action_sequence"),
    ),
)
def test_out_of_scope_interactions_cannot_borrow_the_eighty_call_limit(
    actions: tuple[CandidateReviewAction, ...],
    planning: tuple[int, ...],
    reason: str,
) -> None:
    case = _case((38,) + (1,) * len(actions), actions, planning=planning)
    result = evaluate_interaction_case(case)
    assert result.scope_reason == reason
    assert result.interaction_status == "not_applicable"


def test_actual_resumed_planning_counts_as_a_revision_even_after_rejection() -> None:
    case = _case(
        (38, 38, 1),
        (REJECT, APPROVE),
        planning=(1, 1, 0),
        interrupted=False,
        status=ReviewStatus.COMPLETED,
    )
    result = evaluate_interaction_case(case)
    assert result.research_revisions == 1
    assert result.scope_reason == "within_scope"
    assert result.interaction_status == "passed"


@pytest.mark.parametrize(
    "change",
    (
        {"first_review_limit": 41},
        {"full_interaction_limit": 81},
        {"max_research_revisions": 2},
        {"max_candidate_actions": 3},
        {"api_key": "must-not-be-retained"},
    ),
)
def test_approved_policy_is_closed_to_unapproved_limits_and_private_fields(
    change: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        ApprovedInteractionPolicy.model_validate(ApprovedInteractionPolicy().model_dump() | change)


@pytest.mark.parametrize("mutation", ("total", "nested_counter", "policy", "extra"))
def test_evaluation_revalidates_tampered_models_instead_of_trusting_model_copy(
    mutation: str,
) -> None:
    case = _case()
    policy = ApprovedInteractionPolicy()
    if mutation == "total":
        case = case.model_copy(update={"complete_scripted_interaction_calls": 1})
    elif mutation == "nested_counter":
        observation = case.invocations[0]
        counters = observation.invocation_counts.model_copy(update={"planning": -1})
        case = case.model_copy(
            update={
                "invocations": (observation.model_copy(update={"invocation_counts": counters}),)
            }
        )
    elif mutation == "policy":
        policy = policy.model_copy(update={"full_interaction_limit": 1000})
    else:
        raw = case.model_dump()
        raw["source_url"] = "https://private.example.test/profile"
        with pytest.raises(ValidationError):
            InteractionCaseMeasurement.model_validate(raw)
        return
    with pytest.raises(ValueError):
        evaluate_interaction_case(case, policy)


def test_policy_evaluation_preserves_historical_report_and_legacy_budget(
    historical_report: InteractionBudgetReport,
) -> None:
    original = historical_report.model_dump_json()
    decisions = tuple(evaluate_interaction_case(case) for case in historical_report.cases)
    assert len(decisions) == 12
    assert historical_report.model_dump_json() == original
    assert historical_report.first_review_limit is historical_report.full_interaction_limit is None
    assert historical_report.supplemental_policy_status == "not_configured"
    assert historical_report.legacy_whole_case_budget_passed is False
    assert RuntimeBudget().graph_port_invocations == 40


def test_decision_is_count_only_closed_and_serializable() -> None:
    result = evaluate_interaction_case(_case())
    assert InteractionPolicyDecision.model_validate_json(result.model_dump_json()) == result
    payload = json.loads(result.model_dump_json())
    payload["candidate_statement"] = "private research detail"
    with pytest.raises(ValidationError):
        InteractionPolicyDecision.model_validate(payload)
