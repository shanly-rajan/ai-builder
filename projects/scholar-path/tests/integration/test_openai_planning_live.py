"""Optional live smoke test for OpenAI structured research planning."""

import os

import pytest
from pydantic import SecretStr

from scholarpath.agents import OpenAIPlanningModelAdapter, ResearchPlanningAgent
from scholarpath.config import OpenAIPlanningConfiguration
from tests.fixtures import make_candidate_profile


def _live_tests_enabled() -> bool:
    return os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.live
def test_openai_structured_planning_smoke() -> None:
    if not _live_tests_enabled():
        pytest.skip("Set SCHOLARPATH_RUN_LIVE_TESTS=true to opt in to live tests")
    raw_api_key = os.getenv("OPENAI_API_KEY", "").strip()
    if not raw_api_key:
        pytest.skip("OPENAI_API_KEY is required for the live planning smoke test")

    adapter = OpenAIPlanningModelAdapter(
        OpenAIPlanningConfiguration(
            api_key=SecretStr(raw_api_key),
            model=os.getenv("OPENAI_PLANNING_MODEL", "gpt-5.4-mini"),
            timeout_seconds=60.0,
        )
    )

    plan = ResearchPlanningAgent(adapter).plan(
        make_candidate_profile(),
        (),
        target_regions=("South Africa", "United Kingdom", "Netherlands"),
        exclusions=("fully residential programmes",),
    )

    assert 4 <= len(plan.search_queries) <= 8
    assert all(query.purpose for query in plan.search_queries)
    assert all(query.target_source_types for query in plan.search_queries)
