"""Network-free tests for the official Tavily Extract adapter boundary."""

import asyncio
from datetime import UTC, datetime

import pytest
from langchain_core.tools import ToolException
from langchain_tavily import TavilyExtract as OfficialTavilyExtract
from langchain_tavily._utilities import TavilyExtractAPIWrapper
from pydantic import HttpUrl, SecretStr, ValidationError

from scholarpath.config import TavilyExtractionConfiguration
from scholarpath.tools.content_extraction import (
    ContentExtractionError,
    ContentExtractionErrorCategory,
    ContentExtractionPort,
    ContentExtractionProvider,
    ExtractedContent,
)
from scholarpath.tools.tavily_extraction import TavilyExtractionAdapter

SOURCE_URL = "https://example.edu/people/dr-jordan-lee"
RETRIEVED_AT = datetime(2026, 8, 29, 12, 30, tzinfo=UTC)


class FakeAsyncTavilyExtractTool:
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


def _configuration(**overrides: object) -> TavilyExtractionConfiguration:
    return TavilyExtractionConfiguration.model_validate(
        {
            "api_key": SecretStr("not-a-real-tavily-secret"),
            "provider_timeout_seconds": 20,
            "request_timeout_seconds": 25,
            "extract_depth": "advanced",
            "max_content_characters": 50_000,
            **overrides,
        }
    )


def _success_payload(
    *,
    url: object = SOURCE_URL,
    content: object = "# Dr Jordan Lee\nAssociate Professor of Information Systems.",
) -> dict[str, object]:
    return {
        "results": [{"url": url, "raw_content": content, "images": []}],
        "failed_results": [],
        "response_time": 0.4,
    }


def _adapter(
    response: object,
    *,
    error: Exception | None = None,
    delay_seconds: float = 0.0,
    **configuration_overrides: object,
) -> tuple[TavilyExtractionAdapter, FakeAsyncTavilyExtractTool]:
    tool = FakeAsyncTavilyExtractTool(
        response,
        error=error,
        delay_seconds=delay_seconds,
    )
    return (
        TavilyExtractionAdapter(
            _configuration(**configuration_overrides),
            tool=tool,
            clock=lambda: RETRIEVED_AT,
        ),
        tool,
    )


def test_production_factory_uses_official_tool_with_fixed_content_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_tool = FakeAsyncTavilyExtractTool(_success_payload())

    def fake_factory(**kwargs: object) -> FakeAsyncTavilyExtractTool:
        captured.update(kwargs)
        return fake_tool

    monkeypatch.setattr("scholarpath.tools.tavily_extraction.TavilyExtract", fake_factory)

    adapter = TavilyExtractionAdapter(
        _configuration(extract_depth="basic"),
        clock=lambda: RETRIEVED_AT,
    )
    result = adapter.extract(SOURCE_URL)

    assert result.content.startswith("# Dr Jordan Lee")
    assert captured == {
        "tavily_api_key": "not-a-real-tavily-secret",
        "extract_depth": "basic",
        "include_images": False,
        "include_favicon": False,
        "format": "markdown",
        "include_usage": False,
        "handle_tool_error": False,
    }


def test_exactly_one_url_and_provider_timeout_are_sent() -> None:
    adapter, tool = _adapter(_success_payload())

    adapter.extract(SOURCE_URL)

    assert tool.calls == [{"urls": [SOURCE_URL], "timeout": 20}]


def test_pinned_official_tool_forwards_timeout_and_fixed_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}

    async def fake_raw_results_async(
        _wrapper: TavilyExtractAPIWrapper,
        **kwargs: object,
    ) -> dict[str, object]:
        captured.update(kwargs)
        return _success_payload()

    monkeypatch.setattr(
        TavilyExtractAPIWrapper,
        "raw_results_async",
        fake_raw_results_async,
    )
    official_tool = OfficialTavilyExtract(
        apiwrapper=TavilyExtractAPIWrapper(tavily_api_key=SecretStr("not-a-real-tavily-secret")),
        extract_depth="advanced",
        include_images=False,
        include_favicon=False,
        format="markdown",
        include_usage=False,
        handle_tool_error=False,
    )
    adapter = TavilyExtractionAdapter(
        _configuration(provider_timeout_seconds=7, request_timeout_seconds=8),
        tool=official_tool,
        clock=lambda: RETRIEVED_AT,
    )

    adapter.extract(SOURCE_URL)

    assert captured == {
        "urls": [SOURCE_URL],
        "extract_depth": "advanced",
        "include_images": False,
        "include_favicon": False,
        "format": "markdown",
        "include_usage": False,
        "query": None,
        "chunks_per_source": None,
        "timeout": 7,
    }


def test_successful_content_is_normalized_with_aware_retrieval_time() -> None:
    adapter, _ = _adapter(_success_payload())

    result = adapter.extract(HttpUrl(SOURCE_URL))

    assert isinstance(result, ExtractedContent)
    assert str(result.source_url) == SOURCE_URL
    assert result.content == "# Dr Jordan Lee\nAssociate Professor of Information Systems."
    assert result.retrieved_at == RETRIEVED_AT
    assert result.retrieved_at.utcoffset() is not None
    assert result.content_truncated is False


def test_returned_source_url_is_preserved_after_provider_redirect() -> None:
    canonical_url = "https://profiles.example.edu/jordan-lee"
    adapter, _ = _adapter(_success_payload(url=canonical_url))

    result = adapter.extract(SOURCE_URL)

    assert str(result.source_url) == canonical_url


def test_content_is_capped_deterministically_and_marked_truncated() -> None:
    content = "x" * 1_005
    adapter, _ = _adapter(
        _success_payload(content=content),
        max_content_characters=1_000,
    )

    result = adapter.extract(SOURCE_URL)

    assert result.content == "x" * 1_000
    assert result.content_truncated is True


def test_adapter_satisfies_the_provider_neutral_port() -> None:
    adapter, _ = _adapter(_success_payload())

    assert isinstance(adapter, ContentExtractionPort)


def test_extracted_content_rejects_naive_retrieval_time() -> None:
    with pytest.raises(ValidationError):
        ExtractedContent(
            source_url=HttpUrl(SOURCE_URL),
            content="profile",
            retrieved_at=datetime(2026, 8, 29, 12, 30),
        )


def test_extracted_content_rejects_whitespace_only_content() -> None:
    with pytest.raises(ValidationError):
        ExtractedContent(
            source_url=HttpUrl(SOURCE_URL),
            content="   ",
            retrieved_at=RETRIEVED_AT,
        )


@pytest.mark.parametrize(
    "invalid_url",
    [
        "",
        "not-a-url",
        "ftp://example.edu/profile",
        "https://user:password@example.edu/profile",
        "http://localhost/profile",
        "http://research.local/profile",
        "http://127.0.0.1/profile",
        "http://169.254.169.254/latest/meta-data",
        "http://[::1]/profile",
    ],
)
def test_invalid_url_is_rejected_before_invoking_provider(invalid_url: str) -> None:
    adapter, tool = _adapter(_success_payload())

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(invalid_url)

    assert captured.value.category is ContentExtractionErrorCategory.INVALID_REQUEST
    assert captured.value.retryable is False
    assert tool.calls == []


def test_application_timeout_cancels_async_tool_call() -> None:
    adapter, tool = _adapter(
        _success_payload(),
        delay_seconds=1.1,
        provider_timeout_seconds=1,
        request_timeout_seconds=1.001,
    )

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.provider is ContentExtractionProvider.TAVILY
    assert captured.value.category is ContentExtractionErrorCategory.TIMEOUT
    assert captured.value.retryable is True
    assert tool.cancelled is True


def test_all_failed_tool_exception_is_sanitized_for_alternate_source_routing() -> None:
    adapter, _ = _adapter(
        {},
        error=ToolException(f"No extracted results for {SOURCE_URL}: secret provider detail"),
    )

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.category is ContentExtractionErrorCategory.EXTRACTION_FAILED
    assert captured.value.retryable is True
    assert "secret provider detail" not in str(captured.value)


@pytest.mark.parametrize(
    ("provider_error", "category", "retryable", "status_code"),
    [
        (
            ValueError("Error 401: secret provider body"),
            ContentExtractionErrorCategory.AUTHENTICATION,
            False,
            401,
        ),
        (
            ValueError("Error 403: secret provider body"),
            ContentExtractionErrorCategory.AUTHENTICATION,
            False,
            403,
        ),
        (
            ValueError("Error 429: secret provider body"),
            ContentExtractionErrorCategory.RATE_LIMIT,
            True,
            429,
        ),
        (
            ValueError("Error 432: secret provider body"),
            ContentExtractionErrorCategory.QUOTA,
            False,
            432,
        ),
        (
            ValueError("Error 433: secret provider body"),
            ContentExtractionErrorCategory.QUOTA,
            False,
            433,
        ),
        (
            ValueError("Error 408: secret provider body"),
            ContentExtractionErrorCategory.TIMEOUT,
            True,
            408,
        ),
        (
            ValueError("Error 504: secret provider body"),
            ContentExtractionErrorCategory.TIMEOUT,
            True,
            504,
        ),
        (
            ValueError("Error 400: secret provider body"),
            ContentExtractionErrorCategory.INVALID_REQUEST,
            False,
            400,
        ),
        (
            ValueError("Error 500: secret provider body"),
            ContentExtractionErrorCategory.PROVIDER,
            True,
            500,
        ),
    ],
)
def test_error_payload_is_mapped_to_sanitized_typed_failure(
    provider_error: object,
    category: ContentExtractionErrorCategory,
    retryable: bool,
    status_code: int,
) -> None:
    adapter, _ = _adapter({"error": provider_error})

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.category is category
    assert captured.value.retryable is retryable
    assert captured.value.status_code == status_code
    assert captured.value.source_url == SOURCE_URL
    assert "secret provider body" not in str(captured.value)


def test_raised_transport_error_is_mapped_without_provider_details() -> None:
    adapter, _ = _adapter({}, error=ConnectionError("secret host information"))

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.category is ContentExtractionErrorCategory.TRANSPORT
    assert captured.value.retryable is True
    assert "secret host information" not in str(captured.value)


def test_unknown_provider_error_remains_retryable_and_sanitized() -> None:
    adapter, _ = _adapter({"error": RuntimeError("secret unknown failure")})

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.category is ContentExtractionErrorCategory.PROVIDER
    assert captured.value.retryable is True
    assert "secret unknown failure" not in str(captured.value)


def test_null_error_value_is_a_non_retryable_response_contract_failure() -> None:
    adapter, _ = _adapter({"error": None})

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.category is ContentExtractionErrorCategory.RESPONSE_CONTRACT
    assert captured.value.retryable is False


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        {},
        {"results": [], "failed_results": {}},
        {"results": {}, "failed_results": []},
        {"results": ["not-an-object"], "failed_results": []},
        {
            "results": [
                {"url": SOURCE_URL, "raw_content": "one"},
                {"url": SOURCE_URL, "raw_content": "two"},
            ],
            "failed_results": [],
        },
        {
            "results": [{"url": SOURCE_URL, "raw_content": "profile"}],
            "failed_results": [{"url": SOURCE_URL}],
        },
        {"results": [{"url": "not-a-url", "raw_content": "profile"}], "failed_results": []},
        {
            "results": [
                {
                    "url": "https://user:password@example.edu/profile",
                    "raw_content": "profile",
                }
            ],
            "failed_results": [],
        },
        {
            "results": [{"url": "http://127.0.0.1/profile", "raw_content": "profile"}],
            "failed_results": [],
        },
    ],
)
def test_malformed_success_payload_is_a_response_contract_failure(payload: object) -> None:
    adapter, _ = _adapter(payload)

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.category is ContentExtractionErrorCategory.RESPONSE_CONTRACT
    assert captured.value.retryable is False


@pytest.mark.parametrize(
    "payload",
    [
        {"results": [], "failed_results": [{"url": SOURCE_URL}]},
        {"results": [], "failed_results": []},
        {"results": [{"url": SOURCE_URL, "raw_content": None}], "failed_results": []},
        {"results": [{"url": SOURCE_URL, "raw_content": "   "}], "failed_results": []},
    ],
)
def test_missing_page_content_is_a_retryable_extraction_failure(payload: object) -> None:
    adapter, _ = _adapter(payload)

    with pytest.raises(ContentExtractionError) as captured:
        adapter.extract(SOURCE_URL)

    assert captured.value.category is ContentExtractionErrorCategory.EXTRACTION_FAILED
    assert captured.value.retryable is True
