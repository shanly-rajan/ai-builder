"""Privacy-safe runtime measurements; fake invocations are not billable API calls."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping, Sequence
from math import ceil
from statistics import median
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

type RuntimeTargetKind = Literal[
    "search_planning", "evidence_verification", "research_fit", "graph_fake", "graph_live"
]


class TargetMeasurements(BaseModel):
    """Count observed application port invocations, including failed attempts."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    port_invocations: int | None = Field(default=None, ge=0)


class RuntimeMeasurement(BaseModel):
    """Separate target execution from evaluation overhead; missing is not zero."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    evaluator_seconds: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    port_invocations: int | None = Field(default=None, ge=0)


class RuntimeBudget(BaseModel):
    """Provisional fake-cohort budgets, never a live performance or cost claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    fake_target_p95_seconds: float = Field(default=5.0, gt=0, allow_inf_nan=False)
    component_port_invocations: int = Field(default=2, ge=1)
    graph_port_invocations: int = Field(default=40, ge=1)


class RuntimeCase(BaseModel):
    """Public case identity plus numeric observations only."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    scenario_id: str
    target: RuntimeTargetKind
    measurement: RuntimeMeasurement


class RuntimeSummary(BaseModel):
    """One target family; incomplete telemetry cannot pass a runtime budget."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    target: RuntimeTargetKind
    case_count: int
    latency_sample_count: int
    median_target_seconds: float | None
    p95_target_seconds: float | None
    latency_budget_seconds: float | None
    latency_budget_passed: bool | None
    invocation_sample_count: int
    maximum_port_invocations: int | None
    invocation_budget: int | None
    invocation_budget_passed: bool | None


def target_measurements(outputs: object) -> TargetMeasurements:
    """Accept only explicit typed counters; never inspect payload text or SDK children."""
    if not isinstance(outputs, Mapping):
        return TargetMeasurements()
    raw = outputs.get("measurements")
    if isinstance(raw, TargetMeasurements):
        return raw
    try:
        return TargetMeasurements.model_validate(raw)
    except ValidationError:
        return TargetMeasurements()


def summarize_runtime(
    cases: Sequence[RuntimeCase], budget: RuntimeBudget
) -> tuple[RuntimeSummary, ...]:
    """Aggregate by family using nearest-rank p95, without excluding failed targets."""
    families: dict[RuntimeTargetKind, list[RuntimeMeasurement]] = defaultdict(list)
    for case in cases:
        families[case.target].append(case.measurement)
    summaries: list[RuntimeSummary] = []
    for target, measurements in sorted(families.items()):
        durations = sorted(
            item.target_seconds for item in measurements if item.target_seconds is not None
        )
        invocations = [
            item.port_invocations for item in measurements if item.port_invocations is not None
        ]
        p95 = durations[ceil(0.95 * len(durations)) - 1] if durations else None
        maximum = max(invocations) if invocations else None
        # These budgets are calibrated only for the existing fake/component cohort.
        latency_limit = None if target == "graph_live" else budget.fake_target_p95_seconds
        invocation_limit = (
            None
            if target == "graph_live"
            else budget.graph_port_invocations
            if target == "graph_fake"
            else budget.component_port_invocations
        )
        summaries.append(
            RuntimeSummary(
                target=target,
                case_count=len(measurements),
                latency_sample_count=len(durations),
                median_target_seconds=median(durations) if durations else None,
                p95_target_seconds=p95,
                latency_budget_seconds=latency_limit,
                latency_budget_passed=(
                    p95 <= latency_limit
                    if p95 is not None
                    and latency_limit is not None
                    and len(durations) == len(measurements)
                    else None
                ),
                invocation_sample_count=len(invocations),
                maximum_port_invocations=maximum,
                invocation_budget=invocation_limit,
                invocation_budget_passed=(
                    maximum <= invocation_limit
                    if maximum is not None
                    and invocation_limit is not None
                    and len(invocations) == len(measurements)
                    else None
                ),
            )
        )
    return tuple(summaries)


def runtime_budgets_passed(summaries: Sequence[RuntimeSummary]) -> bool | None:
    """Return unknown for missing observations, false for any exceeded budget."""
    decisions = [
        decision
        for summary in summaries
        for decision in (summary.latency_budget_passed, summary.invocation_budget_passed)
    ]
    if False in decisions:
        return False
    if not decisions or None in decisions:
        return None
    return True


def format_runtime_summary(summaries: Sequence[RuntimeSummary]) -> str:
    """Format only numerical measurements and controlled target labels."""

    def number(value: int | float | None) -> str:
        return "unmeasured" if value is None else f"{value:.3f}"

    def decision(value: bool | None) -> str:
        return "unknown" if value is None else "pass" if value else "exceeded"

    lines = ["Runtime measurements (target time excludes evaluator time):"]
    for summary in summaries:
        lines.extend(
            (
                f"- {summary.target}: n={summary.case_count}; "
                f"latency samples={summary.latency_sample_count}; "
                f"median={number(summary.median_target_seconds)}s; "
                f"p95={number(summary.p95_target_seconds)}s; "
                f"budget={number(summary.latency_budget_seconds)}s "
                f"[{decision(summary.latency_budget_passed)}]",
                f"  Application port invocations: samples={summary.invocation_sample_count}; "
                f"max={number(summary.maximum_port_invocations)}; "
                f"budget={number(summary.invocation_budget)} "
                f"[{decision(summary.invocation_budget_passed)}]",
            )
        )
    lines.append("Tokens and monetary cost: unmeasured; port invocations are not billed requests.")
    lines.append("Fake-cohort budgets are diagnostic unless --enforce-runtime-budgets is set.")
    return "\n".join(lines)
