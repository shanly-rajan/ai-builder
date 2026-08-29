"""Explicitly opted-in live smoke test for the official Tavily Extract integration."""

import os

import pytest
from pydantic import SecretStr

from scholarpath.config import TavilyExtractionConfiguration
from scholarpath.tools.tavily_extraction import TavilyExtractionAdapter

RUN_LIVE_TESTS = os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").casefold() == "true"
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE_TESTS or not TAVILY_API_KEY,
    reason="Set SCHOLARPATH_RUN_LIVE_TESTS=true and TAVILY_API_KEY for this live test.",
)
def test_live_tavily_extract_returns_bounded_normalized_content() -> None:
    """Exercise one bounded Tavily extraction without interpreting page content."""
    assert TAVILY_API_KEY is not None
    configuration = TavilyExtractionConfiguration(
        api_key=SecretStr(TAVILY_API_KEY),
        provider_timeout_seconds=20,
        request_timeout_seconds=25,
        extract_depth="basic",
        max_content_characters=10_000,
    )

    result = TavilyExtractionAdapter(configuration).extract(
        "https://docs.tavily.com/documentation/api-reference/endpoint/extract"
    )

    assert result.content
    assert len(result.content) <= configuration.max_content_characters
    assert result.source_url.scheme == "https"
    assert result.retrieved_at.utcoffset() is not None
