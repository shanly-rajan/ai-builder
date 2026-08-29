"""Explicitly opted-in live smoke test for You.com Web Search."""

import os

import pytest
from pydantic import SecretStr

from scholarpath.config import YouSearchConfiguration
from scholarpath.tools import YouSearchAdapter

RUN_LIVE_TESTS = os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").casefold() == "true"
YDC_API_KEY = os.getenv("YDC_API_KEY")


@pytest.mark.live
@pytest.mark.skipif(
    not RUN_LIVE_TESTS or not YDC_API_KEY,
    reason="Set SCHOLARPATH_RUN_LIVE_TESTS=true and YDC_API_KEY for this live test.",
)
def test_live_you_search_returns_normalized_results() -> None:
    """Exercise one bounded live request without performing domain reasoning."""
    assert YDC_API_KEY is not None
    configuration = YouSearchConfiguration.model_validate(
        {
            "api_key": SecretStr(YDC_API_KEY),
            "endpoint": "https://ydc-index.io/v1/search",
            "timeout_seconds": 20,
            "result_count": 3,
        }
    )

    results = YouSearchAdapter(configuration).search(
        "site:edu professor enterprise architecture university profile"
    )

    assert results
    assert len(results) <= 3
    assert all(result.originating_query for result in results)
