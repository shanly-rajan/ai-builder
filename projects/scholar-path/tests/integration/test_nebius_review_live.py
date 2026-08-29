"""Optional live smoke test for Nebius independent Research Fit review."""

import os

import pytest

from scholarpath.agents.independent_review import IndependentReviewInput
from scholarpath.agents.nebius_review import NebiusReviewModelAdapter
from scholarpath.config import load_nebius_review_settings
from scholarpath.domain import IndependentReviewDecision
from tests.fixtures import (
    make_candidate_profile,
    make_research_fit_assessment,
    make_verified_supervisor,
)


def _live_tests_enabled() -> bool:
    return os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.live
def test_nebius_structured_independent_review_smoke() -> None:
    if not _live_tests_enabled():
        pytest.skip("Set SCHOLARPATH_RUN_LIVE_TESTS=true to opt in to live tests")
    settings = load_nebius_review_settings()
    if settings.api_key is None or not settings.api_key.get_secret_value().strip():
        pytest.skip("NEBIUS_API_KEY is required for the live independent-review smoke test")

    review_input = IndependentReviewInput.from_domain(
        make_candidate_profile(),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )
    result = NebiusReviewModelAdapter(settings.for_review_model()).review(review_input)

    assert result.decision in {
        IndependentReviewDecision.ACCEPT,
        IndependentReviewDecision.REVISE,
    }
    assert 0 <= result.recommended_score <= 100
    valid_evidence_ids = {claim.evidence_id for claim in review_input.evidence_claims}
    assert set(result.unsupported_claim_ids).issubset(valid_evidence_ids)
    assert set(result.overlooked_evidence_ids).issubset(valid_evidence_ids)
