"""Optional live smoke test for OpenAI structured Research Fit evaluation."""

import os

import pytest
from pydantic import SecretStr

from scholarpath.agents import OpenAIResearchFitAdapter, ResearchFitEvaluationAgent
from scholarpath.config import OpenAIResearchFitConfiguration
from scholarpath.domain import EvidenceClaimType, validate_research_fit_evidence
from tests.fixtures import make_candidate_profile, make_verified_supervisor


def _live_tests_enabled() -> bool:
    return os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.live
def test_openai_structured_research_fit_smoke() -> None:
    if not _live_tests_enabled():
        pytest.skip("Set SCHOLARPATH_RUN_LIVE_TESTS=true to opt in to live tests")
    raw_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not raw_api_key:
        pytest.skip("OPENAI_API_KEY is required for the live Research Fit smoke test")

    adapter = OpenAIResearchFitAdapter(
        OpenAIResearchFitConfiguration(
            api_key=SecretStr(raw_api_key),
            model=os.getenv("OPENAI_RESEARCH_FIT_MODEL", "gpt-5.4-mini"),
            timeout_seconds=60.0,
        )
    )
    supervisor = make_verified_supervisor(1)

    assessment = ResearchFitEvaluationAgent(adapter).evaluate(
        make_candidate_profile(),
        supervisor,
    )

    validate_research_fit_evidence(supervisor, assessment)
    assert 0 <= assessment.overall_score <= 100
    availability_ids = {
        claim.evidence_id
        for claim in supervisor.evidence
        if claim.claim_type is EvidenceClaimType.AVAILABILITY
    }
    assert availability_ids.isdisjoint(assessment.supporting_evidence_ids)
