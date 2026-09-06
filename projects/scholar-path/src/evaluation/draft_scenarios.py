"""Thirty separately versioned synthetic cases awaiting Candidate label review.

The eleven v1 scenarios are retained verbatim. New expectations are declared here,
never inferred from running the target. Behavioral variations live in fake targets.
"""

from __future__ import annotations

from typing import Final

from ..domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewStatus,
    VerificationStatus,
)
from ..graph import ReviewStatus, build_walking_skeleton_fixtures, default_review_decision
from .draft_models import DraftEvaluationCase, DraftScenarioType, EvaluationDraft
from .models import (
    CandidateReviewOutcome,
    EvaluationExpectation,
    EvaluationScenario,
    EvaluationTargetKind,
    IndependentReviewExpectation,
    VerificationExpectation,
)
from .scenarios import EVALUATION_SCENARIO_VERSION, EVALUATION_SCENARIOS

DRAFT_DATASET_NAME: Final = "scholarpath-week4-30case-draft-v1"
DRAFT_SCENARIO_VERSION: Final = "week4-30case-draft-v1"
_ACKNOWLEDGED_OUTCOMES: Final = frozenset(
    {
        "strong-research-alignment",
        "superficial-keyword-poor-fit",
        "evidence-extraction-failure",
        "you-timeout-tavily-fallback",
        "candidate-rejects-highly-theoretical",
    }
)
_RETAINED_TYPES: Final = (
    DraftScenarioType.HAPPY,
    DraftScenarioType.EDGE,
    DraftScenarioType.HAPPY,
    DraftScenarioType.EDGE,
    DraftScenarioType.EDGE,
    DraftScenarioType.KNOWN_FAILURE,
    DraftScenarioType.KNOWN_FAILURE,
    DraftScenarioType.EDGE,
    DraftScenarioType.EDGE,
    DraftScenarioType.HAPPY,
    DraftScenarioType.HAPPY,
)

# Each case changes actual synthetic page/claim inputs, not just the scenario name.
_EVIDENCE_CASES: Final = (
    (
        "confirmed_accepting",
        DraftScenarioType.HAPPY,
        "Explicitly accepting research-degree supervision",
        "A directly stated availability sentence permits confirmed_accepting without any "
        "admission likelihood or broader degree-scope inference.",
    ),
    (
        "confirmed_not_accepting",
        DraftScenarioType.HAPPY,
        "Explicitly not accepting research-degree supervision",
        "Negative availability remains confirmed_not_accepting; it does not prevent "
        "identity, affiliation, and research verification, but is surfaced as a concern.",
    ),
    (
        "markdown_identity",
        DraftScenarioType.HAPPY,
        "Markdown-formatted profile identity",
        "Markdown presentation around an exact profile name must preserve its directly "
        "supported identity and all required verification gates.",
    ),
    (
        "honorific_identity",
        DraftScenarioType.HAPPY,
        "Identity with a different supported honorific form",
        "Canonical name matching may normalize an academic title without changing the person.",
    ),
    (
        "line_wrapped_affiliation",
        DraftScenarioType.HAPPY,
        "Line-wrapped current affiliation",
        "Whitespace presentation must not discard an explicit name, institution, and department.",
    ),
    (
        "publication_only",
        DraftScenarioType.HAPPY,
        "Publication evidence supplies the research gate",
        "A directly supported publication satisfies the research gate even without a separate "
        "research-interest claim; no research interests are invented.",
    ),
    (
        "heading_bound_research",
        DraftScenarioType.HAPPY,
        "Research statement bound to the profile heading",
        "A nearby profile heading may bind a self-description to its subject when existing "
        "bounded grounding checks pass; a name need not be repeated in every sentence.",
    ),
    (
        "missing_identity",
        DraftScenarioType.EDGE,
        "Required identity evidence missing",
        "Other evidence cannot replace the mandatory identity claim. Without a grounded "
        "identity, affiliation and research claims are not directly supported either; "
        "retain a partial record with all three gates missing.",
    ),
    (
        "missing_affiliation",
        DraftScenarioType.EDGE,
        "Required current affiliation missing",
        "An identified researcher with research evidence but no current affiliation remains "
        "partially verified under the strict standard.",
    ),
    (
        "missing_research",
        DraftScenarioType.EDGE,
        "Required research evidence missing",
        "Identity and affiliation alone must not satisfy strict research verification.",
    ),
    (
        "publication_year_not_stated",
        DraftScenarioType.EDGE,
        "Publication evidence without a stated year",
        "A grounded undated publication can establish research activity but must not acquire "
        "an invented date or a claim of recency.",
    ),
    (
        "availability_without_statement",
        DraftScenarioType.ADVERSARIAL,
        "Model attempts an unsupported availability assertion",
        "An accepting claim lacking a direct source statement must leave availability "
        "not_stated, regardless of the model's asserted confidence.",
    ),
    (
        "off_page_excerpt",
        DraftScenarioType.ADVERSARIAL,
        "Model cites research excerpts absent from the page",
        "Invented research quotations must not become directly supported evidence or satisfy "
        "the mandatory research gate.",
    ),
)


def _retained_cases() -> tuple[DraftEvaluationCase, ...]:
    return tuple(
        DraftEvaluationCase(
            scenario=scenario,
            scenario_type=scenario_type,
            origin="retained_v1",
            source_reference="src/evaluation/scenarios.py",
            source_version=EVALUATION_SCENARIO_VERSION,
            label_rationale=scenario.description,
            starting_outcome_previously_acknowledged=(
                scenario.scenario_id in _ACKNOWLEDGED_OUTCOMES
            ),
            starting_outcome_reference=(
                "docs/prompts/week4-3-single-synthetic-trace.md"
                if scenario.scenario_id in _ACKNOWLEDGED_OUTCOMES
                else None
            ),
        )
        for scenario, scenario_type in zip(EVALUATION_SCENARIOS, _RETAINED_TYPES, strict=True)
    )


def _new_case(
    scenario: EvaluationScenario, kind: DraftScenarioType, source_reference: str
) -> DraftEvaluationCase:
    return DraftEvaluationCase(
        scenario=scenario,
        scenario_type=kind,
        origin="new_synthetic_fixture",
        source_reference=source_reference,
        source_version=DRAFT_SCENARIO_VERSION,
        label_rationale=scenario.description,
    )


def _evidence_cases() -> tuple[DraftEvaluationCase, ...]:
    supervisor_id = build_walking_skeleton_fixtures().raw_search_results[0].supervisor_id
    cases: list[DraftEvaluationCase] = []
    for evidence_case, kind, title, rationale in _EVIDENCE_CASES:
        missing = {
            "missing_identity": (
                "identity",
                "current_affiliation",
                "research_interest_or_publication",
            ),
            "missing_affiliation": ("current_affiliation",),
            "missing_research": ("research_interest_or_publication",),
            "off_page_excerpt": ("research_interest_or_publication",),
        }.get(evidence_case, ())
        availability = {
            "confirmed_accepting": AvailabilityStatus.CONFIRMED_ACCEPTING,
            "confirmed_not_accepting": AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
        }.get(evidence_case, AvailabilityStatus.NOT_STATED)
        required = tuple(
            claim_type
            for claim_type, gate in (
                (EvidenceClaimType.IDENTITY, "identity"),
                (EvidenceClaimType.CURRENT_AFFILIATION, "current_affiliation"),
                (
                    EvidenceClaimType.PUBLICATION
                    if evidence_case == "publication_only"
                    else EvidenceClaimType.RESEARCH_INTEREST,
                    "research_interest_or_publication",
                ),
            )
            if gate not in missing
        )
        scenario = EvaluationScenario(
            scenario_id=f"draft-evidence-{evidence_case.replace('_', '-')}",
            title=title,
            description=rationale,
            target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
            tags=("application:scholarpath", f"scenario-version:{DRAFT_SCENARIO_VERSION}"),
            splits=("evidence-verification",),
            config={"evidence_case": evidence_case, "supervisor_index": 1},
            expected=EvaluationExpectation(
                expected_availability_status=availability,
                expected_supervisor_ids=(supervisor_id,),
                expected_verification_records=(
                    VerificationExpectation(
                        supervisor_id=supervisor_id,
                        verification_status=(
                            VerificationStatus.PARTIALLY_VERIFIED
                            if missing
                            else VerificationStatus.VERIFIED_WITH_CONCERNS
                            if evidence_case == "confirmed_not_accepting"
                            else VerificationStatus.VERIFIED
                        ),
                        verified_supervisor_present=not missing,
                        minimum_retained_evidence=len(required),
                        required_claim_types=required,
                        expected_missing_required_evidence=missing,
                    ),
                ),
            ),
        )
        cases.append(_new_case(scenario, kind, "src/evaluation/draft_evidence.py"))
    return tuple(cases)


def _graph_cases() -> tuple[DraftEvaluationCase, ...]:
    base = next(
        item
        for item in EVALUATION_SCENARIOS
        if item.scenario_id == "approval-required-before-persistence"
    )
    proposal = default_review_decision().supervisor_ids
    replacement_id = build_walking_skeleton_fixtures().raw_search_results[5].supervisor_id
    cases: list[DraftEvaluationCase] = []
    definitions = (
        (
            "approve_one",
            "Candidate approves only one Supervisor",
            "Persist exactly the one explicitly selected Supervisor and complete the briefing.",
        ),
        (
            "approve_subset",
            "Candidate approves a two-Supervisor subset",
            "Persist the two selected Supervisors, not the entire proposed set.",
        ),
        (
            "request_more",
            "Candidate revises regions and requests more research",
            "Apply the Germany region revision to the next planning input, then pause for "
            "review without saving a shortlist.",
        ),
        (
            "reject_then_approve",
            "Candidate rejects one Supervisor before approving two others",
            "Retain the rejection, exclude that Supervisor from the new proposal, and save "
            "only the two explicitly approved Supervisors.",
        ),
        (
            "review_timeout",
            "Independent reviewer request fails",
            "A scripted Nebius invocation failure preserves the original score, lowers "
            "confidence, flags review unavailable, and still reaches Candidate review.",
        ),
        (
            "review_malformed",
            "Independent reviewer returns malformed structured output",
            "A scripted structured-output failure preserves the original score with reduced "
            "confidence and review unavailable; the graph must not crash.",
        ),
    )
    for graph_case, title, rationale in definitions:
        completed = graph_case in {"approve_one", "approve_subset", "reject_then_approve"}
        shortlisted = {
            "approve_one": proposal[:1],
            "approve_subset": proposal[:2],
            "reject_then_approve": proposal[1:3],
        }.get(graph_case, ())
        expected = EvaluationExpectation.model_validate(
            {
                **base.expected.model_dump(),
                "expected_interrupted": not completed,
                "expected_review_status": (
                    ReviewStatus.COMPLETED if completed else ReviewStatus.PROPOSED
                ),
                "expected_review_outcome": (
                    CandidateReviewOutcome.APPROVE
                    if completed
                    else CandidateReviewOutcome.REQUEST_MORE
                    if graph_case == "request_more"
                    else CandidateReviewOutcome.AWAITING_REVIEW
                ),
                "expected_shortlisted_supervisor_ids": shortlisted,
                "expected_rejected_supervisor_ids": (
                    proposal[:1] if graph_case == "reject_then_approve" else ()
                ),
                "expected_proposed_supervisor_ids": (
                    (*proposal[1:], replacement_id)
                    if graph_case == "reject_then_approve"
                    else proposal
                ),
                "expected_independent_reviews": (
                    (
                        IndependentReviewExpectation(
                            supervisor_id=proposal[0],
                            review_status=IndependentReviewStatus.UNAVAILABLE,
                            effective_score=87,
                            effective_confidence=EvidenceConfidence.MEDIUM,
                            requires_candidate_attention=True,
                        ),
                    )
                    if graph_case in {"review_timeout", "review_malformed"}
                    else ()
                ),
            }
        )
        scenario = EvaluationScenario(
            scenario_id=f"draft-graph-{graph_case.replace('_', '-')}",
            title=title,
            description=rationale,
            target=EvaluationTargetKind.GRAPH_FAKE,
            tags=("application:scholarpath", f"scenario-version:{DRAFT_SCENARIO_VERSION}"),
            splits=("graph-fake",),
            candidate_preferences=base.candidate_preferences,
            config={"graph_case": graph_case},
            expected=expected,
        )
        cases.append(
            _new_case(
                scenario,
                DraftScenarioType.KNOWN_FAILURE
                if graph_case.startswith("review_")
                else DraftScenarioType.HAPPY,
                "src/evaluation/targets.py:fake_end_to_end_target",
            )
        )
    return tuple(cases)


def build_evaluation_draft() -> EvaluationDraft:
    """Build the review manifest without running targets, models, or network clients."""
    return EvaluationDraft(
        dataset_name=DRAFT_DATASET_NAME,
        draft_version=DRAFT_SCENARIO_VERSION,
        cases=(*_retained_cases(), *_evidence_cases(), *_graph_cases()),
    )
