"""Apply approved offline limits without replacing historical measurement results."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Literal, Self

from langsmith import tracing_context
from pydantic import Field, model_validator

from .interaction_budget import InteractionBudgetReport, run_interaction_budget_diagnostic
from .interaction_policy import (
    ApprovedInteractionPolicy,
    InteractionPolicyDecision,
    evaluate_interaction_case,
)
from .models import EvaluationModel

type Count = Annotated[int, Field(strict=True, ge=0)]


class InteractionPolicySummary(EvaluationModel):
    """Keep completed passes, paused prefixes, and historical failures separate."""

    first_review_passed: Count
    first_review_exceeded: Count
    first_review_not_reached: Count
    completed_interaction_passed: Count
    within_budget_so_far: Count
    interaction_exceeded: Count
    interaction_not_completed: Count
    interaction_not_applicable: Count
    legacy_whole_case_failures: Count


def summarize_policy_decisions(
    decisions: Sequence[InteractionPolicyDecision],
) -> InteractionPolicySummary:
    """Count controlled decision labels; paused prefixes are never completed passes."""
    decisions = tuple(
        InteractionPolicyDecision.model_validate(item.model_dump()) for item in decisions
    )
    return InteractionPolicySummary(
        first_review_passed=sum(item.first_review_status == "passed" for item in decisions),
        first_review_exceeded=sum(item.first_review_status == "exceeded" for item in decisions),
        first_review_not_reached=sum(
            item.first_review_status == "not_reached" for item in decisions
        ),
        completed_interaction_passed=sum(item.interaction_status == "passed" for item in decisions),
        within_budget_so_far=sum(
            item.interaction_status == "within_budget_so_far" for item in decisions
        ),
        interaction_exceeded=sum(item.interaction_status == "exceeded" for item in decisions),
        interaction_not_completed=sum(
            item.interaction_status == "not_completed" for item in decisions
        ),
        interaction_not_applicable=sum(
            item.interaction_status == "not_applicable" for item in decisions
        ),
        legacy_whole_case_failures=sum(
            not item.legacy_whole_case_budget_passed for item in decisions
        ),
    )


class InteractionPolicyReport(EvaluationModel):
    """Versioned policy decisions alongside unchanged, count-only source measurements."""

    report_version: Literal["week4-interaction-policy-report-v1"] = (
        "week4-interaction-policy-report-v1"
    )
    recorded_on: date
    policy: ApprovedInteractionPolicy
    source_measurements: InteractionBudgetReport
    decisions: tuple[InteractionPolicyDecision, ...] = Field(min_length=12, max_length=12)
    summary: InteractionPolicySummary

    @model_validator(mode="after")
    def verify_derivation(self) -> Self:
        policy = ApprovedInteractionPolicy.model_validate(self.policy.model_dump())
        source = InteractionBudgetReport.model_validate(self.source_measurements.model_dump())
        expected = tuple(evaluate_interaction_case(case, policy) for case in source.cases)
        actual = tuple(
            InteractionPolicyDecision.model_validate(item.model_dump()) for item in self.decisions
        )
        if actual != expected:
            raise ValueError("Policy decisions must derive from the ordered source measurements")
        summary = InteractionPolicySummary.model_validate(self.summary.model_dump())
        if summary != summarize_policy_decisions(expected):
            raise ValueError("Policy summary must preserve each distinct outcome")
        return self


def build_interaction_policy_report(
    measurements: InteractionBudgetReport, *, recorded_on: date | None = None
) -> InteractionPolicyReport:
    """Pure policy evaluation; no graph invocation, provider call, or trace upload."""
    source = InteractionBudgetReport.model_validate(measurements.model_dump())
    policy = ApprovedInteractionPolicy()
    decisions = tuple(evaluate_interaction_case(case, policy) for case in source.cases)
    return InteractionPolicyReport(
        recorded_on=recorded_on if recorded_on is not None else datetime.now(UTC).date(),
        policy=policy,
        source_measurements=source,
        decisions=decisions,
        summary=summarize_policy_decisions(decisions),
    )


def run_interaction_policy_check() -> InteractionPolicyReport:
    """Re-run the existing frozen fake cases with tracing unconditionally disabled."""
    with tracing_context(enabled=False):
        return build_interaction_policy_report(run_interaction_budget_diagnostic())


def render_interaction_policy_report(report: InteractionPolicyReport) -> str:
    """Render only controlled labels and numerical observations, not source payloads."""
    report = InteractionPolicyReport.model_validate(report.model_dump())
    policy, summary = report.policy, report.summary
    lines = [
        f"Offline interaction policy: {policy.version}; {report.recorded_on.isoformat()} UTC",
        f"Dataset: {report.source_measurements.dataset_name}",
        f"First-review limit: {policy.first_review_limit} calls; "
        f"bounded-interaction limit: {policy.full_interaction_limit} total calls.",
        f"Scope: at most {policy.max_research_revisions} research revision and "
        f"{policy.max_candidate_actions} accepted Candidate actions; approval must be last.",
        "Historical whole-case limit: "
        f"{report.source_measurements.legacy_graph_port_invocation_budget} calls, "
        "retained separately.",
    ]
    for item in report.decisions:
        first = "not reached" if item.first_review_calls is None else str(item.first_review_calls)
        lines.append(
            f"{item.scenario_id}: first review={first}/{policy.first_review_limit} "
            f"[{item.first_review_status}]; interaction={item.interaction_calls}/"
            f"{policy.full_interaction_limit} [{item.interaction_status}]; "
            f"scope={item.scope_reason}; legacy="
            f"{'passed' if item.legacy_whole_case_budget_passed else 'exceeded'}"
        )
    lines.extend(
        (
            f"First review: {summary.first_review_passed} passed; "
            f"{summary.first_review_exceeded} exceeded; "
            f"{summary.first_review_not_reached} not reached.",
            f"Interactions: {summary.completed_interaction_passed} completed within budget; "
            f"{summary.within_budget_so_far} paused within budget so far; "
            f"{summary.interaction_exceeded} exceeded; "
            f"{summary.interaction_not_completed} not completed; "
            f"{summary.interaction_not_applicable} outside policy scope.",
            f"Legacy whole-case budget failures: {summary.legacy_whole_case_failures}.",
            "A paused prefix is not a completed interaction or an approved shortlist.",
            "This is an approved measurement-policy change, not a runtime optimization. "
            "Fake port calls are not live HTTP requests, tokens, or monetary cost.",
        )
    )
    return "\n".join(lines)


def policy_report_exit_code(report: InteractionPolicyReport) -> int:
    """Retain legacy failures and fail on exceeded, unreached, or unsupported outcomes."""
    report = InteractionPolicyReport.model_validate(report.model_dump())
    summary = report.summary
    return int(
        any(
            (
                summary.first_review_exceeded,
                summary.first_review_not_reached,
                summary.interaction_exceeded,
                summary.interaction_not_completed,
                summary.interaction_not_applicable,
                summary.legacy_whole_case_failures,
            )
        )
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Print an offline comparison; exit 1 preserves the legacy overrun, 2 means error."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        report = run_interaction_policy_check()
        report = InteractionPolicyReport.model_validate(report.model_dump())
        rendered = (
            report.model_dump_json(indent=2)
            if args.format == "json"
            else render_interaction_policy_report(report)
        )
        exit_code = policy_report_exit_code(report)
    except Exception:
        print("The offline interaction policy check could not complete safely.", file=sys.stderr)
        return 2
    print(rendered)
    return exit_code
