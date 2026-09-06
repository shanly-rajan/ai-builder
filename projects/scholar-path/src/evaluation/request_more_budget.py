"""Compare two frozen fake graph cases without weakening the whole-case call budget."""

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
from .measurements import GraphPortInvocationCounts, RuntimeBudget
from .models import EvaluationModel, EvaluationTargetKind, GraphTargetOutput
from .reviewed_manifest import ReviewedEvaluationManifest, build_reviewed_manifest
from .scenarios import evaluation_dataset_inputs, evaluation_dataset_reference_outputs
from .targets import fake_end_to_end_target

type DiagnosticScenarioId = Literal[
    "approval-required-before-persistence", "draft-graph-request-more"
]
type StrictCount = Annotated[int, Field(strict=True, ge=0)]
type StrictDelta = Annotated[int, Field(strict=True)]

SCENARIO_IDS: Final[tuple[DiagnosticScenarioId, DiagnosticScenarioId]] = (
    "approval-required-before-persistence",
    "draft-graph-request-more",
)
_ERROR_MESSAGE: Final = "The offline call-budget diagnostic could not complete safely."


class GraphPortInvocationDelta(EvaluationModel):
    """Signed differences between independent cases, never inferred phase timings."""

    planning: StrictDelta
    primary_search: StrictDelta
    fallback_search: StrictDelta
    alternate_evidence_search: StrictDelta
    content_extraction: StrictDelta
    evidence_model: StrictDelta
    research_fit: StrictDelta
    independent_review: StrictDelta
    memory_load: StrictDelta
    memory_store: StrictDelta

    @property
    def total(self) -> int:
        """Retain negative deltas if a future measured case does less work."""
        return sum(self.model_dump().values())


class GraphBudgetCase(EvaluationModel):
    """Closed identity, numeric observations, and explicit outcome statuses only."""

    scenario_id: DiagnosticScenarioId
    port_invocations: GraphPortInvocationCounts
    total_port_invocations: StrictCount
    planning_passes: Annotated[int, Field(strict=True, ge=1)]
    review_status: ReviewStatus
    candidate_actions: tuple[CandidateReviewAction, ...] = Field(max_length=4)
    interrupted: Annotated[bool, Field(strict=True)]
    expected_behavior_passed: Annotated[bool, Field(strict=True)]
    whole_case_budget_passed: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def require_consistent_observations(self) -> Self:
        counts = GraphPortInvocationCounts.model_validate(self.port_invocations.model_dump())
        if not self.expected_behavior_passed:
            raise ValueError("A call-budget comparison requires the frozen expected outcome")
        if self.total_port_invocations != counts.total:
            raise ValueError("Per-port observations must reconcile with the case total")
        if self.whole_case_budget_passed != (
            counts.total <= RuntimeBudget().graph_port_invocations
        ):
            raise ValueError("The whole-case budget decision must use the unchanged budget")
        return self


class RequestMoreBudgetReport(EvaluationModel):
    """Offline diagnostic linked to frozen labels, not a new baseline or cost estimate."""

    dataset_name: Literal["scholarpath-week4-30case-reviewed-v1"]
    reviewed_version: Literal["week4-30case-reviewed-v1"]
    content_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_draft_digest: str = Field(pattern=r"^[a-f0-9]{64}$")
    recorded_on: date
    execution_mode: Literal["fake_only"] = "fake_only"
    comparison_scope: Literal["two_independent_frozen_cases"] = "two_independent_frozen_cases"
    budget_scope: Literal["complete_graph_case"] = "complete_graph_case"
    graph_port_invocation_budget: Literal[40] = 40
    case_count: Literal[2] = 2
    cases: tuple[GraphBudgetCase, GraphBudgetCase]
    additional_port_invocations: GraphPortInvocationDelta
    additional_total_port_invocations: StrictDelta
    whole_case_budget_passed: Annotated[bool, Field(strict=True)]

    @model_validator(mode="after")
    def require_consistent_comparison(self) -> Self:
        manifest = build_reviewed_manifest()
        if (
            self.content_digest != manifest.content_digest
            or self.source_draft_digest != manifest.source_draft_digest
        ):
            raise ValueError("Diagnostic metadata must identify the frozen reviewed manifest")
        cases = tuple(GraphBudgetCase.model_validate(item.model_dump()) for item in self.cases)
        if tuple(item.scenario_id for item in cases) != SCENARIO_IDS:
            raise ValueError("The diagnostic compares exactly the two frozen cases in order")
        first, second = cases
        expected_delta = {
            name: getattr(second.port_invocations, name) - getattr(first.port_invocations, name)
            for name in GraphPortInvocationCounts.model_fields
        }
        delta = GraphPortInvocationDelta.model_validate(
            self.additional_port_invocations.model_dump()
        )
        if delta.model_dump() != expected_delta:
            raise ValueError("The per-port delta must compare the two independent cases")
        if self.additional_total_port_invocations != (
            second.total_port_invocations - first.total_port_invocations
        ):
            raise ValueError("The additional total must reconcile with the case totals")
        if self.whole_case_budget_passed != all(item.whole_case_budget_passed for item in cases):
            raise ValueError("The comparison cannot hide an exceeded whole-case budget")
        if self.graph_port_invocation_budget != RuntimeBudget().graph_port_invocations:
            raise ValueError("The diagnostic must preserve the configured graph budget")
        return self


class RequestMoreBudgetDiagnosticError(RuntimeError):
    """Fixed-message failure without raw graph outputs or exception details."""

    def __init__(self) -> None:
        super().__init__(_ERROR_MESSAGE)


def run_request_more_budget_diagnostic(
    manifest: ReviewedEvaluationManifest | None = None,
    *,
    recorded_on: date | None = None,
) -> RequestMoreBudgetReport:
    """Execute exactly two fake cases with tracing disabled, regardless of opt-in flags."""
    with tracing_context(enabled=False):
        resolved = manifest if manifest is not None else build_reviewed_manifest()
        resolved = ReviewedEvaluationManifest.model_validate(resolved.model_dump())
        by_id = {case.scenario.scenario_id: case.scenario for case in resolved.source_draft.cases}
        cases: list[GraphBudgetCase] = []
        for scenario_id in SCENARIO_IDS:
            scenario = by_id[scenario_id]
            observations: list[GraphPortInvocationCounts] = []
            raw_output = fake_end_to_end_target(
                evaluation_dataset_inputs(scenario), port_usage_observer=observations.append
            )
            output = GraphTargetOutput.model_validate(raw_output)
            if (
                output.target is not EvaluationTargetKind.GRAPH_FAKE
                or output.scenario_id != scenario_id
                or len(observations) != 1
            ):
                raise RequestMoreBudgetDiagnosticError()
            counts = GraphPortInvocationCounts.model_validate(observations[0].model_dump())
            if output.measurements.port_invocations != counts.total:
                raise RequestMoreBudgetDiagnosticError()
            outcome = expected_behavior(raw_output, evaluation_dataset_reference_outputs(scenario))
            if outcome.score is not True:
                raise RequestMoreBudgetDiagnosticError()
            cases.append(
                GraphBudgetCase(
                    scenario_id=scenario_id,
                    port_invocations=counts,
                    total_port_invocations=counts.total,
                    planning_passes=output.execution_log.count("plan_supervisor_searches"),
                    review_status=output.review_status,
                    candidate_actions=tuple(item.action for item in output.candidate_reviews),
                    interrupted=output.interrupted,
                    expected_behavior_passed=True,
                    whole_case_budget_passed=(
                        counts.total <= RuntimeBudget().graph_port_invocations
                    ),
                )
            )
        first, second = cases
        delta = GraphPortInvocationDelta.model_validate(
            {
                name: getattr(second.port_invocations, name) - getattr(first.port_invocations, name)
                for name in GraphPortInvocationCounts.model_fields
            }
        )
        return RequestMoreBudgetReport(
            dataset_name=resolved.dataset_name,
            reviewed_version=resolved.reviewed_version,
            content_digest=resolved.content_digest,
            source_draft_digest=resolved.source_draft_digest,
            recorded_on=recorded_on if recorded_on is not None else datetime.now(UTC).date(),
            cases=(first, second),
            additional_port_invocations=delta,
            additional_total_port_invocations=delta.total,
            whole_case_budget_passed=all(item.whole_case_budget_passed for item in cases),
        )


def render_request_more_budget_report(report: RequestMoreBudgetReport) -> str:
    """Render only closed-label metadata, numerical counts, and explicit status values."""
    report = RequestMoreBudgetReport.model_validate(report.model_dump())
    lines = [
        f"Offline call-budget diagnostic: {report.recorded_on.isoformat()} UTC",
        f"Dataset: {report.dataset_name} ({report.reviewed_version})",
        f"Content SHA-256: {report.content_digest}",
        f"Source draft SHA-256: {report.source_draft_digest}",
        "Two independent frozen cases; the delta is not a measured per-round breakdown.",
        f"Unchanged budget: {report.graph_port_invocation_budget} calls per complete graph case.",
    ]
    for case in report.cases:
        lines.append(
            f"{case.scenario_id}: {case.total_port_invocations}/"
            f"{report.graph_port_invocation_budget} calls "
            f"[{'pass' if case.whole_case_budget_passed else 'exceeded'}]; "
            f"planning passes={case.planning_passes}; review status={case.review_status.value}; "
            f"interrupted={case.interrupted}; expected behavior={case.expected_behavior_passed}"
        )
        lines.append(
            "  Ports: "
            + ", ".join(
                f"{name}={value}" for name, value in case.port_invocations.model_dump().items()
            )
        )
        lines.append(
            "  Candidate actions: "
            + (", ".join(action.value for action in case.candidate_actions) or "none")
        )
    lines.append(
        f"Additional calls across independent cases: {report.additional_total_port_invocations}"
    )
    lines.append(
        "  Delta: "
        + ", ".join(
            f"{name}={value}"
            for name, value in report.additional_port_invocations.model_dump().items()
        )
    )
    lines.append("Application port invocations are not HTTP requests, tokens, or monetary cost.")
    lines.append("Fake providers only; no upload, live service, or budget waiver.")
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect offline only; exit 1 for an exceeded budget, 2 for a diagnostic failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)
    try:
        report = run_request_more_budget_diagnostic()
        report = RequestMoreBudgetReport.model_validate(report.model_dump())
        rendered = (
            report.model_dump_json(indent=2)
            if args.format == "json"
            else render_request_more_budget_report(report)
        )
    except Exception:
        print(_ERROR_MESSAGE, file=sys.stderr)
        return 2
    print(rendered)
    return 0 if report.whole_case_budget_passed else 1
