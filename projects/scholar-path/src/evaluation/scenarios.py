"""Versioned synthetic scenarios for ScholarPath's M12 regression dataset."""

from __future__ import annotations

from typing import Final

from ..domain import AvailabilityStatus
from ..graph import build_walking_skeleton_fixtures, default_review_decision
from .models import (
    CandidatePreferenceProjection,
    CandidateReviewOutcome,
    EvaluationExpectation,
    EvaluationScenario,
    EvaluationTargetKind,
)

EVALUATION_DATASET_NAME: Final = "scholarpath-m12-regression-v1"
EVALUATION_SCENARIO_VERSION: Final = "m12-scenarios-v1"


def _candidate_preferences(
    *,
    research_topics: tuple[str, ...] = (
        "enterprise architecture",
        "responsible AI governance",
        "digital transformation",
        "organisational resilience",
    ),
    preferred_research_orientation: str = "applied",
    methodological_interests: tuple[str, ...] = (
        "design science",
        "comparative case study",
        "mixed methods",
    ),
    exclusions: tuple[str, ...] = ("fully residential programmes",),
) -> CandidatePreferenceProjection:
    return CandidatePreferenceProjection(
        research_topics=research_topics,
        preferred_regions=("South Africa", "United Kingdom", "Netherlands"),
        preferred_study_modes=("hybrid", "part-time"),
        preferred_research_orientation=preferred_research_orientation,
        methodological_interests=methodological_interests,
        exclusions=exclusions,
    )


def build_evaluation_scenarios() -> tuple[EvaluationScenario, ...]:
    """Build the ten required regressions plus one planning-coverage scenario."""
    fixtures = build_walking_skeleton_fixtures()
    supervisor_ids = tuple(item.supervisor_id for item in fixtures.raw_search_results)
    default_proposal_ids = default_review_decision().supervisor_ids
    common_tags = ("application:scholarpath", f"scenario-version:{EVALUATION_SCENARIO_VERSION}")

    scenarios = (
        EvaluationScenario(
            scenario_id="strong-research-alignment",
            title="Strong research alignment",
            description=(
                "A directly supported applied enterprise-architecture profile should receive "
                "a strong, evidence-cited Research Fit assessment."
            ),
            target=EvaluationTargetKind.RESEARCH_FIT,
            tags=(*common_tags, "quality:strong-fit"),
            splits=("research-fit", "llm-judge"),
            candidate_preferences=_candidate_preferences(),
            config={"fit_case": "strong", "supervisor_index": 1},
            expected=EvaluationExpectation(
                expected_availability_status=AvailabilityStatus.NOT_STATED,
                expected_supervisor_ids=(supervisor_ids[0],),
                minimum_research_fit_score=80,
                maximum_research_fit_score=100,
            ),
        ),
        EvaluationScenario(
            scenario_id="superficial-keyword-poor-fit",
            title="Superficial keyword overlap with poor actual fit",
            description=(
                "Shared generic enterprise wording must not override incompatible topics, "
                "methods, orientation, and explicit exclusions."
            ),
            target=EvaluationTargetKind.RESEARCH_FIT,
            tags=(*common_tags, "quality:weak-fit"),
            splits=("research-fit", "llm-judge"),
            candidate_preferences=_candidate_preferences(
                research_topics=("enterprise ethnography", "workplace culture"),
                preferred_research_orientation="highly theoretical",
                methodological_interests=("long-form ethnography",),
                exclusions=("AI governance", "design science"),
            ),
            config={"fit_case": "superficial", "supervisor_index": 1},
            expected=EvaluationExpectation(
                expected_availability_status=AvailabilityStatus.NOT_STATED,
                expected_supervisor_ids=(supervisor_ids[0],),
                maximum_research_fit_score=25,
            ),
        ),
        EvaluationScenario(
            scenario_id="availability-not-stated",
            title="Supervisor availability is not stated",
            description=(
                "Complete identity, affiliation, and research evidence must verify without "
                "inventing doctoral supervision availability."
            ),
            target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
            tags=(*common_tags, "evidence:availability"),
            splits=("evidence-verification",),
            config={"evidence_case": "not_stated", "supervisor_index": 1},
            expected=EvaluationExpectation(
                expected_availability_status=AvailabilityStatus.NOT_STATED,
                expected_supervisor_ids=(supervisor_ids[0],),
            ),
        ),
        EvaluationScenario(
            scenario_id="conflicting-institutional-affiliation",
            title="Conflicting institutional affiliation",
            description=(
                "Two official sources assert different current affiliations and both must "
                "remain visible as a verification concern."
            ),
            target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
            tags=(*common_tags, "evidence:conflict"),
            splits=("evidence-verification",),
            config={"evidence_case": "affiliation_conflict", "supervisor_index": 1},
            expected=EvaluationExpectation(expected_supervisor_ids=(supervisor_ids[0],)),
        ),
        EvaluationScenario(
            scenario_id="duplicate-supervisor-multiple-queries",
            title="Duplicate Supervisor discovered through multiple queries",
            description=(
                "One academic profile appears in two query result sets and must be retained "
                "once with both provenance records."
            ),
            target=EvaluationTargetKind.GRAPH_FAKE,
            tags=(*common_tags, "routing:deduplication"),
            splits=("graph-fake",),
            candidate_preferences=_candidate_preferences(),
            config={"graph_case": "duplicate_provenance"},
            expected=EvaluationExpectation(
                expected_review_outcome=CandidateReviewOutcome.AWAITING_REVIEW,
                expected_interrupted=True,
                expected_supervisor_ids=supervisor_ids,
                maximum_duplicate_supervisor_rate=0.0,
                minimum_multi_query_provenance_count=1,
            ),
        ),
        EvaluationScenario(
            scenario_id="you-timeout-tavily-fallback",
            title="You.com timeout requiring Tavily fallback",
            description=(
                "A primary timeout and its single retry should route to Tavily and preserve "
                "the bounded attempt history."
            ),
            target=EvaluationTargetKind.GRAPH_FAKE,
            tags=(*common_tags, "routing:fallback"),
            splits=("graph-fake",),
            candidate_preferences=_candidate_preferences(),
            config={"graph_case": "you_timeout_tavily"},
            expected=EvaluationExpectation(
                expected_fallback_search_used=True,
                expected_review_outcome=CandidateReviewOutcome.AWAITING_REVIEW,
                expected_interrupted=True,
                minimum_you_attempts=2,
                minimum_tavily_attempts=1,
            ),
        ),
        EvaluationScenario(
            scenario_id="evidence-extraction-failure",
            title="Evidence extraction failure",
            description=(
                "One failed profile extraction must remain partially verified without "
                "fabricated evidence while the useful partial cohort continues."
            ),
            target=EvaluationTargetKind.GRAPH_FAKE,
            tags=(*common_tags, "evidence:extraction-failure"),
            splits=("graph-fake",),
            candidate_preferences=_candidate_preferences(),
            config={"graph_case": "extraction_failure", "failed_supervisor_index": 1},
            expected=EvaluationExpectation(
                expected_review_outcome=CandidateReviewOutcome.AWAITING_REVIEW,
                expected_interrupted=True,
            ),
        ),
        EvaluationScenario(
            scenario_id="independent-reviewer-disagreement",
            title="Independent reviewer disagreement",
            description=(
                "A large valid review revision must lower confidence, flag Candidate attention, "
                "and update ordering deterministically."
            ),
            target=EvaluationTargetKind.GRAPH_FAKE,
            tags=(*common_tags, "review:disagreement"),
            splits=("graph-fake", "llm-judge"),
            candidate_preferences=_candidate_preferences(),
            config={
                "graph_case": "reviewer_disagreement",
                "reviewed_supervisor_index": 1,
                "reviewed_score": 60,
            },
            expected=EvaluationExpectation(
                expected_review_outcome=CandidateReviewOutcome.AWAITING_REVIEW,
                expected_interrupted=True,
            ),
        ),
        EvaluationScenario(
            scenario_id="candidate-rejects-highly-theoretical",
            title="Candidate rejects highly theoretical research",
            description=(
                "An explicit Supervisor-specific rejection must be recorded and route to a "
                "bounded refined proposal without persisting a shortlist."
            ),
            target=EvaluationTargetKind.GRAPH_FAKE,
            tags=(*common_tags, "candidate-review:reject"),
            splits=("graph-fake",),
            candidate_preferences=_candidate_preferences(),
            config={"graph_case": "reject_theoretical", "rejected_supervisor_index": 1},
            expected=EvaluationExpectation(
                expected_review_outcome=CandidateReviewOutcome.REJECT,
                expected_interrupted=True,
                expected_rejected_supervisor_ids=(supervisor_ids[0],),
                expected_shortlisted_supervisor_ids=(),
            ),
        ),
        EvaluationScenario(
            scenario_id="approval-required-before-persistence",
            title="Candidate approval required before shortlist persistence",
            description=(
                "The graph must pause with a proposed set and persist no Shortlisted Supervisor "
                "until an explicit approval response is received."
            ),
            target=EvaluationTargetKind.GRAPH_FAKE,
            tags=(*common_tags, "candidate-review:approval-gate"),
            splits=("graph-fake", "graph-live"),
            candidate_preferences=_candidate_preferences(),
            config={"graph_case": "approval_pause"},
            expected=EvaluationExpectation(
                expected_review_outcome=CandidateReviewOutcome.AWAITING_REVIEW,
                expected_interrupted=True,
                expected_proposed_supervisor_ids=default_proposal_ids,
                expected_shortlisted_supervisor_ids=(),
            ),
        ),
        EvaluationScenario(
            scenario_id="planning-source-coverage",
            title="Search planning source coverage",
            description=(
                "A source-complete plan must cover official profiles, departments, recent "
                "publications, and explicit doctoral supervision information."
            ),
            target=EvaluationTargetKind.SEARCH_PLANNING,
            tags=(*common_tags, "planning:source-coverage"),
            splits=("planning",),
            candidate_preferences=_candidate_preferences(),
            config={"planning_case": "source_coverage"},
            expected=EvaluationExpectation(),
        ),
    )
    scenario_ids = [scenario.scenario_id for scenario in scenarios]
    if len(scenario_ids) != len(set(scenario_ids)):
        raise AssertionError("Evaluation scenario identifiers must be unique")
    return scenarios


EVALUATION_SCENARIOS: Final = build_evaluation_scenarios()


def evaluation_scenario_by_id(scenario_id: str) -> EvaluationScenario:
    """Resolve one known synthetic scenario by its stable identifier."""
    normalized = scenario_id.strip()
    try:
        return next(item for item in EVALUATION_SCENARIOS if item.scenario_id == normalized)
    except StopIteration as error:
        raise ValueError(f"Unknown ScholarPath evaluation scenario: {normalized}") from error


def evaluation_dataset_inputs(scenario: EvaluationScenario) -> dict[str, object]:
    """Return one JSON-safe dataset input envelope accepted by every target."""
    return {"scenario": scenario.model_dump(mode="json", exclude={"expected"})}


def evaluation_dataset_reference_outputs(scenario: EvaluationScenario) -> dict[str, object]:
    """Return only deterministic expectations, never target-generated prose."""
    return {"expected": scenario.expected.model_dump(mode="json")}


__all__ = [
    "EVALUATION_DATASET_NAME",
    "EVALUATION_SCENARIOS",
    "EVALUATION_SCENARIO_VERSION",
    "build_evaluation_scenarios",
    "evaluation_dataset_inputs",
    "evaluation_dataset_reference_outputs",
    "evaluation_scenario_by_id",
]
