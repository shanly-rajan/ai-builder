"""Deterministic synthesis of evidence-backed Supervisor recommendations."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime
from fractions import Fraction

from ..domain import (
    EvidenceConfidence,
    ProposedSupervisorRecommendation,
    ProposedSupervisorShortlist,
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


def _strengths(assessment: ResearchFitAssessment) -> tuple[str, ...]:
    """Select up to three strongest rationales by percentage of configured weight."""
    scored = [
        (Fraction(component.score, weight), position, component.rationale)
        for position, weight, component in _components(assessment)
        if component.score > 0
    ]
    scored.sort(key=lambda item: (-item[0], item[1]))
    strengths = _unique_text(item[2] for item in scored)
    if not strengths:
        return ("No evidence-backed Research Fit strengths were identified.",)
    return strengths[:3]


def _concerns(
    supervisor: VerifiedSupervisor,
    assessment: ResearchFitAssessment,
) -> tuple[str, ...]:
    """Combine recorded concerns and evidence gaps without changing availability."""
    evidence_gaps = (
        component.evidence_gap
        for _, _, component in _components(assessment)
        if component.evidence_gap is not None
    )
    return _unique_text(
        (
            *assessment.concerns,
            *evidence_gaps,
            *supervisor.verification_concerns,
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

        ranked_pairs = [
            (supervisor, assessments_by_id[supervisor_id])
            for supervisor_id, supervisor in supervisors_by_id.items()
            if supervisor_id in assessments_by_id
        ]
        ranked_pairs.sort(
            key=lambda item: (
                -item[1].overall_score,
                -_CONFIDENCE_RANK[item[1].confidence],
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
                strengths=_strengths(assessment),
                concerns=_concerns(supervisor, assessment),
                availability_status=supervisor.availability_status,
                evidence_confidence=assessment.confidence,
            )
            for rank, (supervisor, assessment) in enumerate(selected, start=1)
        )
        return ProposedSupervisorShortlist(
            candidate_id=candidate_id,
            recommendations=recommendations,
            generated_at=generated_at,
            summary=(
                f"Proposed {len(recommendations)} evidence-backed Supervisor "
                "recommendation(s), ranked by Research Fit Score, evidence confidence, "
                "and normalized name. Candidate approval is required before lifecycle change."
            ),
        )
