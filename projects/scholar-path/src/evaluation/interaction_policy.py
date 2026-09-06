"""Approved, supplemental fake-effort policy; historical measurements stay unchanged."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..domain import CandidateReviewAction
from ..graph import ReviewStatus
from .interaction_budget import GraphScenarioId, InteractionCaseMeasurement

type StrictCount = Annotated[int, Field(strict=True, ge=0)]
type FirstReviewStatus = Literal["passed", "exceeded", "not_reached"]
type InteractionStatus = Literal[
    "passed", "within_budget_so_far", "exceeded", "not_completed", "not_applicable"
]
type ScopeReason = Literal[
    "within_scope", "too_many_actions", "too_many_revisions", "invalid_action_sequence"
]


class ApprovedInteractionPolicy(BaseModel):
    """Versioned allowance for bounded fake work, never an approval or live-cost claim."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True, validate_default=True)

    version: Literal["week4-interaction-policy-v1"] = "week4-interaction-policy-v1"
    first_review_limit: Literal[40] = 40
    full_interaction_limit: Literal[80] = 80
    max_research_revisions: Literal[1] = 1
    max_candidate_actions: Literal[2] = 2

    @field_validator(
        "first_review_limit",
        "full_interaction_limit",
        "max_research_revisions",
        "max_candidate_actions",
        mode="before",
    )
    @classmethod
    def require_integer_limits(cls, value: object) -> object:
        """Literal equality alone would accept equal floats and booleans."""
        if type(value) is not int:
            raise ValueError("Approved limits must be exact integers")
        return value


class InteractionPolicyDecision(BaseModel):
    """Closed, count-only decision; a paused interaction cannot claim completion."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    scenario_id: GraphScenarioId
    first_review_calls: StrictCount | None
    interaction_calls: StrictCount
    research_revisions: StrictCount
    candidate_action_count: StrictCount
    first_review_status: FirstReviewStatus
    interaction_status: InteractionStatus
    scope_reason: ScopeReason
    legacy_whole_case_budget_passed: bool


def _scope_reason(
    measurement: InteractionCaseMeasurement,
    policy: ApprovedInteractionPolicy,
    research_revisions: int,
) -> ScopeReason:
    """Apply workload limits before checking whether its call count is affordable."""
    actions = measurement.candidate_actions
    if measurement.candidate_action_count > policy.max_candidate_actions:
        return "too_many_actions"
    if (
        research_revisions > policy.max_research_revisions
        or actions.count(CandidateReviewAction.REQUEST_MORE) > policy.max_research_revisions
    ):
        return "too_many_revisions"
    if CandidateReviewAction.APPROVE in actions[:-1]:
        return "invalid_action_sequence"
    # An approval cannot both complete and leave a review interrupt outstanding.
    if actions and actions[-1] is CandidateReviewAction.APPROVE and measurement.final_interrupted:
        return "invalid_action_sequence"
    return "within_scope"


def _interaction_status(
    measurement: InteractionCaseMeasurement,
    policy: ApprovedInteractionPolicy,
    scope_reason: ScopeReason,
) -> InteractionStatus:
    """Separate total effort, partial progress, and a completed approved interaction."""
    if scope_reason != "within_scope":
        return "not_applicable"
    if measurement.complete_scripted_interaction_calls > policy.full_interaction_limit:
        return "exceeded"
    approved = bool(
        measurement.candidate_actions
        and measurement.candidate_actions[-1] is CandidateReviewAction.APPROVE
    )
    if (
        measurement.final_review_status is ReviewStatus.COMPLETED
        and not measurement.final_interrupted
        and approved
    ):
        return "passed"
    if (
        measurement.final_interrupted
        and measurement.final_review_status is ReviewStatus.PROPOSED
        and not approved
    ):
        return "within_budget_so_far"
    return "not_completed"


def evaluate_interaction_case(
    measurement: InteractionCaseMeasurement,
    policy: ApprovedInteractionPolicy | None = None,
) -> InteractionPolicyDecision:
    """Evaluate measured boundaries without running a graph or changing legacy results."""
    # Pydantic trusts existing instances by default: reject unchecked model_copy data.
    measured = InteractionCaseMeasurement.model_validate(measurement.model_dump())
    resolved = ApprovedInteractionPolicy.model_validate(
        (policy if policy is not None else ApprovedInteractionPolicy()).model_dump()
    )
    research_revisions = sum(
        invocation.invocation_counts.planning > 0 for invocation in measured.invocations[1:]
    )
    reason = _scope_reason(measured, resolved, research_revisions)
    first_status: FirstReviewStatus = (
        "not_reached"
        if measured.first_review_calls is None
        else "passed"
        if measured.first_review_calls <= resolved.first_review_limit
        else "exceeded"
    )
    return InteractionPolicyDecision(
        scenario_id=measured.scenario_id,
        first_review_calls=measured.first_review_calls,
        interaction_calls=measured.complete_scripted_interaction_calls,
        research_revisions=research_revisions,
        candidate_action_count=measured.candidate_action_count,
        first_review_status=first_status,
        interaction_status=_interaction_status(measured, resolved, reason),
        scope_reason=reason,
        legacy_whole_case_budget_passed=measured.legacy_whole_case_budget_passed,
    )
