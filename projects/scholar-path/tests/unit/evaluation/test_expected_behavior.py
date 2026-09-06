"""Declared outcome labels catch semantically wrong but structurally valid results."""

from copy import deepcopy
from typing import Any

import pytest
from pydantic import ValidationError

from scholarpath.evaluation.evaluators import expected_behavior, schema_validity
from scholarpath.evaluation.models import EvaluationExpectation, EvaluationTargetKind
from scholarpath.evaluation.runner import dispatch_evaluation_target
from scholarpath.evaluation.scenarios import (
    EVALUATION_SCENARIOS,
    evaluation_dataset_inputs,
    evaluation_dataset_reference_outputs,
    evaluation_scenario_by_id,
)


@pytest.fixture(scope="module")
def examples() -> dict[str, dict[str, Any]]:
    """Capture real fake-tool target projections without making any provider calls."""
    return {
        scenario.scenario_id: dispatch_evaluation_target(evaluation_dataset_inputs(scenario))
        for scenario in EVALUATION_SCENARIOS
    }


def _reference(scenario_id: str) -> dict[str, object]:
    return evaluation_dataset_reference_outputs(evaluation_scenario_by_id(scenario_id))


@pytest.mark.parametrize("scenario", EVALUATION_SCENARIOS, ids=lambda item: item.scenario_id)
def test_each_reviewed_scenario_checks_its_actual_fake_outcome(
    scenario: Any, examples: dict[str, dict[str, Any]]
) -> None:
    result = expected_behavior(examples[scenario.scenario_id], _reference(scenario.scenario_id))
    assert result.score is True, result.comment


@pytest.mark.parametrize(
    "reference",
    [
        None,
        {},
        {"expected": {}},
        {"expected": None},
        {"expected": []},
        {"expected": {"unknown_label": True}},
        {"expected": {"expected_interrupted": "false"}},
        {"expected": {"minimum_research_fit_score": True}},
        {"expected": {"maximum_duplicate_supervisor_rate": float("nan")}},
        {"expected": {"expected_supervisor_ids": ["same", "same"]}},
    ],
)
def test_missing_malformed_or_empty_reference_cannot_pass(
    reference: Any, examples: dict[str, dict[str, Any]]
) -> None:
    result = expected_behavior(examples["strong-research-alignment"], reference)
    assert result.score is False
    assert result.comment == "Declared outcome labels are missing or invalid."


@pytest.mark.parametrize("scenario", EVALUATION_SCENARIOS, ids=lambda item: item.scenario_id)
def test_empty_target_or_empty_graph_cannot_pass_a_positive_labeled_outcome(
    scenario: Any, examples: dict[str, dict[str, Any]]
) -> None:
    assert expected_behavior({}, _reference(scenario.scenario_id)).score is False
    if scenario.target is not EvaluationTargetKind.GRAPH_FAKE:
        return
    output = deepcopy(examples[scenario.scenario_id])
    for field, value in output.items():
        if isinstance(value, list):
            output[field] = []
    output["raw_search_result_count"] = 0
    output["plausible_profile_count"] = 0
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario.scenario_id)).score is False


@pytest.mark.parametrize(
    "scenario_id",
    [
        "strong-research-alignment",
        "availability-not-stated",
        "duplicate-supervisor-multiple-queries",
    ],
)
def test_expected_supervisor_identifiers_are_consumed_for_every_result_family(
    scenario_id: str, examples: dict[str, dict[str, Any]]
) -> None:
    reference = _reference(scenario_id)
    expected = EvaluationExpectation.model_validate(reference["expected"])
    wrong = expected.model_copy(update={"expected_supervisor_ids": ("unrelated-supervisor",)})
    assert (
        expected_behavior(examples[scenario_id], {"expected": wrong.model_dump(mode="json")}).score
        is False
    )


@pytest.mark.parametrize("mutation", ["status", "concerns", "links", "evidence"])
def test_affiliation_conflict_must_remain_explicit_and_linked_to_retained_sources(
    mutation: str, examples: dict[str, dict[str, Any]]
) -> None:
    scenario_id = "conflicting-institutional-affiliation"
    output = deepcopy(examples[scenario_id])
    record = output["verification_records"][0]
    if mutation == "status":
        record["verification_status"] = "verified"
    elif mutation == "concerns":
        record["verification_concerns"] = []
    elif mutation == "links":
        for claim in record["evidence"]:
            claim["conflicting_evidence_ids"] = []
    else:
        record["evidence"] = []
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario_id)).score is False


@pytest.mark.parametrize(
    "mutation",
    ["dropped_partial_record", "invented_completion", "lost_useful_evidence", "lost_missing_gate"],
)
def test_extraction_failure_preserves_partial_record_and_successful_evidence(
    mutation: str, examples: dict[str, dict[str, Any]]
) -> None:
    scenario_id = "evidence-extraction-failure"
    output = deepcopy(examples[scenario_id])
    records = output["verification_records"]
    if mutation == "dropped_partial_record":
        output["verification_records"] = records[1:]
    elif mutation == "invented_completion":
        records[0]["verification_status"] = "verified"
        records[0]["verified_supervisor_present"] = True
    elif mutation == "lost_useful_evidence":
        records[1]["evidence"] = []
    else:
        records[0]["missing_required_evidence"] = []
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario_id)).score is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("review_status", "accepted"),
        ("effective_score", 87),
        ("effective_confidence", "high"),
        ("requires_candidate_attention", False),
    ],
)
def test_disagreement_requires_the_reviewed_score_confidence_and_attention(
    field: str, value: object, examples: dict[str, dict[str, Any]]
) -> None:
    scenario_id = "independent-reviewer-disagreement"
    output = deepcopy(examples[scenario_id])
    output["independent_reviews"][0][field] = value
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario_id)).score is False


def test_disagreement_also_checks_the_updated_proposal_order(
    examples: dict[str, dict[str, Any]],
) -> None:
    scenario_id = "independent-reviewer-disagreement"
    output = deepcopy(examples[scenario_id])
    output["proposed_supervisor_ids"].reverse()
    output["shortlist_recommendations"].reverse()
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario_id)).score is False


def test_missing_independent_review_is_not_an_accepted_disagreement(
    examples: dict[str, dict[str, Any]],
) -> None:
    scenario_id = "independent-reviewer-disagreement"
    output = deepcopy(examples[scenario_id])
    output["independent_reviews"] = []
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario_id)).score is False


def test_planning_coverage_requires_the_correct_output_family_and_sources(
    examples: dict[str, dict[str, Any]],
) -> None:
    scenario_id = "planning-source-coverage"
    reference = _reference(scenario_id)
    assert expected_behavior(examples["strong-research-alignment"], reference).score is False
    output = deepcopy(examples[scenario_id])
    for query in output["search_plan"]["search_queries"]:
        query["target_source_types"] = ["official_university_profile"]
    assert expected_behavior(output, reference).score is False


def test_labels_work_after_renaming_the_scenario(examples: dict[str, dict[str, Any]]) -> None:
    output = deepcopy(examples["independent-reviewer-disagreement"])
    output["scenario_id"] = "reviewer-example-renamed"
    assert expected_behavior(output, _reference("independent-reviewer-disagreement")).score is True


@pytest.mark.parametrize(
    "observed,expected",
    [
        ("strong-research-alignment", "superficial-keyword-poor-fit"),
        ("superficial-keyword-poor-fit", "strong-research-alignment"),
    ],
)
def test_valid_fit_schema_does_not_override_the_labeled_fit_band(
    observed: str, expected: str, examples: dict[str, dict[str, Any]]
) -> None:
    assert schema_validity(examples[observed]).score is True
    assert expected_behavior(examples[observed], _reference(expected)).score is False


@pytest.mark.parametrize("mutation", ["no_fallback", "no_retry", "no_attempts"])
def test_fallback_success_requires_the_expected_attempt_route(
    mutation: str, examples: dict[str, dict[str, Any]]
) -> None:
    scenario_id = "you-timeout-tavily-fallback"
    output = deepcopy(examples[scenario_id])
    if mutation == "no_fallback":
        output["fallback_search_used"] = False
    elif mutation == "no_retry":
        output["search_attempts"] = [
            attempt for attempt in output["search_attempts"] if attempt["attempt_number"] == 1
        ]
    else:
        output["search_attempts"] = []
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario_id)).score is False


@pytest.mark.parametrize("mutation", ["lost_action", "lost_rejection", "reoffered_supervisor"])
def test_rejection_outcome_requires_feedback_and_an_excluding_proposal(
    mutation: str, examples: dict[str, dict[str, Any]]
) -> None:
    scenario_id = "candidate-rejects-highly-theoretical"
    output = deepcopy(examples[scenario_id])
    if mutation == "lost_action":
        output["candidate_reviews"] = []
    elif mutation == "lost_rejection":
        output["rejected_supervisor_ids"] = []
    else:
        original = examples["approval-required-before-persistence"]
        output["proposed_supervisor_ids"][0] = original["proposed_supervisor_ids"][0]
        output["shortlist_recommendations"][0] = original["shortlist_recommendations"][0]
    assert schema_validity(output).score is True
    assert expected_behavior(output, _reference(scenario_id)).score is False


def test_declared_empty_graph_projection_cannot_stand_in_for_a_plan(
    examples: dict[str, dict[str, Any]],
) -> None:
    assert (
        expected_behavior(
            examples["planning-source-coverage"], {"expected": {"expected_supervisor_ids": []}}
        ).score
        is False
    )


def test_explicit_empty_shortlist_label_is_enforced_even_with_approval(
    examples: dict[str, dict[str, Any]],
) -> None:
    output = deepcopy(examples["approval-required-before-persistence"])
    supervisor_id = output["proposed_supervisor_ids"][0]
    output["interrupted"] = False
    output["shortlisted_supervisor_ids"] = [supervisor_id]
    output["candidate_reviews"] = [{"action": "approve", "supervisor_ids": [supervisor_id]}]
    assert schema_validity(output).score is True
    assert (
        expected_behavior(output, {"expected": {"expected_shortlisted_supervisor_ids": []}}).score
        is False
    )


@pytest.mark.parametrize("scenario", EVALUATION_SCENARIOS, ids=lambda item: item.scenario_id)
def test_reviewed_labels_round_trip_with_distinct_unscoped_and_empty_outcomes(
    scenario: Any,
) -> None:
    expected = scenario.expected
    assert EvaluationExpectation.model_validate_json(expected.model_dump_json()) == expected
    assert EvaluationExpectation().expected_shortlisted_supervisor_ids is None
    assert (
        EvaluationExpectation(
            expected_shortlisted_supervisor_ids=()
        ).expected_shortlisted_supervisor_ids
        == ()
    )


@pytest.mark.parametrize(
    "labels",
    [
        {"minimum_research_fit_score": 90, "maximum_research_fit_score": 20},
        {
            "expected_verification_records": [
                {
                    "supervisor_id": "supervisor-1",
                    "verification_status": "partially_verified",
                    "verified_supervisor_present": True,
                }
            ]
        },
        {
            "expected_verification_records": [
                {
                    "supervisor_id": "supervisor-1",
                    "verification_status": "verified",
                    "verified_supervisor_present": True,
                    "minimum_retained_evidence": 3,
                    "maximum_retained_evidence": 0,
                }
            ]
        },
    ],
)
def test_impossible_outcome_labels_are_rejected(labels: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        EvaluationExpectation.model_validate(labels)
