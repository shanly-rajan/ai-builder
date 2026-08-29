"""Deterministic synthesis of evidence-backed Supervisor recommendations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from fractions import Fraction

from ..domain import (
    EvidenceConfidence,
    IndependentReviewStatus,
    ProposedSupervisorRecommendation,
    ProposedSupervisorShortlist,
    ReconciledResearchFitAssessment,
    ResearchFitAssessment,
    ResearchFitComponentAssessment,
    SupervisorLifecycleStatus,
    VerifiedSupervisor,
)

_CONFIDENCE_RANK = {
    EvidenceConfidence.HIGH: 3,
    EvidenceConfidence.MEDIUM: 2,
    EvidenceConfidence.LOW: 1,
}
_ACADEMIC_TITLE_PATTERN = re.compile(
    r"^(?:associate professor|assistant professor|professor|prof\.?|dr\.?)\s+"
)


def _normalized_supervisor_name(value: str) -> str:
    """Normalize title, punctuation, case, and whitespace for stable ordering."""
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = _ACADEMIC_TITLE_PATTERN.sub("", normalized)
    return " ".join(re.sub(r"[_\W]+", " ", normalized).split())


def _unique_text(values: Iterable[str]) -> tuple[str, ...]:
    """Remove case-and-whitespace duplicates while retaining first-seen wording."""
    unique: list[str] = []
    seen: set[str] = set()
    for value in values:
        key = " ".join(value.casefold().split())
        if key in seen:
            continue
        seen.add(key)
        unique.append(value)
    return tuple(unique)


def _components(
    assessment: ResearchFitAssessment,
) -> tuple[tuple[int, int, ResearchFitComponentAssessment], ...]:
    """Return component position, configured weight, and evaluated component."""
    return (
        (
            0,
            assessment.rubric.topic_alignment,
            assessment.breakdown.topic_alignment,
        ),
        (
            1,
            assessment.rubric.methodological_alignment,
            assessment.breakdown.methodological_alignment,
        ),
        (
            2,
            assessment.rubric.research_orientation_alignment,
            assessment.breakdown.research_orientation_alignment,
        ),
        (
            3,
            assessment.rubric.recent_research_alignment,
            assessment.breakdown.recent_research_alignment,
        ),
        (
            4,
            assessment.rubric.practical_constraint_alignment,
            assessment.breakdown.practical_constraint_alignment,
        ),
    )


def _strengths(
    assessment: ResearchFitAssessment,
    independent_review: ReconciledResearchFitAssessment | None = None,
) -> tuple[str, ...]:
    """Select strong rationales only when review retained all of their citations."""
    if (
        independent_review is not None
        and independent_review.review_status is IndependentReviewStatus.REVISED
        and independent_review.requires_candidate_attention
    ):
        return (
            "Independent review requires Candidate attention before relying on the "
            "initial Research Fit strengths.",
        )
    unsupported_ids = (
        set(independent_review.unsupported_claim_ids) if independent_review is not None else set()
    )
    scored = [
        (Fraction(component.score, weight), position, component.rationale)
        for position, weight, component in _components(assessment)
        if component.score > 0 and unsupported_ids.isdisjoint(component.supporting_evidence_ids)
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    strengths = _unique_text(item[2] for item in scored)
    if not strengths:
        return ("No evidence-backed Research Fit strengths were identified.",)
    return strengths[:3]


def _concerns(
    supervisor: VerifiedSupervisor,
    assessment: ResearchFitAssessment,
    independent_review: ReconciledResearchFitAssessment | None = None,
) -> tuple[str, ...]:
    """Combine recorded concerns and evidence gaps without changing availability."""
    evidence_gaps = (
        component.evidence_gap
        for _, _, component in _components(assessment)
        if component.evidence_gap is not None
    )
    review_concerns: tuple[str, ...] = ()
    if independent_review is not None and (
        independent_review.review_status is IndependentReviewStatus.UNAVAILABLE
        or independent_review.requires_candidate_attention
        or bool(independent_review.unsupported_claim_ids)
    ):
        attention = (
            ("Independent review requires Candidate attention.",)
            if independent_review.requires_candidate_attention
            else ()
        )
        review_concerns = (independent_review.critique, *attention)
    return _unique_text(
        (
            *assessment.concerns,
            *evidence_gaps,
            *supervisor.verification_concerns,
            *review_concerns,
        )
    )


class ShortlistSynthesisAgent:
    """Rank Verified Supervisors and create a proposal for Candidate review."""

    def __init__(self, max_results: int = 5) -> None:
        if isinstance(max_results, bool) or not isinstance(max_results, int):
            raise ValueError("max_results must be an integer between 1 and 5")
        if not 1 <= max_results <= 5:
            raise ValueError("max_results must be an integer between 1 and 5")
        self._max_results = max_results

    def synthesize(
        self,
        candidate_id: str,
        verified_supervisors: Iterable[VerifiedSupervisor],
        assessments: Iterable[ResearchFitAssessment],
        generated_at: datetime,
        independent_reviews: Iterable[ReconciledResearchFitAssessment] = (),
    ) -> ProposedSupervisorShortlist:
        """Build a stable proposal without moving any Supervisor through the lifecycle."""
        supervisors_by_id: dict[str, VerifiedSupervisor] = {}
        for supervisor in verified_supervisors:
            if supervisor.status is not SupervisorLifecycleStatus.VERIFIED:
                continue
            if supervisor.supervisor_id in supervisors_by_id:
                raise ValueError("Verified Supervisor identifiers must be unique")
            supervisors_by_id[supervisor.supervisor_id] = supervisor

        assessments_by_id: dict[str, ResearchFitAssessment] = {}
        for assessment in assessments:
            if assessment.supervisor_id in assessments_by_id:
                raise ValueError("Research Fit assessment Supervisor identifiers must be unique")
            assessments_by_id[assessment.supervisor_id] = assessment

        reviews_by_id: dict[str, ReconciledResearchFitAssessment] = {}
        for review in independent_reviews:
            if review.supervisor_id in reviews_by_id:
                raise ValueError("Independent-review Supervisor identifiers must be unique")
            reviewed_assessment = assessments_by_id.get(review.supervisor_id)
            if reviewed_assessment is None or review.initial_assessment != reviewed_assessment:
                raise ValueError(
                    "Every independent review must match its initial Research Fit assessment"
                )
            reviews_by_id[review.supervisor_id] = review

        ranked_pairs = [
            (
                supervisor,
                assessments_by_id[supervisor_id],
                reviews_by_id.get(supervisor_id),
            )
            for supervisor_id, supervisor in supervisors_by_id.items()
            if supervisor_id in assessments_by_id
        ]
        ranked_pairs.sort(
            key=lambda item: (
                -(item[2].effective_score if item[2] is not None else item[1].overall_score),
                -_CONFIDENCE_RANK[
                    item[2].effective_confidence if item[2] is not None else item[1].confidence
                ],
                _normalized_supervisor_name(item[0].full_name),
                item[0].supervisor_id,
            )
        )
        selected = ranked_pairs[: self._max_results]
        if not selected:
            raise ValueError(
                "A proposed shortlist requires at least one Verified Supervisor with "
                "a matching Research Fit assessment"
            )

        recommendations = tuple(
            ProposedSupervisorRecommendation(
                rank=rank,
                supervisor=supervisor,
                assessment=assessment,
                strengths=_strengths(assessment, independent_review),
                concerns=_concerns(supervisor, assessment, independent_review),
                availability_status=supervisor.availability_status,
                evidence_confidence=(
                    independent_review.effective_confidence
                    if independent_review is not None
                    else assessment.confidence
                ),
                independent_review=independent_review,
            )
            for rank, (supervisor, assessment, independent_review) in enumerate(selected, start=1)
        )
        score_label = (
            "independently reconciled Research Fit Score" if reviews_by_id else "Research Fit Score"
        )
        return ProposedSupervisorShortlist(
            candidate_id=candidate_id,
            recommendations=recommendations,
            generated_at=generated_at,
            summary=(
                f"Proposed {len(recommendations)} evidence-backed Supervisor "
                f"recommendation(s), ranked by {score_label}, "
                "evidence confidence, "
                "and normalized name. Candidate approval is required before lifecycle change."
            ),
        )
