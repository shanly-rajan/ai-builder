"""Pure deterministic evaluators for ScholarPath LangSmith experiments."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from langsmith.evaluation import EvaluationResult
from pydantic import ValidationError

from ..domain import (
    AvailabilityStatus,
    CandidateReviewAction,
    EvidenceClaimType,
    ResearchFitAssessment,
)
from ..tools import SearchErrorCategory, SearchProvider
from .models import (
    EvaluationExpectation,
    EvaluationTargetOutput,
    EvidenceReferenceProjection,
    EvidenceVerificationTargetOutput,
    GraphTargetOutput,
    IndependentReviewExpectation,
    ResearchFitAssessmentProjection,
    ResearchFitTargetOutput,
    SearchPlanningTargetOutput,
    VerificationExpectation,
    VerificationRecordProjection,
    parse_evaluation_target_output,
)

_BANNED_TERMINOLOGY_PATTERNS = (
    re.compile(r"\bsupervisor[\s_-]+candidates?\b", re.IGNORECASE),
    re.compile(r"\bapproved[\s_-]+candidates?\b", re.IGNORECASE),
)
_ADMISSION_PROBABILITY_PATTERNS = (
    re.compile(r"\b(?:admission|acceptance)\s+(?:chance|likelihood|odds|probability)\b", re.I),
    re.compile(
        r"\b(?:chance|likelihood|odds|probability|percentage)\s+of\s+"
        r"(?:acceptance|being\s+(?:accepted|admitted))\b",
        re.I,
    ),
    re.compile(r"\b(?:likely|unlikely)\s+to\s+be\s+(?:accepted|admitted)\b", re.I),
    re.compile(r"\b\d+(?:\.\d+)?\s*%[^.\n]{0,40}\b(?:accepted|admitted)\b", re.I),
)


def _boolean_result(key: str, passed: bool, failure_comment: str) -> EvaluationResult:
    """Build one consistent boolean metric without exposing evaluated content."""
    return EvaluationResult(
        key=key,
        score=passed,
        comment=None if passed else failure_comment,
    )


def _invalid_output_result(key: str) -> EvaluationResult:
    """Return a sanitized failure for an output that cannot cross its schema boundary."""
    return _boolean_result(
        key,
        False,
        "The target output did not satisfy the typed ScholarPath evaluation contract.",
    )


def _not_applicable_result(key: str) -> EvaluationResult:
    """Exclude an irrelevant metric from aggregate scores."""
    return EvaluationResult(key=key, score=None, value="not_applicable")


def _parsed_output(outputs: Mapping[str, object]) -> EvaluationTargetOutput | None:
    try:
        return parse_evaluation_target_output(dict(outputs))
    except (ValidationError, TypeError, ValueError):
        return None


def _expectation(
    reference_outputs: Mapping[str, object] | None,
) -> EvaluationExpectation:
    if not reference_outputs:
        return EvaluationExpectation()
    raw_expectation: object = reference_outputs.get("expected", reference_outputs)
    try:
        return EvaluationExpectation.model_validate(raw_expectation)
    except (ValidationError, TypeError, ValueError):
        return EvaluationExpectation()


def _string_values(value: object) -> Iterable[str]:
    """Yield nested strings from JSON-like values without interpreting their meaning."""
    if isinstance(value, str):
        yield value
        return
    if isinstance(value, Mapping):
        for nested in value.values():
            yield from _string_values(nested)
        return
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        for nested in value:
            yield from _string_values(nested)


def _verification_records(
    output: EvaluationTargetOutput,
) -> tuple[VerificationRecordProjection, ...]:
    if isinstance(output, EvidenceVerificationTargetOutput | GraphTargetOutput):
        return output.verification_records
    return ()


def _assessment_projections(
    output: EvaluationTargetOutput,
) -> tuple[ResearchFitAssessmentProjection, ...]:
    if isinstance(output, ResearchFitTargetOutput | GraphTargetOutput):
        return output.assessments
    return ()


def _component_assessments(assessment: ResearchFitAssessment) -> tuple[tuple[str, Any], ...]:
    """Return dimension names with their typed component records."""
    return (
        ("topic_alignment", assessment.breakdown.topic_alignment),
        ("methodological_alignment", assessment.breakdown.methodological_alignment),
        (
            "research_orientation_alignment",
            assessment.breakdown.research_orientation_alignment,
        ),
        ("recent_research_alignment", assessment.breakdown.recent_research_alignment),
        (
            "practical_constraint_alignment",
            assessment.breakdown.practical_constraint_alignment,
        ),
    )


def schema_validity(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Check that a target returned one strict discriminated output schema."""
    del reference_outputs
    return _boolean_result(
        "schema_validity",
        _parsed_output(outputs) is not None,
        "The target output did not satisfy the typed ScholarPath evaluation contract.",
    )


def canonical_terminology(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Detect ambiguous Supervisor terminology without using a model."""
    del reference_outputs
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("canonical_terminology")
    serialized = output.model_dump(mode="json")
    passed = not any(
        pattern.search(text)
        for text in _string_values(serialized)
        for pattern in _BANNED_TERMINOLOGY_PATTERNS
    )
    return _boolean_result(
        "canonical_terminology",
        passed,
        "The output used ambiguous Candidate/Supervisor terminology.",
    )


def evidence_id_validity(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Validate Research Fit and review references against same-Supervisor evidence IDs."""
    del reference_outputs
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("evidence_id_validity")
    if not _assessment_projections(output) and not (
        isinstance(output, GraphTargetOutput) and output.independent_reviews
    ):
        return _not_applicable_result("evidence_id_validity")

    valid = True
    evidence_ids_by_supervisor: dict[str, set[str]] = {}
    for record in _verification_records(output):
        evidence_ids_by_supervisor.setdefault(record.supervisor_id, set()).update(
            item.evidence_id for item in record.evidence
        )

    for projection in _assessment_projections(output):
        assessment = projection.assessment
        evidence_by_id = {item.evidence_id: item for item in projection.evidence}
        evidence_ids_by_supervisor.setdefault(assessment.supervisor_id, set()).update(
            evidence_by_id
        )
        cited_ids = set(assessment.supporting_evidence_ids)
        if not cited_ids.issubset(evidence_by_id):
            valid = False
            continue
        if any(
            not evidence_by_id[evidence_id].directly_supported
            or evidence_by_id[evidence_id].claim_type is EvidenceClaimType.AVAILABILITY
            for evidence_id in cited_ids
        ):
            valid = False

    if isinstance(output, GraphTargetOutput):
        for review in output.independent_reviews:
            valid_ids = evidence_ids_by_supervisor.get(review.supervisor_id, set())
            if not set(review.unsupported_claim_ids).issubset(valid_ids):
                valid = False
            if not set(review.overlooked_evidence_ids).issubset(valid_ids):
                valid = False

    return _boolean_result(
        "evidence_id_validity",
        valid,
        "One or more assessment or review references were not valid evidence IDs.",
    )


def source_url_presence(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Require a validated source URL for every emitted factual evidence reference."""
    del reference_outputs
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("source_url_presence")
    if not isinstance(
        output,
        EvidenceVerificationTargetOutput | ResearchFitTargetOutput | GraphTargetOutput,
    ):
        return _not_applicable_result("source_url_presence")
    evidence = tuple(
        item for record in _verification_records(output) for item in record.evidence
    ) + tuple(
        item for assessment in _assessment_projections(output) for item in assessment.evidence
    )
    passed = all(bool(str(item.source_url).strip()) for item in evidence)
    return _boolean_result(
        "source_url_presence",
        passed,
        "At least one factual evidence reference did not preserve a source URL.",
    )


def score_range_and_component_totals(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Recalculate Research Fit bounds and component totals deterministically."""
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("score_range_and_component_totals")
    if not _assessment_projections(output):
        return _not_applicable_result("score_range_and_component_totals")
    expectation = _expectation(reference_outputs)
    valid = True
    for projection in _assessment_projections(output):
        assessment = projection.assessment
        components = _component_assessments(assessment)
        total = sum(component.score for _, component in components)
        valid = valid and 0 <= assessment.overall_score <= 100
        valid = valid and assessment.overall_score == total
        valid = valid and sum(assessment.rubric.weights.values()) == 100
        valid = valid and all(
            component.score <= assessment.rubric.weights[dimension]
            for dimension, component in components
        )
        if expectation.minimum_research_fit_score is not None:
            valid = valid and (assessment.overall_score >= expectation.minimum_research_fit_score)
        if expectation.maximum_research_fit_score is not None:
            valid = valid and (assessment.overall_score <= expectation.maximum_research_fit_score)
    return _boolean_result(
        "score_range_and_component_totals",
        valid,
        "A Research Fit Score violated its rubric bounds or deterministic total.",
    )


def _derived_availability(
    evidence: Iterable[EvidenceReferenceProjection],
) -> AvailabilityStatus:
    statuses = {
        item.availability_status
        for item in evidence
        if item.directly_supported
        and item.claim_type is EvidenceClaimType.AVAILABILITY
        and item.availability_status is not None
    }
    if statuses == {
        AvailabilityStatus.CONFIRMED_ACCEPTING,
        AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
    }:
        return AvailabilityStatus.CONFLICTING_EVIDENCE
    if AvailabilityStatus.CONFIRMED_ACCEPTING in statuses:
        return AvailabilityStatus.CONFIRMED_ACCEPTING
    if AvailabilityStatus.CONFIRMED_NOT_ACCEPTING in statuses:
        return AvailabilityStatus.CONFIRMED_NOT_ACCEPTING
    return AvailabilityStatus.NOT_STATED


def no_unsupported_availability_claim(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Re-derive availability only from direct typed evidence."""
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("no_unsupported_availability_claim")
    if not _verification_records(output) and not _assessment_projections(output):
        return _not_applicable_result("no_unsupported_availability_claim")
    expectation = _expectation(reference_outputs)
    records = _verification_records(output)
    valid = all(
        record.availability_status is _derived_availability(record.evidence) for record in records
    )
    observed_statuses = [record.availability_status for record in records]
    observed_statuses.extend(
        _derived_availability(projection.evidence) for projection in _assessment_projections(output)
    )
    if expectation.expected_availability_status is not None and observed_statuses:
        valid = valid and all(
            status is expectation.expected_availability_status for status in observed_statuses
        )
    if isinstance(output, GraphTargetOutput):
        availability_by_id = {
            record.supervisor_id: record.availability_status for record in records
        }
        for projection in output.assessments:
            availability_by_id.setdefault(
                projection.assessment.supervisor_id,
                _derived_availability(projection.evidence),
            )
        valid = valid and all(
            availability_by_id.get(item.supervisor_id) is item.availability_status
            for item in output.shortlist_recommendations
        )
    return _boolean_result(
        "no_unsupported_availability_claim",
        valid,
        "An availability status was not supported by direct typed evidence.",
    )


def _generated_prose(output: EvaluationTargetOutput) -> tuple[str, ...]:
    """Return generated prose while excluding Candidate preference input."""
    prose: list[str] = []
    if hasattr(output, "search_plan"):
        prose.append(output.search_plan.rationale)
        prose.extend(query.purpose for query in output.search_plan.search_queries)
    for record in _verification_records(output):
        prose.extend(record.verification_concerns)
        prose.extend(item.claim_summary for item in record.evidence)
    for projection in _assessment_projections(output):
        assessment = projection.assessment
        prose.extend((assessment.rationale, *assessment.concerns))
        for _, component in _component_assessments(assessment):
            prose.append(component.rationale)
            if component.evidence_gap is not None:
                prose.append(component.evidence_gap)
    if isinstance(output, GraphTargetOutput):
        for review in output.independent_reviews:
            prose.extend((review.effective_rationale, review.critique))
        for recommendation in output.shortlist_recommendations:
            prose.extend((*recommendation.strengths, *recommendation.concerns))
    return tuple(prose)


def no_admission_probability(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Reject admission-likelihood language using fixed patterns only."""
    del reference_outputs
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("no_admission_probability")
    passed = not any(
        pattern.search(text)
        for text in _generated_prose(output)
        for pattern in _ADMISSION_PROBABILITY_PATTERNS
    )
    return _boolean_result(
        "no_admission_probability",
        passed,
        "Generated prose estimated admission or acceptance probability.",
    )


def correct_fallback_route(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Compare the observed provider route with deterministic scenario expectations."""
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("correct_fallback_route")
    if not isinstance(output, GraphTargetOutput):
        return _not_applicable_result("correct_fallback_route")
    expectation = _expectation(reference_outputs)
    expected_fallback = expectation.expected_fallback_search_used
    if expected_fallback is None:
        return _not_applicable_result("correct_fallback_route")

    you_attempts = tuple(
        item for item in output.search_attempts if item.provider_used is SearchProvider.YOU
    )
    tavily_attempts = tuple(
        item for item in output.search_attempts if item.provider_used is SearchProvider.TAVILY
    )
    valid = output.fallback_search_used is expected_fallback
    valid = valid and bool(tavily_attempts) if expected_fallback else valid and not tavily_attempts
    valid = valid and len(you_attempts) >= expectation.minimum_you_attempts
    valid = valid and len(tavily_attempts) >= expectation.minimum_tavily_attempts
    if expectation.minimum_you_attempts > 1:
        valid = valid and any(
            item.error_category is SearchErrorCategory.TIMEOUT for item in you_attempts
        )
        valid = valid and max(item.attempt_number for item in you_attempts) >= 2
    return _boolean_result(
        "correct_fallback_route",
        valid,
        "Observed provider attempts did not follow the expected bounded fallback route.",
    )


def duplicate_supervisor_rate(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Report the retained duplicate-ID rate as a lower-is-better numeric metric."""
    output = _parsed_output(outputs)
    if output is None:
        return EvaluationResult(
            key="duplicate_supervisor_rate",
            score=None,
            value="invalid_output",
            comment="The target output did not satisfy the typed evaluation contract.",
        )
    if not isinstance(output, GraphTargetOutput):
        return _not_applicable_result("duplicate_supervisor_rate")
    identifiers = output.prospective_supervisor_ids
    duplicate_count = len(identifiers) - len(set(identifiers))
    rate = duplicate_count / len(identifiers) if identifiers else 0.0
    expectation = _expectation(reference_outputs)
    provenance_matches = sum(item.provenance_count > 1 for item in output.supervisor_provenance)
    within_threshold = rate <= expectation.maximum_duplicate_supervisor_rate
    provenance_sufficient = provenance_matches >= expectation.minimum_multi_query_provenance_count
    comment = None
    if not within_threshold or not provenance_sufficient:
        comment = "Deduplication or merged-provenance expectations were not satisfied."
    return EvaluationResult(
        key="duplicate_supervisor_rate",
        score=rate,
        value=rate,
        comment=comment,
        metadata={
            "lower_is_better": True,
            "threshold": expectation.maximum_duplicate_supervisor_rate,
            "threshold_passed": within_threshold and provenance_sufficient,
        },
    )


def _candidate_review_action(output: GraphTargetOutput) -> CandidateReviewAction | None:
    if not output.candidate_reviews:
        return None
    return output.candidate_reviews[-1].action


def human_approval_enforcement(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Ensure shortlist persistence occurs only after explicit scoped approval."""
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("human_approval_enforcement")
    if not isinstance(output, GraphTargetOutput):
        return _not_applicable_result("human_approval_enforcement")

    expectation = _expectation(reference_outputs)
    approvals = tuple(
        review
        for review in output.candidate_reviews
        if review.action is CandidateReviewAction.APPROVE
    )
    approved_ids = approvals[-1].supervisor_ids if approvals else ()
    valid = True
    if approved_ids:
        valid = tuple(output.shortlisted_supervisor_ids) == tuple(approved_ids)
    else:
        valid = not output.shortlisted_supervisor_ids
    if output.interrupted:
        valid = valid and not output.shortlisted_supervisor_ids

    if "save_shortlisted_supervisors" in output.execution_log:
        save_position = max(
            index
            for index, node_name in enumerate(output.execution_log)
            if node_name == "save_shortlisted_supervisors"
        )
        review_positions = [
            index
            for index, node_name in enumerate(output.execution_log)
            if node_name == "candidate_review_gate"
        ]
        valid = valid and bool(review_positions) and max(review_positions) < save_position
        valid = valid and bool(approved_ids)

    if expectation.expected_shortlisted_supervisor_ids:
        valid = valid and (
            tuple(output.shortlisted_supervisor_ids)
            == expectation.expected_shortlisted_supervisor_ids
        )
    if expectation.expected_proposed_supervisor_ids:
        valid = valid and (
            tuple(output.proposed_supervisor_ids) == expectation.expected_proposed_supervisor_ids
        )
    if expectation.expected_rejected_supervisor_ids:
        valid = valid and (
            tuple(output.rejected_supervisor_ids) == expectation.expected_rejected_supervisor_ids
        )
    if expectation.expected_interrupted is not None:
        valid = valid and output.interrupted is expectation.expected_interrupted
    expected_outcome = expectation.expected_review_outcome
    if expected_outcome is not None:
        observed_action = _candidate_review_action(output)
        observed_outcome = (
            "awaiting_review"
            if output.interrupted and observed_action is None
            else observed_action.value
            if observed_action is not None
            else "not_applicable"
        )
        valid = valid and observed_outcome == expected_outcome.value

    return _boolean_result(
        "human_approval_enforcement",
        valid,
        "A shortlist was persisted without the required explicit Candidate approval.",
    )


def _verification_matches(
    record: VerificationRecordProjection, expected: VerificationExpectation
) -> bool:
    """Compare labeled evidence outcomes without interpreting generated prose."""
    if (
        record.verification_status is not expected.verification_status
        or record.verified_supervisor_present is not expected.verified_supervisor_present
        or len(record.evidence) < expected.minimum_retained_evidence
        or (
            expected.maximum_retained_evidence is not None
            and len(record.evidence) > expected.maximum_retained_evidence
        )
        or not set(expected.required_claim_types).issubset(
            claim.claim_type for claim in record.evidence if claim.directly_supported
        )
        or (
            expected.expected_missing_required_evidence is not None
            and set(record.missing_required_evidence)
            != set(expected.expected_missing_required_evidence)
        )
    ):
        return False
    if expected.affiliation_conflict_surfaced:
        affiliation_claims = {
            claim.evidence_id: claim
            for claim in record.evidence
            if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
            and claim.directly_supported
        }
        return bool(record.verification_concerns) and any(
            other_id in affiliation_claims
            and claim.evidence_id in affiliation_claims[other_id].conflicting_evidence_ids
            and claim.source_url != affiliation_claims[other_id].source_url
            for claim in affiliation_claims.values()
            for other_id in claim.conflicting_evidence_ids
        )
    return True


def _independent_review_matches(
    output: GraphTargetOutput, expected: IndependentReviewExpectation
) -> bool:
    matching = [
        review
        for review in output.independent_reviews
        if review.supervisor_id == expected.supervisor_id
    ]
    if len(matching) != 1:
        return False
    review = matching[0]
    return (
        review.review_status is expected.review_status
        and review.effective_score == expected.effective_score
        and review.effective_confidence is expected.effective_confidence
        and review.requires_candidate_attention is expected.requires_candidate_attention
        and any(
            item.assessment.supervisor_id == expected.supervisor_id for item in output.assessments
        )
        and all(
            item.effective_score == review.effective_score
            and item.evidence_confidence is review.effective_confidence
            for item in output.shortlist_recommendations
            if item.supervisor_id == expected.supervisor_id
        )
    )


def _graph_behavior_matches(output: GraphTargetOutput, expected: EvaluationExpectation) -> bool:
    """Require real progress before accepting a labeled successful graph outcome."""
    if not output.execution_log:
        return False
    if (
        expected.expected_review_status is not None
        and output.review_status is not expected.expected_review_status
    ):
        return False
    if expected.expected_interrupted or expected.expected_proposed_supervisor_ids:
        verified_ids = {
            record.supervisor_id
            for record in output.verification_records
            if record.verified_supervisor_present
        }
        assessed_ids = {item.assessment.supervisor_id for item in output.assessments}
        if (
            not output.prospective_supervisor_ids
            or not output.proposed_supervisor_ids
            or not output.shortlist_recommendations
            or not set(output.proposed_supervisor_ids).issubset(verified_ids & assessed_ids)
        ):
            return False
    for observed, labeled in (
        (output.proposed_supervisor_ids, expected.expected_proposed_supervisor_ids),
        (output.shortlisted_supervisor_ids, expected.expected_shortlisted_supervisor_ids),
        (output.rejected_supervisor_ids, expected.expected_rejected_supervisor_ids),
    ):
        if labeled is not None and observed != labeled:
            return False
    if set(output.rejected_supervisor_ids) & (
        set(output.proposed_supervisor_ids) | set(output.shortlisted_supervisor_ids)
    ):
        return False
    reference: dict[str, object] = {"expected": expected.model_dump(mode="json")}
    if human_approval_enforcement(output.model_dump(mode="json"), reference).score is not True:
        return False
    if (
        expected.expected_fallback_search_used is not None
        and correct_fallback_route(output.model_dump(mode="json"), reference).score is not True
    ):
        return False
    for provider, minimum in (
        (SearchProvider.YOU, expected.minimum_you_attempts),
        (SearchProvider.TAVILY, expected.minimum_tavily_attempts),
    ):
        if sum(attempt.provider_used is provider for attempt in output.search_attempts) < minimum:
            return False
    duplicate_result = duplicate_supervisor_rate(output.model_dump(mode="json"), reference)
    if not duplicate_result.metadata or not duplicate_result.metadata.get("threshold_passed"):
        return False
    return all(
        _independent_review_matches(output, item) for item in expected.expected_independent_reviews
    )


def expected_behavior(
    outputs: dict[str, object],
    reference_outputs: dict[str, object] | None = None,
) -> EvaluationResult:
    """Check declared outcome labels; missing or malformed references never pass."""
    output = _parsed_output(outputs)
    if output is None:
        return _invalid_output_result("expected_behavior")
    try:
        if not reference_outputs or "expected" not in reference_outputs:
            raise ValueError("Explicit reference outcomes are required")
        expected = EvaluationExpectation.model_validate(reference_outputs["expected"])
        if expected == EvaluationExpectation():
            raise ValueError("At least one declared outcome label is required")
    except (ValidationError, TypeError, ValueError):
        return _boolean_result(
            "expected_behavior", False, "Declared outcome labels are missing or invalid."
        )

    valid = True
    if expected.expected_supervisor_ids is not None:
        if isinstance(output, GraphTargetOutput):
            observed_ids = output.prospective_supervisor_ids
        elif isinstance(output, EvidenceVerificationTargetOutput):
            observed_ids = tuple(record.supervisor_id for record in output.verification_records)
        else:
            observed_ids = tuple(
                item.assessment.supervisor_id for item in _assessment_projections(output)
            )
        valid = len(observed_ids) == len(expected.expected_supervisor_ids) and set(
            observed_ids
        ) == set(expected.expected_supervisor_ids)
    if expected.expected_verification_records:
        records = _verification_records(output)
        by_id = {record.supervisor_id: record for record in records}
        valid = valid and len(records) == len(expected.expected_verification_records)
        valid = valid and all(
            label.supervisor_id in by_id
            and _verification_matches(by_id[label.supervisor_id], label)
            for label in expected.expected_verification_records
        )
    if expected.required_planning_source_types:
        if isinstance(output, SearchPlanningTargetOutput):
            valid = valid and set(expected.required_planning_source_types).issubset(
                source
                for query in output.search_plan.search_queries
                for source in query.target_source_types
            )
        else:
            valid = False
    if expected.expected_supervisor_ids is not None and isinstance(
        output, SearchPlanningTargetOutput
    ):
        valid = False
    if (
        expected.minimum_research_fit_score is not None
        or expected.maximum_research_fit_score is not None
    ):
        valid = (
            valid
            and bool(_assessment_projections(output))
            and score_range_and_component_totals(outputs, reference_outputs).score is True
        )
    if expected.expected_availability_status is not None:
        valid = (
            valid
            and bool(_verification_records(output) or _assessment_projections(output))
            and no_unsupported_availability_claim(outputs, reference_outputs).score is True
        )

    graph_labels = (
        expected.expected_review_status is not None
        or expected.expected_review_outcome is not None
        or expected.expected_interrupted is not None
        or expected.expected_fallback_search_used is not None
        or expected.expected_proposed_supervisor_ids is not None
        or expected.expected_shortlisted_supervisor_ids is not None
        or expected.expected_rejected_supervisor_ids is not None
        or bool(expected.expected_independent_reviews)
        or expected.minimum_you_attempts > 0
        or expected.minimum_tavily_attempts > 0
        or expected.minimum_multi_query_provenance_count > 0
    )
    if isinstance(output, GraphTargetOutput):
        valid = valid and _graph_behavior_matches(output, expected)
    elif graph_labels:
        valid = False
    return _boolean_result(
        "expected_behavior",
        valid,
        "The output did not satisfy the declared Supervisor, evidence, planning, "
        "or graph outcome labels.",
    )


DETERMINISTIC_EVALUATORS = (
    schema_validity,
    expected_behavior,
    canonical_terminology,
    evidence_id_validity,
    source_url_presence,
    score_range_and_component_totals,
    no_unsupported_availability_claim,
    no_admission_probability,
    correct_fallback_route,
    duplicate_supervisor_rate,
    human_approval_enforcement,
)
"""Stable ordered evaluator set used by the M12 runner."""
