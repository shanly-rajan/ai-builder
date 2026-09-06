"""Usage observations count executed evaluation ports without inventing live billing."""

import pytest

from scholarpath.agents import (
    PlanningInput,
    PlanningModelOutputError,
    StructuredSearchPlanResponse,
)
from scholarpath.domain import EvidenceClaimType
from scholarpath.evaluation.fakes import (
    ScriptedEvidenceModel,
    ScriptedResearchFitModel,
    StaticPlanningModel,
    make_evaluation_evidence_outcomes,
    make_evaluation_planning_response,
)
from scholarpath.evaluation.models import (
    EvidenceVerificationTargetOutput,
    GraphTargetOutput,
    parse_evaluation_target_output,
)
from scholarpath.evaluation.runner import dispatch_evaluation_target
from scholarpath.evaluation.scenarios import (
    evaluation_dataset_inputs,
    evaluation_scenario_by_id,
)
from scholarpath.evaluation.targets import (
    EvaluationTarget,
    evidence_verification_target,
    fake_end_to_end_target,
    live_end_to_end_target,
    make_evidence_verification_target,
    make_research_fit_target,
    make_search_planning_target,
)
from scholarpath.graph import (
    ScholarPathState,
    build_walking_skeleton_fixtures,
    create_initial_state,
)


def _inputs(scenario_id: str) -> dict[str, object]:
    return evaluation_dataset_inputs(evaluation_scenario_by_id(scenario_id))


@pytest.mark.parametrize(
    ("scenario_id", "expected_calls"),
    (
        ("planning-source-coverage", 1),
        ("strong-research-alignment", 1),
        ("superficial-keyword-poor-fit", 1),
        ("availability-not-stated", 1),
        ("conflicting-institutional-affiliation", 2),
    ),
)
def test_component_usage_counts_actual_model_invocations(
    scenario_id: str, expected_calls: int
) -> None:
    output = parse_evaluation_target_output(dispatch_evaluation_target(_inputs(scenario_id)))

    assert output.measurements.port_invocations == expected_calls


@pytest.mark.parametrize(
    ("scenario_id", "expected_calls"),
    (
        ("duplicate-supervisor-multiple-queries", 38),
        ("you-timeout-tavily-fallback", 31),
        ("evidence-extraction-failure", 36),
        ("independent-reviewer-disagreement", 38),
        ("candidate-rejects-highly-theoretical", 39),
        ("approval-required-before-persistence", 38),
    ),
)
def test_graph_usage_includes_model_tool_and_memory_ports(
    scenario_id: str, expected_calls: int
) -> None:
    output = GraphTargetOutput.model_validate(fake_end_to_end_target(_inputs(scenario_id)))

    assert output.measurements.port_invocations == expected_calls


def test_timeout_calls_count_even_when_the_provider_returns_no_results() -> None:
    output = GraphTargetOutput.model_validate(
        fake_end_to_end_target(_inputs("you-timeout-tavily-fallback"))
    )

    assert len(output.search_attempts) == 5
    assert sum(item.error_category is not None for item in output.search_attempts) == 2
    assert output.measurements.port_invocations == 31


def test_failed_extraction_and_alternate_search_remain_counted() -> None:
    output = GraphTargetOutput.model_validate(
        fake_end_to_end_target(_inputs("evidence-extraction-failure"))
    )

    assert len(output.search_attempts) == 4
    # 4 discovery + 1 alternate search + 8 extraction + 1 planning + 7 evidence
    # + 7 fit + 7 review + 1 memory read, including the failed page extraction.
    assert output.measurements.port_invocations == 36


def test_component_measurement_includes_bounded_output_retry() -> None:
    model = StaticPlanningModel(
        (
            PlanningModelOutputError("Synthetic malformed output."),
            make_evaluation_planning_response(),
        )
    )
    target = make_search_planning_target(model)

    output = parse_evaluation_target_output(target(_inputs("planning-source-coverage")))

    assert len(model.inputs) == 2
    assert output.measurements.port_invocations == 2


def test_reused_component_adapters_report_each_call_delta() -> None:
    _, evidence_outcomes = make_evaluation_evidence_outcomes()
    targets: tuple[tuple[EvaluationTarget, str], ...] = (
        (make_search_planning_target(StaticPlanningModel()), "planning-source-coverage"),
        (
            make_evidence_verification_target(ScriptedEvidenceModel(evidence_outcomes)),
            "availability-not-stated",
        ),
        (make_research_fit_target(ScriptedResearchFitModel()), "strong-research-alignment"),
    )

    for target, scenario_id in targets:
        first = parse_evaluation_target_output(target(_inputs(scenario_id)))
        second = parse_evaluation_target_output(target(_inputs(scenario_id)))

        assert first.measurements.port_invocations == 1
        assert second.measurements.port_invocations == 1


class UninstrumentedPlanningModel:
    """A valid injected port whose internal usage is deliberately not exposed."""

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        del planning_input
        return make_evaluation_planning_response()


def test_custom_model_without_usage_observations_reports_unknown() -> None:
    target = make_search_planning_target(UninstrumentedPlanningModel())

    output = parse_evaluation_target_output(target(_inputs("planning-source-coverage")))

    assert output.measurements.port_invocations is None


def test_live_target_does_not_infer_total_port_calls_from_graph_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHOLARPATH_RUN_LIVE_E2E_EVALS", "true")

    def fake_graph(*args: object, **kwargs: object) -> ScholarPathState:
        del args, kwargs
        return create_initial_state(build_walking_skeleton_fixtures().candidate_profile)

    monkeypatch.setattr("scholarpath.evaluation.targets.run_scholarpath_graph", fake_graph)

    output = GraphTargetOutput.model_validate(
        live_end_to_end_target(_inputs("approval-required-before-persistence"))
    )

    assert output.measurements.port_invocations is None


def test_affiliation_conflict_projection_retains_linked_evidence() -> None:
    output = EvidenceVerificationTargetOutput.model_validate(
        evidence_verification_target(_inputs("conflicting-institutional-affiliation"))
    )
    record = output.verification_records[0]
    affiliations = [
        claim
        for claim in record.evidence
        if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
    ]

    assert len(affiliations) == 2
    assert affiliations[0].conflicting_evidence_ids == (affiliations[1].evidence_id,)
    assert affiliations[1].conflicting_evidence_ids == (affiliations[0].evidence_id,)
