"""Fixed-example tests for every deterministic ScholarPath evaluator."""

from collections.abc import Callable
from typing import Any

import pytest
from langsmith.evaluation import EvaluationResult

from scholarpath.domain import (
    AvailabilityStatus,
    CandidateReviewAction,
    EvidenceClaimType,
)
from scholarpath.evaluation.evaluators import (
    DETERMINISTIC_EVALUATORS,
    canonical_terminology,
    correct_fallback_route,
    duplicate_supervisor_rate,
    evidence_id_validity,
    human_approval_enforcement,
    no_admission_probability,
    no_unsupported_availability_claim,
    schema_validity,
    score_range_and_component_totals,
    source_url_presence,
)
from scholarpath.evaluation.models import (
    CandidatePreferenceProjection,
    CandidateReviewOutcome,
    CandidateReviewProjection,
    EvaluationExpectation,
    EvaluationTargetKind,
    EvidenceReferenceProjection,
    EvidenceVerificationTargetOutput,
    GraphTargetOutput,
    ResearchFitAssessmentProjection,
    ResearchFitTargetOutput,
    SearchAttemptProjection,
    SearchPlanningTargetOutput,
    SupervisorProvenanceProjection,
    VerificationRecordProjection,
)
from scholarpath.graph import ReviewStatus
from scholarpath.tools import SearchErrorCategory, SearchProvider
from tests.fixtures import (
    make_research_fit_assessment,
    make_search_plan,
    make_verified_supervisor,
)

Evaluator = Callable[
    [dict[str, object], dict[str, object] | None],
    EvaluationResult,
]


def _preferences() -> CandidatePreferenceProjection:
    return CandidatePreferenceProjection(
        research_topics=("enterprise architecture", "responsible AI governance"),
        preferred_regions=("South Africa",),
        preferred_study_modes=("part-time",),
        preferred_research_orientation="applied",
        methodological_interests=("design science",),
        exclusions=("fully residential programmes",),
    )


def _evidence(index: int = 1) -> tuple[EvidenceReferenceProjection, ...]:
    supervisor = make_verified_supervisor(index)
    return tuple(
        EvidenceReferenceProjection(
            evidence_id=claim.evidence_id,
            supervisor_id=claim.supervisor_id,
            claim_type=claim.claim_type,
            claim_summary=claim.claim,
            source_url=claim.source_url,
            directly_supported=claim.directly_supported,
            confidence=claim.confidence,
            availability_status=claim.availability_status,
        )
        for claim in supervisor.evidence
    )


def _verification_record(
    *,
    index: int = 1,
    availability_status: AvailabilityStatus | None = None,
    evidence: tuple[EvidenceReferenceProjection, ...] | None = None,
) -> VerificationRecordProjection:
    supervisor = make_verified_supervisor(index)
    return VerificationRecordProjection(
        supervisor_id=supervisor.supervisor_id,
        verification_status=supervisor.verification_status,
        availability_status=availability_status or supervisor.availability_status,
        evidence=evidence if evidence is not None else _evidence(index),
        verification_concerns=supervisor.verification_concerns,
        missing_required_evidence=(),
        verified_supervisor_present=True,
    )


def _planning_output(*, rationale: str | None = None) -> dict[str, object]:
    plan = make_search_plan(**({"rationale": rationale} if rationale is not None else {}))
    return SearchPlanningTargetOutput(
        target=EvaluationTargetKind.SEARCH_PLANNING,
        scenario_id="planning-fixed-example",
        search_plan=plan,
    ).model_dump(mode="json")


def _fit_output(
    *,
    assessment_data: dict[str, Any] | None = None,
    evidence: tuple[EvidenceReferenceProjection, ...] | None = None,
) -> dict[str, object]:
    assessment = make_research_fit_assessment(1)
    if assessment_data is not None:
        assessment = assessment.__class__.model_validate(assessment_data)
    return ResearchFitTargetOutput(
        target=EvaluationTargetKind.RESEARCH_FIT,
        scenario_id="fit-fixed-example",
        candidate_preferences=_preferences(),
        assessments=(
            ResearchFitAssessmentProjection(
                assessment=assessment,
                evidence=evidence if evidence is not None else _evidence(),
            ),
        ),
    ).model_dump(mode="json")


def _attempt(
    provider: SearchProvider,
    attempt_number: int,
    *,
    error_category: SearchErrorCategory | None = None,
) -> SearchAttemptProjection:
    failed = error_category is not None
    return SearchAttemptProjection(
        provider_used=provider,
        attempt_number=attempt_number,
        result_count=0 if failed else 8,
        plausible_supervisor_count=0 if failed else 6,
        error_category=error_category,
        retryable=failed,
        discovery_round=1,
    )


def _graph_output(
    *,
    interrupted: bool = True,
    fallback_search_used: bool = False,
    search_attempts: tuple[SearchAttemptProjection, ...] = (),
    execution_log: tuple[str, ...] = ("candidate_review_gate",),
    prospective_supervisor_ids: tuple[str, ...] = ("supervisor-001",),
    supervisor_provenance: tuple[SupervisorProvenanceProjection, ...] = (),
    proposed_supervisor_ids: tuple[str, ...] = (),
    shortlisted_supervisor_ids: tuple[str, ...] = (),
    rejected_supervisor_ids: tuple[str, ...] = (),
    candidate_reviews: tuple[CandidateReviewProjection, ...] = (),
) -> dict[str, object]:
    return GraphTargetOutput(
        target=EvaluationTargetKind.GRAPH_FAKE,
        scenario_id="graph-fixed-example",
        candidate_preferences=_preferences(),
        review_status=ReviewStatus.PROPOSED,
        interrupted=interrupted,
        execution_log=execution_log,
        fallback_search_used=fallback_search_used,
        search_attempts=search_attempts,
        raw_search_result_count=8,
        plausible_profile_count=len(prospective_supervisor_ids),
        prospective_supervisor_ids=prospective_supervisor_ids,
        supervisor_provenance=supervisor_provenance,
        verification_records=(),
        assessments=(),
        independent_reviews=(),
        proposed_supervisor_ids=proposed_supervisor_ids,
        shortlist_recommendations=(),
        shortlisted_supervisor_ids=shortlisted_supervisor_ids,
        rejected_supervisor_ids=rejected_supervisor_ids,
        candidate_reviews=candidate_reviews,
        tool_error_codes=(),
    ).model_dump(mode="json")


def _expectation(**overrides: object) -> dict[str, object]:
    return {"expected": EvaluationExpectation.model_validate(overrides).model_dump(mode="json")}


def _assert_passed(result: EvaluationResult) -> None:
    assert result.score is True
    assert result.comment is None


def _assert_failed(result: EvaluationResult) -> None:
    assert result.score is False
    assert result.comment


def test_deterministic_evaluator_registry_is_complete_and_stable() -> None:
    assert tuple(evaluator.__name__ for evaluator in DETERMINISTIC_EVALUATORS) == (
        "schema_validity",
        "canonical_terminology",
        "evidence_id_validity",
        "source_url_presence",
        "score_range_and_component_totals",
        "no_unsupported_availability_claim",
        "no_admission_probability",
        "correct_fallback_route",
        "duplicate_supervisor_rate",
        "human_approval_enforcement",
    )


def test_schema_validity_accepts_typed_output_and_rejects_invalid_output() -> None:
    _assert_passed(schema_validity(_planning_output()))
    _assert_failed(schema_validity({"target": "unknown", "candidate_email": "hidden@example"}))


def test_canonical_terminology_accepts_canonical_text_and_rejects_banned_text() -> None:
    _assert_passed(canonical_terminology(_planning_output()))
    _assert_failed(
        canonical_terminology(
            _planning_output(rationale="Rank each supervisor candidate deterministically.")
        )
    )


def test_evidence_id_validity_accepts_known_ids_and_rejects_unknown_ids() -> None:
    _assert_passed(evidence_id_validity(_fit_output()))

    assessment_data = make_research_fit_assessment(1).model_dump(mode="python")
    replacement_by_id = {
        evidence_id: f"unknown-{evidence_id}"
        for evidence_id in assessment_data["supporting_evidence_ids"]
    }
    assessment_data["supporting_evidence_ids"] = tuple(replacement_by_id.values())
    breakdown = assessment_data["breakdown"]
    for component in breakdown.values():
        component["supporting_evidence_ids"] = tuple(
            replacement_by_id[item] for item in component["supporting_evidence_ids"]
        )

    _assert_failed(evidence_id_validity(_fit_output(assessment_data=assessment_data)))


def test_source_url_presence_accepts_urls_and_rejects_schema_missing_url() -> None:
    output = EvidenceVerificationTargetOutput(
        target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
        scenario_id="source-url-fixed-example",
        verification_records=(_verification_record(),),
    ).model_dump(mode="json")
    _assert_passed(source_url_presence(output))

    broken = dict(output)
    records = [dict(item) for item in output["verification_records"]]
    evidence = [dict(item) for item in records[0]["evidence"]]
    evidence[0].pop("source_url")
    records[0]["evidence"] = evidence
    broken["verification_records"] = records
    _assert_failed(source_url_presence(broken))


def test_score_totals_accept_valid_rubric_and_reject_out_of_expected_range() -> None:
    _assert_passed(
        score_range_and_component_totals(
            _fit_output(),
            _expectation(minimum_research_fit_score=80, maximum_research_fit_score=90),
        )
    )
    _assert_failed(
        score_range_and_component_totals(
            _fit_output(),
            _expectation(minimum_research_fit_score=100),
        )
    )


def test_availability_evaluator_accepts_not_stated_and_rejects_unsupported_status() -> None:
    valid = EvidenceVerificationTargetOutput(
        target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
        scenario_id="availability-fixed-example",
        verification_records=(_verification_record(),),
    ).model_dump(mode="json")
    _assert_passed(
        no_unsupported_availability_claim(
            valid,
            _expectation(expected_availability_status=AvailabilityStatus.NOT_STATED),
        )
    )

    unsupported = EvidenceVerificationTargetOutput(
        target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
        scenario_id="availability-unsupported-example",
        verification_records=(
            _verification_record(
                availability_status=AvailabilityStatus.CONFIRMED_ACCEPTING,
                evidence=tuple(
                    item
                    for item in _evidence()
                    if item.claim_type is not EvidenceClaimType.AVAILABILITY
                ),
            ),
        ),
    ).model_dump(mode="json")
    _assert_failed(no_unsupported_availability_claim(unsupported))


def test_admission_probability_evaluator_accepts_fit_text_and_rejects_estimate() -> None:
    _assert_passed(no_admission_probability(_fit_output()))

    record = _verification_record()
    first, *remaining = record.evidence
    unsafe_evidence = (
        first.model_copy(update={"claim_summary": "There is a 90% chance of being admitted."}),
        *remaining,
    )
    unsafe = EvidenceVerificationTargetOutput(
        target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
        scenario_id="admission-probability-fixed-example",
        verification_records=(record.model_copy(update={"evidence": unsafe_evidence}),),
    ).model_dump(mode="json")
    _assert_failed(no_admission_probability(unsafe))


def test_fallback_route_accepts_bounded_retry_and_rejects_missing_fallback() -> None:
    reference = _expectation(
        expected_fallback_search_used=True,
        minimum_you_attempts=2,
        minimum_tavily_attempts=1,
    )
    valid_attempts = (
        _attempt(SearchProvider.YOU, 1, error_category=SearchErrorCategory.TIMEOUT),
        _attempt(SearchProvider.YOU, 2, error_category=SearchErrorCategory.TIMEOUT),
        _attempt(SearchProvider.TAVILY, 1),
    )
    _assert_passed(
        correct_fallback_route(
            _graph_output(fallback_search_used=True, search_attempts=valid_attempts), reference
        )
    )
    _assert_failed(
        correct_fallback_route(
            _graph_output(fallback_search_used=False, search_attempts=valid_attempts[:2]),
            reference,
        )
    )


def test_duplicate_rate_reports_lower_is_better_and_merged_provenance() -> None:
    reference = _expectation(
        maximum_duplicate_supervisor_rate=0.0,
        minimum_multi_query_provenance_count=1,
    )
    valid = duplicate_supervisor_rate(
        _graph_output(
            prospective_supervisor_ids=("supervisor-001", "supervisor-002"),
            supervisor_provenance=(
                SupervisorProvenanceProjection(supervisor_id="supervisor-001", provenance_count=2),
                SupervisorProvenanceProjection(supervisor_id="supervisor-002", provenance_count=1),
            ),
        ),
        reference,
    )
    assert valid.score == 0.0
    assert valid.comment is None
    assert valid.metadata == {
        "lower_is_better": True,
        "threshold": 0.0,
        "threshold_passed": True,
    }

    invalid = duplicate_supervisor_rate(
        _graph_output(
            prospective_supervisor_ids=("supervisor-001", "supervisor-001"),
            supervisor_provenance=(
                SupervisorProvenanceProjection(supervisor_id="supervisor-001", provenance_count=1),
            ),
        ),
        reference,
    )
    assert invalid.score == pytest.approx(0.5)
    assert invalid.comment
    assert invalid.metadata and invalid.metadata["threshold_passed"] is False


def test_human_approval_accepts_pause_and_approved_save_then_rejects_early_save() -> None:
    awaiting = _expectation(
        expected_review_outcome=CandidateReviewOutcome.AWAITING_REVIEW,
        expected_interrupted=True,
        expected_shortlisted_supervisor_ids=(),
    )
    _assert_passed(human_approval_enforcement(_graph_output(), awaiting))

    approval = CandidateReviewProjection(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=("supervisor-001",),
    )
    approved = _graph_output(
        interrupted=False,
        execution_log=("candidate_review_gate", "save_shortlisted_supervisors"),
        shortlisted_supervisor_ids=("supervisor-001",),
        candidate_reviews=(approval,),
    )
    _assert_passed(
        human_approval_enforcement(
            approved,
            _expectation(
                expected_review_outcome=CandidateReviewOutcome.APPROVE,
                expected_interrupted=False,
                expected_shortlisted_supervisor_ids=("supervisor-001",),
            ),
        )
    )

    _assert_failed(
        human_approval_enforcement(
            _graph_output(
                interrupted=False,
                execution_log=("save_shortlisted_supervisors", "candidate_review_gate"),
                shortlisted_supervisor_ids=("supervisor-001",),
            )
        )
    )


@pytest.mark.parametrize(
    "evaluator",
    (correct_fallback_route, duplicate_supervisor_rate, human_approval_enforcement),
)
def test_graph_only_evaluators_are_not_applicable_to_planning(
    evaluator: Evaluator,
) -> None:
    result = evaluator(_planning_output(), None)

    assert result.score is None
    assert result.value == "not_applicable"
