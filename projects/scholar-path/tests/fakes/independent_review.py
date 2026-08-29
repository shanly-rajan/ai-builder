"""Recording fake for deterministic offline independent Research Fit review."""

from collections.abc import Mapping, Sequence

from scholarpath.agents.independent_review import (
    IndependentReviewInput,
    IndependentReviewResult,
)
from scholarpath.domain import (
    EvidenceConfidence,
    IndependentReviewDecision,
)

type IndependentReviewModelOutcome = IndependentReviewResult | Exception


def make_accepted_review(
    review_input: IndependentReviewInput,
) -> IndependentReviewResult:
    """Accept the supplied assessment without changing score or evidence."""
    return IndependentReviewResult(
        decision=IndependentReviewDecision.ACCEPT,
        recommended_score=review_input.initial_assessment.overall_score,
        unsupported_claim_ids=[],
        overlooked_evidence_ids=[],
        confidence=review_input.initial_assessment.confidence,
        critique="The assessment is supported by the supplied evidence.",
    )


def make_revised_review(
    review_input: IndependentReviewInput,
    *,
    recommended_score: int,
    unsupported_claim_ids: Sequence[str] = (),
    overlooked_evidence_ids: Sequence[str] = (),
    confidence: EvidenceConfidence = EvidenceConfidence.MEDIUM,
    critique: str = "The supplied evidence supports a revised Research Fit Score.",
) -> IndependentReviewResult:
    """Create a typed revision using only identifiers from the supplied input."""
    return IndependentReviewResult(
        decision=IndependentReviewDecision.REVISE,
        recommended_score=recommended_score,
        unsupported_claim_ids=list(unsupported_claim_ids),
        overlooked_evidence_ids=list(overlooked_evidence_ids),
        confidence=confidence,
        critique=critique,
    )


class FakeIndependentReviewModel:
    """Return structured review results without Nebius or a network call."""

    def __init__(
        self,
        outcomes: Mapping[str, Sequence[IndependentReviewModelOutcome]] | None = None,
    ) -> None:
        self._outcomes = {
            supervisor_id: list(items) for supervisor_id, items in (outcomes or {}).items()
        }
        self.inputs: list[IndependentReviewInput] = []

    @property
    def call_count(self) -> int:
        """Return the number of structured independent-review calls."""
        return len(self.inputs)

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        """Record one call, then return a scripted or accepting result."""
        self.inputs.append(review_input)
        scripted = self._outcomes.get(review_input.initial_assessment.supervisor_id)
        outcome = scripted.pop(0) if scripted else make_accepted_review(review_input)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
