"""Unit tests for the versioned synthetic ScholarPath evaluation dataset."""

import json

import pytest
from pydantic import ValidationError

from scholarpath.domain import AvailabilityStatus
from scholarpath.evaluation.models import (
    CandidateReviewOutcome,
    EvaluationScenario,
    EvaluationTargetKind,
)
from scholarpath.evaluation.scenarios import (
    EVALUATION_DATASET_NAME,
    EVALUATION_SCENARIO_VERSION,
    EVALUATION_SCENARIOS,
    build_evaluation_scenarios,
    evaluation_dataset_inputs,
    evaluation_dataset_reference_outputs,
    evaluation_scenario_by_id,
)
from scholarpath.evaluation.targets import (
    evidence_verification_target,
    fake_end_to_end_target,
    live_end_to_end_target,
    research_fit_target,
    search_planning_target,
)

EXPECTED_SCENARIO_TITLES = {
    "Strong research alignment",
    "Superficial keyword overlap with poor actual fit",
    "Supervisor availability is not stated",
    "Conflicting institutional affiliation",
    "Duplicate Supervisor discovered through multiple queries",
    "You.com timeout requiring Tavily fallback",
    "Evidence extraction failure",
    "Independent reviewer disagreement",
    "Candidate rejects highly theoretical research",
    "Candidate approval required before shortlist persistence",
    "Search planning source coverage",
}

EXPECTED_SCENARIO_IDS = {
    "strong-research-alignment",
    "superficial-keyword-poor-fit",
    "availability-not-stated",
    "conflicting-institutional-affiliation",
    "duplicate-supervisor-multiple-queries",
    "you-timeout-tavily-fallback",
    "evidence-extraction-failure",
    "independent-reviewer-disagreement",
    "candidate-rejects-highly-theoretical",
    "approval-required-before-persistence",
    "planning-source-coverage",
}


def test_dataset_contains_the_ten_required_scenarios_plus_planning_coverage() -> None:
    scenarios = build_evaluation_scenarios()

    assert len(scenarios) == 11
    assert {scenario.scenario_id for scenario in scenarios} == EXPECTED_SCENARIO_IDS
    assert {scenario.title for scenario in scenarios} == EXPECTED_SCENARIO_TITLES
    assert scenarios == EVALUATION_SCENARIOS
    assert EVALUATION_DATASET_NAME == "scholarpath-m12-regression-v1"
    assert EVALUATION_SCENARIO_VERSION == "m12-scenarios-v1"


def test_scenario_identifiers_tags_and_splits_are_unique_and_stable() -> None:
    scenario_ids = [scenario.scenario_id for scenario in EVALUATION_SCENARIOS]

    assert len(scenario_ids) == len(set(scenario_ids))
    for scenario in EVALUATION_SCENARIOS:
        assert scenario.splits
        assert len(scenario.splits) == len(set(scenario.splits))
        assert len(scenario.tags) == len(set(scenario.tags))
        assert "application:scholarpath" in scenario.tags
        assert f"scenario-version:{EVALUATION_SCENARIO_VERSION}" in scenario.tags


def test_scenario_catalog_covers_all_offline_targets_and_one_guarded_live_split() -> None:
    represented_targets = {scenario.target for scenario in EVALUATION_SCENARIOS}
    represented_splits = {split for scenario in EVALUATION_SCENARIOS for split in scenario.splits}

    assert represented_targets == {
        EvaluationTargetKind.SEARCH_PLANNING,
        EvaluationTargetKind.EVIDENCE_VERIFICATION,
        EvaluationTargetKind.RESEARCH_FIT,
        EvaluationTargetKind.GRAPH_FAKE,
    }
    assert set(EvaluationTargetKind) == {
        *represented_targets,
        EvaluationTargetKind.GRAPH_LIVE,
    }
    assert {"planning", "evidence-verification", "research-fit", "graph-fake"} <= (
        represented_splits
    )
    assert "graph-live" in represented_splits


def test_scenario_expectations_encode_the_requested_safety_and_route_outcomes() -> None:
    availability = evaluation_scenario_by_id("availability-not-stated")
    duplicate = evaluation_scenario_by_id("duplicate-supervisor-multiple-queries")
    fallback = evaluation_scenario_by_id("you-timeout-tavily-fallback")
    rejection = evaluation_scenario_by_id("candidate-rejects-highly-theoretical")
    approval = evaluation_scenario_by_id("approval-required-before-persistence")

    assert availability.expected.expected_availability_status is AvailabilityStatus.NOT_STATED
    assert duplicate.expected.maximum_duplicate_supervisor_rate == 0.0
    assert duplicate.expected.minimum_multi_query_provenance_count >= 1
    assert fallback.expected.expected_fallback_search_used is True
    assert fallback.expected.minimum_you_attempts >= 2
    assert fallback.expected.minimum_tavily_attempts >= 1
    assert rejection.expected.expected_review_outcome is CandidateReviewOutcome.REJECT
    assert rejection.expected.expected_shortlisted_supervisor_ids == ()
    assert approval.expected.expected_review_outcome is CandidateReviewOutcome.AWAITING_REVIEW
    assert approval.expected.expected_interrupted is True
    assert approval.expected.expected_shortlisted_supervisor_ids == ()


@pytest.mark.parametrize("scenario", EVALUATION_SCENARIOS, ids=lambda item: item.scenario_id)
def test_every_scenario_round_trips_and_has_json_safe_dataset_envelopes(
    scenario: EvaluationScenario,
) -> None:
    restored = EvaluationScenario.model_validate_json(scenario.model_dump_json())
    inputs = evaluation_dataset_inputs(scenario)
    references = evaluation_dataset_reference_outputs(scenario)

    assert restored == scenario
    json.dumps(inputs)
    json.dumps(references)
    assert set(inputs) == {"scenario"}
    assert set(references) == {"expected"}
    raw_scenario = inputs["scenario"]
    assert isinstance(raw_scenario, dict)
    assert "expected" not in raw_scenario
    assert "candidate_id" not in raw_scenario
    assert "proposed_research_statement" not in raw_scenario


def test_dataset_inputs_never_contain_candidate_identity_secrets_or_full_pages() -> None:
    serialized = json.dumps(
        [evaluation_dataset_inputs(scenario) for scenario in EVALUATION_SCENARIOS]
    ).casefold()

    for forbidden in (
        "candidate_id",
        "candidate_name",
        "candidate_email",
        "proposed_research_statement",
        "api_key",
        "provider_secret",
        "full_page_content",
        "thread_id",
    ):
        assert forbidden not in serialized


def test_unknown_scenario_and_duplicate_labels_are_rejected() -> None:
    with pytest.raises(ValueError, match="Unknown ScholarPath evaluation scenario"):
        evaluation_scenario_by_id("not-an-evaluation-scenario")

    original = EVALUATION_SCENARIOS[0].model_dump(mode="python")
    original["splits"] = ("research-fit", "RESEARCH-FIT")
    with pytest.raises(ValidationError, match="labels must be unique"):
        EvaluationScenario.model_validate(original)


@pytest.mark.parametrize("scenario", EVALUATION_SCENARIOS, ids=lambda item: item.scenario_id)
def test_every_offline_scenario_executes_through_its_typed_fake_target(
    scenario: EvaluationScenario,
) -> None:
    targets = {
        EvaluationTargetKind.SEARCH_PLANNING: search_planning_target,
        EvaluationTargetKind.EVIDENCE_VERIFICATION: evidence_verification_target,
        EvaluationTargetKind.RESEARCH_FIT: research_fit_target,
        EvaluationTargetKind.GRAPH_FAKE: fake_end_to_end_target,
    }

    output = targets[scenario.target](evaluation_dataset_inputs(scenario))

    assert output["target"] == scenario.target.value
    assert output["scenario_id"] == scenario.scenario_id
    serialized = json.dumps(output).casefold()
    for forbidden in (
        "candidate_id",
        "candidate_email",
        "proposed_research_statement",
        "api_key",
        "full_page_content",
        "thread_id",
    ):
        assert forbidden not in serialized


def test_live_end_to_end_target_requires_a_separate_explicit_opt_in(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SCHOLARPATH_RUN_LIVE_E2E_EVALS", "false")
    scenario = evaluation_scenario_by_id("approval-required-before-persistence")

    with pytest.raises(RuntimeError, match="Live end-to-end evaluation is disabled"):
        live_end_to_end_target(evaluation_dataset_inputs(scenario))
