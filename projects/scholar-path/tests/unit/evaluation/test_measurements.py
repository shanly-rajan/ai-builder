"""Deterministic runtime summaries distinguish real measurements from missing data."""

from __future__ import annotations

from typing import Literal

import pytest
from pydantic import ValidationError

from scholarpath.evaluation.measurements import (
    RuntimeBudget,
    RuntimeCase,
    RuntimeMeasurement,
    TargetMeasurements,
    format_runtime_summary,
    runtime_budgets_passed,
    summarize_runtime,
    target_measurements,
)

type TargetFamily = Literal[
    "search_planning", "evidence_verification", "research_fit", "graph_fake", "graph_live"
]


def _case(
    index: int,
    seconds: float | None,
    calls: int | None,
    *,
    target: TargetFamily = "search_planning",
) -> RuntimeCase:
    return RuntimeCase(
        scenario_id=f"case-{index}",
        target=target,
        measurement=RuntimeMeasurement(target_seconds=seconds, port_invocations=calls),
    )


def test_median_and_nearest_rank_p95_for_twenty_values() -> None:
    cases = tuple(_case(index, float(index), index) for index in reversed(range(1, 21)))
    (summary,) = summarize_runtime(
        cases, RuntimeBudget(fake_target_p95_seconds=19, component_port_invocations=20)
    )

    assert summary.case_count == summary.latency_sample_count == 20
    assert summary.median_target_seconds == 10.5
    assert summary.p95_target_seconds == 19.0
    assert summary.maximum_port_invocations == 20
    assert summary.latency_budget_passed is True
    assert summary.invocation_budget_passed is True


@pytest.mark.parametrize(
    ("durations", "expected_median", "expected_p95"),
    [((2.0,), 2.0, 2.0), ((1.0, 2.0), 1.5, 2.0), ((1.0, 8.0, 3.0), 3.0, 8.0)],
)
def test_small_sample_percentiles_are_deterministic(
    durations: tuple[float, ...], expected_median: float, expected_p95: float
) -> None:
    (summary,) = summarize_runtime(
        tuple(_case(index, duration, 1) for index, duration in enumerate(durations)),
        RuntimeBudget(),
    )

    assert summary.median_target_seconds == expected_median
    assert summary.p95_target_seconds == expected_p95


def test_target_families_are_aggregated_separately_with_appropriate_call_budgets() -> None:
    summaries = summarize_runtime(
        (
            _case(1, 1, 1),
            _case(2, 9, 2, target="research_fit"),
            _case(3, 3, 30, target="graph_fake"),
            _case(4, 3, 2),
        ),
        RuntimeBudget(),
    )
    by_target = {summary.target: summary for summary in summaries}

    assert [summary.target for summary in summaries] == sorted(by_target)
    assert by_target["search_planning"].case_count == 2
    assert by_target["search_planning"].median_target_seconds == 2.0
    assert by_target["search_planning"].invocation_budget == 2
    assert by_target["graph_fake"].invocation_budget == 40
    assert by_target["graph_fake"].maximum_port_invocations == 30
    assert by_target["research_fit"].latency_budget_passed is False
    assert runtime_budgets_passed(summaries) is False


def test_missing_observations_are_unmeasured_never_zero_or_a_pass() -> None:
    summaries = summarize_runtime((_case(1, None, None),), RuntimeBudget())
    (summary,) = summaries

    assert summary.case_count == 1
    assert summary.latency_sample_count == summary.invocation_sample_count == 0
    assert summary.median_target_seconds is None
    assert summary.p95_target_seconds is None
    assert summary.maximum_port_invocations is None
    assert summary.latency_budget_passed is None
    assert summary.invocation_budget_passed is None
    assert runtime_budgets_passed(summaries) is None
    rendered = format_runtime_summary(summaries)
    assert "median=unmeasured" in rendered
    assert "max=unmeasured" in rendered
    assert "[unknown]" in rendered


def test_partial_observations_do_not_claim_a_complete_cohort_pass() -> None:
    summaries = summarize_runtime((_case(1, 1, None), _case(2, None, 1)), RuntimeBudget())
    (summary,) = summaries

    assert summary.case_count == 2
    assert summary.latency_sample_count == summary.invocation_sample_count == 1
    assert summary.median_target_seconds == summary.p95_target_seconds == 1
    assert summary.maximum_port_invocations == 1
    assert summary.latency_budget_passed is None
    assert summary.invocation_budget_passed is None
    assert runtime_budgets_passed(summaries) is None


def test_measured_zero_values_are_real_observations_that_can_pass() -> None:
    summaries = summarize_runtime((_case(1, 0, 0),), RuntimeBudget())
    (summary,) = summaries

    assert summary.latency_sample_count == summary.invocation_sample_count == 1
    assert summary.median_target_seconds == summary.p95_target_seconds == 0.0
    assert summary.maximum_port_invocations == 0
    assert runtime_budgets_passed(summaries) is True
    assert "median=0.000s" in format_runtime_summary(summaries)


def test_live_measurements_are_not_judged_against_fake_cohort_budgets() -> None:
    summaries = summarize_runtime((_case(1, 200, 100, target="graph_live"),), RuntimeBudget())
    (summary,) = summaries

    assert summary.p95_target_seconds == 200
    assert summary.maximum_port_invocations == 100
    assert summary.latency_budget_seconds is None
    assert summary.invocation_budget is None
    assert summary.latency_budget_passed is None
    assert summary.invocation_budget_passed is None
    assert runtime_budgets_passed(summaries) is None


def test_exceeded_budget_wins_over_another_familys_unknown_result() -> None:
    summaries = summarize_runtime(
        (_case(1, 6, 1), _case(2, None, None, target="graph_live")), RuntimeBudget()
    )

    assert runtime_budgets_passed(summaries) is False


def test_empty_cohort_has_no_runtime_decision() -> None:
    assert summarize_runtime((), RuntimeBudget()) == ()
    assert runtime_budgets_passed(()) is None


@pytest.mark.parametrize("field", ("target_seconds", "evaluator_seconds"))
@pytest.mark.parametrize("value", (-0.1, float("inf"), float("-inf"), float("nan")))
def test_invalid_duration_is_rejected(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        RuntimeMeasurement.model_validate({field: value})


@pytest.mark.parametrize("value", (0.0, -1.0, float("inf"), float("-inf"), float("nan")))
def test_invalid_latency_budget_is_rejected(value: float) -> None:
    with pytest.raises(ValidationError):
        RuntimeBudget(fake_target_p95_seconds=value)


@pytest.mark.parametrize("field", ("component_port_invocations", "graph_port_invocations"))
@pytest.mark.parametrize("value", (0, -1, 1.5))
def test_invalid_invocation_budget_is_rejected(field: str, value: int | float) -> None:
    with pytest.raises(ValidationError):
        RuntimeBudget.model_validate({field: value})


@pytest.mark.parametrize("value", ("5", 1.0, True, -1, float("nan"), float("inf"), {}, []))
def test_counter_parser_rejects_invalid_or_coerced_values(value: object) -> None:
    result = target_measurements({"measurements": {"port_invocations": value}})

    assert result.port_invocations is None


@pytest.mark.parametrize("outputs", (None, [], "2 calls", {}, {"measurements": None}))
def test_counter_parser_does_not_infer_missing_measurements(outputs: object) -> None:
    assert target_measurements(outputs).port_invocations is None


def test_counter_parser_accepts_only_explicit_typed_measurements() -> None:
    explicit = TargetMeasurements(port_invocations=0)

    assert target_measurements({"measurements": explicit}) is explicit
    assert target_measurements({"measurements": {"port_invocations": 5}}).port_invocations == 5
    assert target_measurements({"trace_children": 5, "comment": "5 calls"}).port_invocations is None


def test_runtime_reporting_excludes_payloads_scenario_identity_and_unmeasured_cost() -> None:
    private = "person@example.test secret-token private research statement"
    measured = target_measurements(
        {"measurements": {"port_invocations": 2}, "metadata": private, "output": private}
    )
    cases = (
        RuntimeCase(
            scenario_id=private,
            target="search_planning",
            measurement=RuntimeMeasurement(
                target_seconds=0.25,
                evaluator_seconds=1000,
                port_invocations=measured.port_invocations,
            ),
        ),
    )
    summaries = summarize_runtime(cases, RuntimeBudget())
    rendered = format_runtime_summary(summaries)

    assert "p95=0.250s" in rendered
    assert "1000" not in rendered
    assert private not in rendered
    assert private not in summaries[0].model_dump_json()
    assert "Tokens and monetary cost: unmeasured" in rendered
    assert "port invocations are not billed requests" in rendered
    assert (
        target_measurements(
            {"measurements": {"port_invocations": 2, "secret": private}}
        ).port_invocations
        is None
    )


def test_private_target_label_is_not_an_accepted_runtime_family() -> None:
    with pytest.raises(ValidationError):
        RuntimeCase.model_validate(
            {"scenario_id": "case-1", "target": "private@example.test", "measurement": {}}
        )
