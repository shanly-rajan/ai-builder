"""Network-free tests for the official langchain-tavily adapter boundary."""

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langchain_core.tools import ToolException
from pydantic import SecretStr

from scholarpath.config import TavilySearchConfiguration
from scholarpath.tools.supervisor_search import (
    InvalidSupervisorSearchQueryError,
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
    SupervisorSearchPort,
)
from scholarpath.tools.tavily_search import TavilySearchAdapter


class FakeAsyncTavilyTool:
    """Record async invocations and deterministically return, fail, or wait."""

    def __init__(
        self,
        response: object,
        *,
        error: Exception | None = None,
        delay_seconds: float = 0.0,
    ) -> None:
        self.response = response
        self.error = error
        self.delay_seconds = delay_seconds
        self.calls: list[dict[str, object]] = []
        self.cancelled = False

    async def ainvoke(self, input: dict[str, object]) -> object:
        self.calls.append(input)
        try:
            if self.delay_seconds:
                await asyncio.sleep(self.delay_seconds)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.error is not None:
            raise self.error
        return self.response


def _configuration(**overrides: object) -> TavilySearchConfiguration:
    return TavilySearchConfiguration.model_validate(
        {
            "api_key": SecretStr("not-a-real-tavily-secret"),
            "timeout_seconds": 0.25,
            "result_count": 5,
            **overrides,
        }
    )


def _adapter(
    response: object,
    *,
    error: Exception | None = None,
    delay_seconds: float = 0.0,
    **configuration_overrides: object,
) -> tuple[TavilySearchAdapter, FakeAsyncTavilyTool]:
    tool = FakeAsyncTavilyTool(response, error=error, delay_seconds=delay_seconds)
    return (
        TavilySearchAdapter(
            _configuration(**configuration_overrides),
            tool=tool,
        ),
        tool,
    )


def test_production_factory_uses_public_official_tool_and_minimal_search_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_tool = FakeAsyncTavilyTool({"results": []})

    def fake_factory(**kwargs: object) -> FakeAsyncTavilyTool:
        captured.update(kwargs)
        return fake_tool

    monkeypatch.setattr("scholarpath.tools.tavily_search.TavilySearch", fake_factory)

    adapter = TavilySearchAdapter(_configuration(result_count=7))

    assert adapter.search("enterprise architecture university professor") == ()
    assert captured == {
        "tavily_api_key": "not-a-real-tavily-secret",
        "max_results": 7,
        "topic": "general",
        "search_depth": "basic",
        "include_answer": False,
        "include_raw_content": False,
        "include_images": False,
        "auto_parameters": False,
        "handle_tool_error": False,
    }
    assert "timeout" not in captured


def test_exact_query_is_invoked_once_and_results_are_normalized() -> None:
    query = "responsible AI supervisor university profile"
    adapter, tool = _adapter(
        {
            "query": query,
            "results": [
                {
                    "url": "https://example.edu/people/dr-jordan-lee",
                    "title": "Dr Jordan Lee | Example University",
                    "content": "Associate professor researching responsible AI.",
                    "score": 0.93,
                    "raw_content": "content that the adapter must not preserve",
                },
                {
                    "url": "https://example.edu/news/research-update",
                    "title": "Research update",
                    "content": "A recent research publication.",
                    "published_date": "Tue, 11 Mar 2025 17:00:00 GMT",
                },
            ],
            "response_time": 0.42,
        }
    )

    results = adapter.search(query)

    assert tool.calls == [{"query": query}]
    assert len(results) == 2
    assert str(results[0].url) == "https://example.edu/people/dr-jordan-lee"
    assert results[0].title == "Dr Jordan Lee | Example University"
    assert results[0].description == "Associate professor researching responsible AI."
    assert results[0].publication_date is None
    assert results[1].publication_date is not None
    assert results[1].publication_date.isoformat() == "2025-03-11T17:00:00+00:00"
    assert all(result.originating_query == query for result in results)
    assert all("raw_content" not in result.model_dump() for result in results)


@pytest.mark.parametrize(
    "published_date",
    ["2026-07-04T10:15:00Z", "2026-07-04T12:15:00+02:00"],
)
def test_iso_publication_dates_are_normalized(published_date: str) -> None:
    adapter, _ = _adapter(
        {
            "results": [
                {
                    "url": "https://example.edu/research",
                    "title": "Research",
                    "content": "Recent research.",
                    "published_date": published_date,
                }
            ]
        }
    )

    result = adapter.search("recent research")[0]

    assert result.publication_date is not None
    assert result.publication_date.utcoffset() is not None


def test_empty_results_return_an_empty_tuple() -> None:
    adapter, _ = _adapter({"results": []})

    assert adapter.search("academic profiles") == ()


def test_official_no_results_tool_error_is_normalized_to_empty_results() -> None:
    adapter, _ = _adapter(
        {},
        error=ToolException(
            "No search results found for 'academic profiles'. Try modifying the query."
        ),
    )

    assert adapter.search("academic profiles") == ()


def test_other_tool_errors_are_sanitized_non_retryable_provider_errors() -> None:
    adapter, _ = _adapter({}, error=ToolException("secret tool failure"))

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value.category is SearchErrorCategory.PROVIDER
    assert captured.value.retryable is False
    assert "secret tool failure" not in str(captured.value)


def test_results_are_capped_by_the_configured_limit() -> None:
    adapter, _ = _adapter(
        {
            "results": [
                {
                    "url": f"https://example.edu/people/{index}",
                    "title": f"Professor {index}",
                    "content": "Academic profile.",
                }
                for index in range(4)
            ]
        },
        result_count=2,
    )

    assert len(adapter.search("academic profiles")) == 2


def test_application_timeout_cancels_the_async_tool_call() -> None:
    adapter, tool = _adapter(
        {"results": []},
        delay_seconds=0.1,
        timeout_seconds=0.001,
    )

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value.provider is SearchProvider.TAVILY
    assert captured.value.category is SearchErrorCategory.TIMEOUT
    assert captured.value.retryable is True
    assert captured.value.status_code is None
    assert tool.cancelled is True


@pytest.mark.parametrize(
    ("provider_error", "category", "retryable", "status_code"),
    [
        (
            ValueError("Error 401: unauthorized secret-response-body"),
            SearchErrorCategory.AUTHENTICATION,
            False,
            401,
        ),
        (
            ValueError("Error 403: forbidden secret-response-body"),
            SearchErrorCategory.AUTHENTICATION,
            False,
            403,
        ),
        (
            ValueError("Error 429: rate limited secret-response-body"),
            SearchErrorCategory.RATE_LIMIT,
            True,
            429,
        ),
        (
            ValueError("Error 432: quota secret-response-body"),
            SearchErrorCategory.QUOTA,
            False,
            432,
        ),
        (
            ValueError("Error 400: invalid secret-response-body"),
            SearchErrorCategory.INVALID_REQUEST,
            False,
            400,
        ),
        (
            ValueError("Error 500: provider secret-response-body"),
            SearchErrorCategory.PROVIDER,
            True,
            500,
        ),
        (
            ValueError("Error 504: timeout secret-response-body"),
            SearchErrorCategory.TIMEOUT,
            True,
            504,
        ),
    ],
)
def test_official_error_payload_is_mapped_and_sanitized(
    provider_error: Exception,
    category: SearchErrorCategory,
    retryable: bool,
    status_code: int,
) -> None:
    adapter, _ = _adapter({"error": provider_error})

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value.provider is SearchProvider.TAVILY
    assert captured.value.category is category
    assert captured.value.retryable is retryable
    assert captured.value.status_code == status_code
    assert "secret-response-body" not in str(captured.value)


def test_transport_error_returned_by_tool_is_retryable_and_sanitized() -> None:
    adapter, _ = _adapter({"error": OSError("connection secret-response-body")})

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value.category is SearchErrorCategory.TRANSPORT
    assert captured.value.retryable is True
    assert "secret-response-body" not in str(captured.value)


def test_timeout_error_returned_by_tool_is_retryable() -> None:
    adapter, _ = _adapter({"error": TimeoutError("secret-response-body")})

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value.category is SearchErrorCategory.TIMEOUT
    assert captured.value.retryable is True
    assert "secret-response-body" not in str(captured.value)


def test_pretyped_error_raised_by_tool_is_preserved() -> None:
    original = SearchProviderError(
        "already sanitized",
        provider=SearchProvider.TAVILY,
        category=SearchErrorCategory.RATE_LIMIT,
        retryable=True,
        status_code=429,
    )
    adapter, _ = _adapter({}, error=original)

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value is original


def test_pretyped_error_returned_by_tool_is_preserved() -> None:
    original = SearchProviderError(
        "already sanitized",
        provider=SearchProvider.TAVILY,
        category=SearchErrorCategory.PROVIDER,
        retryable=True,
    )
    adapter, _ = _adapter({"error": original})

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value is original


def test_unknown_tool_failure_is_a_retryable_provider_error() -> None:
    adapter, _ = _adapter({}, error=RuntimeError("secret-response-body"))

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value.category is SearchErrorCategory.PROVIDER
    assert captured.value.retryable is True
    assert "secret-response-body" not in str(captured.value)


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {},
        {"results": None},
        {"results": {}},
        {"results": ["not-an-object"]},
        {"results": [{"title": "Missing URL", "content": "Profile"}]},
        {
            "results": [
                {
                    "url": "https://example.edu/profile",
                    "title": "Professor Lee",
                    "content": object(),
                }
            ]
        },
        {
            "results": [
                {
                    "url": "https://example.edu/profile",
                    "title": "Professor Lee",
                    "content": "Profile",
                    "published_date": "not-a-date",
                }
            ]
        },
        {
            "results": [
                {
                    "url": "https://example.edu/profile",
                    "title": "Professor Lee",
                    "content": "Profile",
                    "published_date": 20260829,
                }
            ]
        },
        {"error": None},
    ],
)
def test_malformed_tool_output_is_a_non_retryable_contract_error(payload: object) -> None:
    adapter, _ = _adapter(payload)

    with pytest.raises(SearchProviderError) as captured:
        adapter.search("academic profiles")

    assert captured.value.provider is SearchProvider.TAVILY
    assert captured.value.category is SearchErrorCategory.RESPONSE_CONTRACT
    assert captured.value.retryable is False


@pytest.mark.parametrize(
    ("published_date", "expected"),
    [
        (datetime(2026, 8, 29, 8, 30, tzinfo=UTC), "2026-08-29T08:30:00+00:00"),
        ("   ", None),
    ],
)
def test_datetime_objects_and_blank_dates_are_normalized(
    published_date: object,
    expected: str | None,
) -> None:
    adapter, _ = _adapter(
        {
            "results": [
                {
                    "url": "https://example.edu/profile",
                    "title": "Professor Lee",
                    "content": "Profile",
                    "published_date": published_date,
                }
            ]
        }
    )

    actual = adapter.search("academic profiles")[0].publication_date

    assert (actual.isoformat() if actual else None) == expected


def test_blank_query_is_rejected_before_tool_invocation() -> None:
    adapter, tool = _adapter({"results": []})

    with pytest.raises(InvalidSupervisorSearchQueryError):
        adapter.search("   ")

    assert tool.calls == []


def test_adapter_satisfies_the_provider_neutral_search_port() -> None:
    adapter, _ = _adapter({"results": []})

    assert isinstance(adapter, SupervisorSearchPort)


def test_source_uses_only_the_supported_public_tavily_import() -> None:
    source_path = Path(__file__).parents[3] / "src" / "tools" / "tavily_search.py"
    source = source_path.read_text(encoding="utf-8")

    assert "from langchain_tavily import TavilySearch" in source
    assert "langchain_community" not in source
    assert "langchain_tavily._" not in source
