"""Measure real fake-graph invocation boundaries without approving new budgets."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import UTC, date, datetime
from typing import Annotated, Final, Literal, Self

from langsmith import tracing_context
from pydantic import Field, model_validator

from ..domain import CandidateReviewAction
from ..graph import ReviewStatus
from .evaluators import expected_behavior
from .measurements import GraphInvocationObservation, GraphPortInvocationCounts, RuntimeBudget
from .models import EvaluationModel, EvaluationTargetKind, GraphTargetOutput
from .reviewed_manifest import ReviewedEvaluationManifest, build_reviewed_manifest
from .scenarios import evaluation_dataset_inputs, evaluation_dataset_reference_outputs
from .targets import fake_end_to_end_target

type StrictCount = Annotated[int, Field(strict=True, ge=0)]
type GraphScenarioId = Literal[
    "duplicate-supervisor-multiple-queries",
    "you-timeout-tavily-fallback",
    "evidence-extraction-failure",
    "independent-reviewer-disagreement",
    "candidate-rejects-highly-theoretical",
    "approval-required-before-persistence",
    "draft-graph-approve-one",
    "draft-graph-approve-subset",
    "draft-graph-request-more",
    "draft-graph-reject-then-approve",
    "draft-graph-review-timeout",
    "draft-graph-review-malformed",
]
_ERROR_MESSAGE: Final = "The offline interaction measurement could not complete safely."


def _difference(
    current: GraphPortInvocationCounts, previous: GraphPortInvocationCounts | None
) -> GraphPortInvocationCounts:
    """Subtract actual cumulative counters; declining observations are invalid."""
    return GraphPortInvocationCounts.model_validate(
        {
            name: getattr(current, name) - (getattr(previous, name) if previous else 0)
            for name in GraphPortInvocationCounts.model_fields
        }
    )


class InvocationPortUsage(EvaluationModel):
    """One completed graph invocation, not a model call or inferred research round."""

    invocation_index: StrictCount
    at_candidate_review: Annotated[bool, Field(strict=True)]
    cumulative_counts: GraphPortInvocationCounts
    invocation_counts: GraphPortInvocationCounts
    invocation_calls: StrictCount

    @model_validator(mode="after")
    def validate_counter_totals(self) -> Self:
        GraphPortInvocationCounts.model_validate(self.cumulative_counts.model_dump())
        interval = GraphPortInvocationCounts.model_validate(self.invocation_counts.model_dump())
        if self.invocation_calls != interval.total:
            raise ValueError("Invocation total must equal its measured port counters")
        return self


class InteractionCaseMeasurement(EvaluationModel):
    """Numeric work up to first review and through the complete scripted case."""

    scenario_id: GraphScenarioId
    invocations: tuple[InvocationPortUsage, ...] = Field(min_length=1, max_length=5)
    first_review_calls: StrictCount | None
    complete_scripted_interaction_calls: StrictCount
    final_review_status: ReviewStatus
    final_interrupted: Annotated[bool, Field(strict=True)]
    candidate_actions: tuple[CandidateReviewAction, ...] = Field(max_length=20)
    candidate_action_count: StrictCount
    expected_behavior_passed: Annotated[bool, Field(strict=True)]
    legacy_whole_case_budget_passed: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def validate_measured_boundaries(self) -> Self:
        previous: GraphPortInvocationCounts | None = None
        for index, raw in enumerate(self.invocations):
            invocation = InvocationPortUsage.model_validate(raw.model_dump())
            if invocation.invocation_index != index:
                raise ValueError("Invocation observations must be contiguous and ordered")
            if index and not self.invocations[index - 1].at_candidate_review:
                raise ValueError("A completed terminal invocation cannot be resumed")
            if invocation.invocation_counts != _difference(invocation.cumulative_counts, previous):
                raise ValueError("Invocation counters must equal successive cumulative deltas")
            previous = invocation.cumulative_counts
        first, last = self.invocations[0], self.invocations[-1]
        if self.first_review_calls != (
            first.cumulative_counts.total if first.at_candidate_review else None
        ):
            raise ValueError("First-review effort requires an observed initial review pause")
        if self.complete_scripted_interaction_calls != last.cumulative_counts.total:
            raise ValueError("Complete interaction total must match the last measured boundary")
        if self.final_interrupted != last.at_candidate_review:
            raise ValueError("Final pause status must match its observed boundary")
        if self.candidate_action_count != len(self.candidate_actions):
            raise ValueError("Action count must match actual projected Candidate actions")
        # Every scripted response in this frozen cohort is one accepted action.
        if len(self.invocations) != self.candidate_action_count + 1:
            raise ValueError("Each accepted scripted action requires its own measured resume")
        if self.final_interrupted and self.final_review_status is not ReviewStatus.PROPOSED:
            raise ValueError("An observed review pause requires proposed review status")
        if not self.expected_behavior_passed:
            raise ValueError("Measurements require the frozen expected behavior to pass")
        if self.legacy_whole_case_budget_passed != (
            self.complete_scripted_interaction_calls <= RuntimeBudget().graph_port_invocations
        ):
            raise ValueError("Legacy assessment must retain the complete-case budget")
        return self


class InteractionBudgetReport(EvaluationModel):
    """Supplemental measurements, with both new numeric targets explicitly unset."""

    measurement_version: Literal["week4-interaction-measurements-v1"] = (
        "week4-interaction-measurements-v1"
    )
    dataset_name: Literal["scholarpath-week4-30case-reviewed-v1"]
    reviewed_version: Literal["week4-30case-reviewed-v1"]
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_draft_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    recorded_on: date
    execution_mode: Literal["fake_only"] = "fake_only"
    measurement_scope: Literal["actual_graph_invocation_boundaries"] = (
        "actual_graph_invocation_boundaries"
    )
    supplemental_policy_status: Literal["not_configured"] = "not_configured"
    first_review_limit: None = None
    full_interaction_limit: None = None
    legacy_budget_scope: Literal["complete_graph_case"] = "complete_graph_case"
    legacy_graph_port_invocation_budget: Literal[40] = 40
    case_count: Literal[12] = 12
    cases: tuple[InteractionCaseMeasurement, ...] = Field(min_length=12, max_length=12)
    legacy_whole_case_budget_passed: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def validate_frozen_cohort(self) -> Self:
        manifest = build_reviewed_manifest()
        if (
            self.content_digest != manifest.content_digest
            or self.source_draft_digest != manifest.source_draft_digest
        ):
            raise ValueError("Measurement metadata must identify the frozen reviewed manifest")
        expected_ids = tuple(
            case.scenario.scenario_id
            for case in manifest.source_draft.cases
            if case.scenario.target is EvaluationTargetKind.GRAPH_FAKE
        )
        cases = tuple(
            InteractionCaseMeasurement.model_validate(item.model_dump()) for item in self.cases
        )
        if tuple(item.scenario_id for item in cases) != expected_ids:
            raise ValueError("Measure each frozen graph case exactly once in manifest order")
        if self.legacy_graph_port_invocation_budget != RuntimeBudget().graph_port_invocations:
            raise ValueError("The legacy graph budget cannot change in a measurement report")
        if self.legacy_whole_case_budget_passed != all(
            item.legacy_whole_case_budget_passed for item in cases
        ):
            raise ValueError("The report cannot hide a legacy budget failure")
        return self


class InteractionMeasurementError(RuntimeError):
    """Fixed-message contract failure without provider or Candidate details."""

    def __init__(self) -> None:
        super().__init__(_ERROR_MESSAGE)


def run_interaction_budget_diagnostic(
    manifest: ReviewedEvaluationManifest | None = None,
    *,
    recorded_on: date | None = None,
) -> InteractionBudgetReport:
    """Observe all twelve existing fake graph cases; never call or trace live services."""
    with tracing_context(enabled=False):
        resolved = manifest if manifest is not None else build_reviewed_manifest()
        resolved = ReviewedEvaluationManifest.model_validate(resolved.model_dump())
        cases: list[InteractionCaseMeasurement] = []
        for case in resolved.source_draft.cases:
            scenario = case.scenario
            if scenario.target is not EvaluationTargetKind.GRAPH_FAKE:
                continue
            observations: list[GraphInvocationObservation] = []
            raw_output = fake_end_to_end_target(
                evaluation_dataset_inputs(scenario), invocation_usage_observer=observations.append
            )
            output = GraphTargetOutput.model_validate(raw_output)
            if (
                output.target is not EvaluationTargetKind.GRAPH_FAKE
                or output.scenario_id != scenario.scenario_id
                or not observations
            ):
                raise InteractionMeasurementError()
            invocations: list[InvocationPortUsage] = []
            previous: GraphPortInvocationCounts | None = None
            for raw in observations:
                observed = GraphInvocationObservation.model_validate(raw.model_dump())
                delta = _difference(observed.cumulative_counts, previous)
                invocations.append(
                    InvocationPortUsage(
                        invocation_index=observed.invocation_index,
                        at_candidate_review=observed.at_candidate_review,
                        cumulative_counts=observed.cumulative_counts,
                        invocation_counts=delta,
                        invocation_calls=delta.total,
                    )
                )
                previous = observed.cumulative_counts
            first, last = invocations[0], invocations[-1]
            if output.measurements.port_invocations != last.cumulative_counts.total:
                raise InteractionMeasurementError()
            outcome = expected_behavior(raw_output, evaluation_dataset_reference_outputs(scenario))
            if outcome.score is not True:
                raise InteractionMeasurementError()
            cases.append(
                InteractionCaseMeasurement.model_validate(
                    {
                        "scenario_id": scenario.scenario_id,
                        "invocations": tuple(invocations),
                        "first_review_calls": (
                            first.cumulative_counts.total if first.at_candidate_review else None
                        ),
                        "complete_scripted_interaction_calls": last.cumulative_counts.total,
                        "final_review_status": output.review_status,
                        "final_interrupted": output.interrupted,
                        "candidate_actions": tuple(
                            item.action for item in output.candidate_reviews
                        ),
                        "candidate_action_count": len(output.candidate_reviews),
                        "expected_behavior_passed": True,
                        "legacy_whole_case_budget_passed": (
                            last.cumulative_counts.total <= RuntimeBudget().graph_port_invocations
                        ),
                    }
                )
            )
        return InteractionBudgetReport(
            dataset_name=resolved.dataset_name,
            reviewed_version=resolved.reviewed_version,
            content_digest=resolved.content_digest,
            source_draft_digest=resolved.source_draft_digest,
            recorded_on=recorded_on if recorded_on is not None else datetime.now(UTC).date(),
            cases=tuple(cases),
            legacy_whole_case_budget_passed=all(
                item.legacy_whole_case_budget_passed for item in cases
            ),
        )


def render_interaction_budget_report(report: InteractionBudgetReport) -> str:
    """Render only validated case identities, counts, and controlled status labels."""
    report = InteractionBudgetReport.model_validate(report.model_dump())
    lines = [
        f"Offline interaction measurements: {report.recorded_on.isoformat()} UTC",
        f"Measurement version: {report.measurement_version}",
        f"Dataset: {report.dataset_name} ({report.reviewed_version})",
        f"Content SHA-256: {report.content_digest}",
        f"Source draft SHA-256: {report.source_draft_digest}",
        "Actual invocation boundaries within each case; no cross-case phase inference.",
        "Supplemental limits: first review=not configured; full interaction=not configured.",
        f"Legacy budget: {report.legacy_graph_port_invocation_budget} calls "
        "per complete graph case.",
    ]
    for case in report.cases:
        first = "not reached" if case.first_review_calls is None else str(case.first_review_calls)
        lines.append(
            f"{case.scenario_id}: first review={first}; complete interaction="
            f"{case.complete_scripted_interaction_calls}/"
            f"{report.legacy_graph_port_invocation_budget} "
            f"[{'pass' if case.legacy_whole_case_budget_passed else 'exceeded'}]; "
            f"invocation calls={[item.invocation_calls for item in case.invocations]}; "
            f"status={case.final_review_status.value}; interrupted={case.final_interrupted}"
        )
    lines.extend(
        (
            "Initial invocation ends at first Candidate review or a terminal result. "
            "Resumes include feedback work.",
            "Complete scripted interaction may end paused; "
            "it does not imply approval or a completed shortlist.",
            "Fake application-port calls are not HTTP requests, tokens, monetary cost, "
            "or human review time.",
            "No new budget is approved; the original whole-case result remains unchanged.",
        )
    )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Exit 1 for the preserved legacy overrun, 2 for a sanitized diagnostic failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        report = run_interaction_budget_diagnostic()
        report = InteractionBudgetReport.model_validate(report.model_dump())
        rendered = (
            report.model_dump_json(indent=2)
            if args.format == "json"
            else render_interaction_budget_report(report)
        )
    except Exception:
        print(_ERROR_MESSAGE, file=sys.stderr)
        return 2
    print(rendered)
    return 0 if report.legacy_whole_case_budget_passed else 1
