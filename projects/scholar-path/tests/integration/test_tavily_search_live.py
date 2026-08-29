"""Explicitly opted-in live smoke test for the official Tavily integration."""

import os

import pytest
from pydantic import SecretStr

from scholarpath.config import TavilySearchConfiguration
from scholarpath.tools import TavilySearchAdapter

RUN_LIVE_TESTS = os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").casefold() == "true"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE_TESTS or not TAVILY_API_KEY,
    reason="Set SCHOLARPATH_RUN_LIVE_TESTS=true and TAVILY_API_KEY for this live test.",
)
def test_live_tavily_search_returns_normalized_results() -> None:
    """Exercise one bounded Tavily request without applying Supervisor reasoning."""
    assert TAVILY_API_KEY is not None
    configuration = TavilySearchConfiguration(
        api_key=SecretStr(TAVILY_API_KEY),
        timeout_seconds=20,
        result_count=3,
    )

    results = TavilySearchAdapter(configuration).search(
        "site:edu professor enterprise architecture university profile"
    )

    assert results
    assert len(results) <= 3
    assert all(result.originating_query for result in results)
