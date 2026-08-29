"""Cancellable transport adapter for the official Tavily Extract tool."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from ipaddress import ip_address
from typing import Protocol, cast

from langchain_core.tools import ToolException
from langchain_tavily import TavilyExtract
from pydantic import HttpUrl, TypeAdapter, ValidationError

from ..config import TavilyExtractionConfiguration
from .content_extraction import (
    ContentExtractionError,
    ContentExtractionErrorCategory,
    ContentExtractionPort,
    ContentExtractionProvider,
    ExtractedContent,
)

_STATUS_CODE_PATTERN = re.compile(r"\b(?:error|http)\s+(?P<status>\d{3})\b", re.IGNORECASE)
_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)


class AsyncTavilyExtractionTool(Protocol):
    """Narrow public async boundary implemented by TavilyExtract and test fakes."""

    async def ainvoke(self, input: dict[str, object]) -> object:
        """Invoke Tavily Extract for one provider payload."""
        ...


class _NoExtractedContentError(ValueError):
    """The provider processed a URL but returned no usable page content."""


def _utc_now() -> datetime:
    """Return an aware UTC retrieval timestamp."""
    return datetime.now(UTC)


class TavilyExtractionAdapter(ContentExtractionPort):
    """Normalize Tavily Extract responses without interpreting their content."""

    def __init__(
        self,
        configuration: TavilyExtractionConfiguration,
        *,
        tool: AsyncTavilyExtractionTool | None = None,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._configuration = configuration
        self._clock = clock or _utc_now
        self._tool = tool or cast(
            AsyncTavilyExtractionTool,
            TavilyExtract(
                tavily_api_key=configuration.api_key.get_secret_value(),
                extract_depth=configuration.extract_depth,
                include_images=False,
                include_favicon=False,
                format="markdown",
                include_usage=False,
                handle_tool_error=False,
            ),
        )

    def extract(self, source_url: str | HttpUrl) -> ExtractedContent:
        """Extract one URL within both provider and application deadlines."""
        try:
            requested_url = self._validate_public_url(source_url)
        except (TypeError, ValueError, ValidationError):
            raise self._error(
                "Content extraction requires a valid HTTP or HTTPS URL.",
                category=ContentExtractionErrorCategory.INVALID_REQUEST,
                retryable=False,
            ) from None

        normalized_url = str(requested_url)
        try:
            payload = asyncio.run(self._invoke_with_timeout(normalized_url))
        except TimeoutError:
            raise self._error(
                "Tavily Extract exceeded the configured application deadline.",
                category=ContentExtractionErrorCategory.TIMEOUT,
                retryable=True,
                source_url=normalized_url,
            ) from None
        except ToolException:
            raise self._error(
                "Tavily Extract returned no usable content for the requested URL.",
                category=ContentExtractionErrorCategory.EXTRACTION_FAILED,
                retryable=True,
                source_url=normalized_url,
            ) from None
        except ContentExtractionError:
            raise
        except Exception as error:
            raise self._map_provider_error(error, normalized_url) from None

        if isinstance(payload, Mapping) and "error" in payload:
            provider_error = payload["error"]
            if provider_error is None:
                raise self._contract_error(normalized_url)
            raise self._map_provider_error(provider_error, normalized_url) from None

        try:
            return self._normalize_payload(payload)
        except _NoExtractedContentError:
            raise self._error(
                "Tavily Extract returned no usable content for the requested URL.",
                category=ContentExtractionErrorCategory.EXTRACTION_FAILED,
                retryable=True,
                source_url=normalized_url,
            ) from None
        except (TypeError, ValueError, ValidationError):
            raise self._contract_error(normalized_url) from None

    async def _invoke_with_timeout(self, source_url: str) -> object:
        """Apply an application deadline outside Tavily's provider-side timeout."""
        async with asyncio.timeout(self._configuration.request_timeout_seconds):
            return await self._tool.ainvoke(
                {
                    "urls": [source_url],
                    "timeout": self._configuration.provider_timeout_seconds,
                }
            )

    def _normalize_payload(self, payload: object) -> ExtractedContent:
        """Validate the official response and cap content deterministically."""
        if not isinstance(payload, Mapping):
            raise TypeError("The Tavily Extract response root must be an object")
        if "results" not in payload or "failed_results" not in payload:
            raise TypeError("The Tavily Extract response is missing required result fields")

        results = payload["results"]
        failed_results = payload["failed_results"]
        if not isinstance(results, list) or not isinstance(failed_results, list):
            raise TypeError("Tavily Extract result fields must be lists")
        if not results:
            raise _NoExtractedContentError
        if failed_results:
            raise TypeError("A one-URL response cannot both succeed and fail")
        if len(results) != 1:
            raise TypeError("One extraction request must return exactly one result")

        item = results[0]
        if not isinstance(item, Mapping):
            raise TypeError("Every Tavily Extract result must be an object")

        source_url = self._validate_public_url(item.get("url"))
        raw_content = item.get("raw_content")
        if not isinstance(raw_content, str) or not raw_content.strip():
            raise _NoExtractedContentError

        maximum = self._configuration.max_content_characters
        content = raw_content[:maximum]
        if not content.strip():
            raise _NoExtractedContentError

        return ExtractedContent.model_validate(
            {
                "source_url": source_url,
                "content": content,
                "retrieved_at": self._clock(),
                "content_truncated": len(raw_content) > maximum,
            }
        )

    @staticmethod
    def _validate_public_url(value: object) -> HttpUrl:
        """Reject embedded credentials and clearly non-public extraction targets."""
        url = _HTTP_URL_ADAPTER.validate_python(value)
        if url.username is not None or url.password is not None:
            raise ValueError("Content extraction URLs must not contain credentials")

        host = url.host
        if host is None:
            raise ValueError("Content extraction URLs must include a host")
        normalized_host = host.casefold().strip("[]")
        if normalized_host == "localhost" or normalized_host.endswith((".localhost", ".local")):
            raise ValueError("Content extraction URLs must use a public host")

        try:
            address = ip_address(normalized_host)
        except ValueError:
            return url
        if not address.is_global:
            raise ValueError("Content extraction URLs must use a public IP address")
        return url

    @classmethod
    def _map_provider_error(cls, error: object, source_url: str) -> ContentExtractionError:
        """Convert provider details into stable, non-sensitive routing metadata."""
        if isinstance(error, ContentExtractionError):
            return error

        error_type_names = {error_type.__name__.casefold() for error_type in type(error).__mro__}
        if any("timeout" in name for name in error_type_names):
            return cls._error(
                "Tavily Extract exceeded its configured timeout.",
                category=ContentExtractionErrorCategory.TIMEOUT,
                retryable=True,
                source_url=source_url,
            )

        status_code = cls._status_code(error)
        if status_code in {401, 403}:
            return cls._error(
                "Tavily Extract authentication failed.",
                category=ContentExtractionErrorCategory.AUTHENTICATION,
                retryable=False,
                source_url=source_url,
                status_code=status_code,
            )
        if status_code == 429:
            return cls._error(
                "Tavily Extract was rate limited.",
                category=ContentExtractionErrorCategory.RATE_LIMIT,
                retryable=True,
                source_url=source_url,
                status_code=status_code,
            )
        if status_code in {432, 433}:
            return cls._error(
                "Tavily Extract quota is unavailable.",
                category=ContentExtractionErrorCategory.QUOTA,
                retryable=False,
                source_url=source_url,
                status_code=status_code,
            )
        if status_code in {408, 504}:
            return cls._error(
                "Tavily Extract exceeded its provider timeout.",
                category=ContentExtractionErrorCategory.TIMEOUT,
                retryable=True,
                source_url=source_url,
                status_code=status_code,
            )
        if status_code is not None and 400 <= status_code < 500:
            return cls._error(
                "Tavily Extract rejected the request.",
                category=ContentExtractionErrorCategory.INVALID_REQUEST,
                retryable=False,
                source_url=source_url,
                status_code=status_code,
            )
        if status_code is not None and status_code >= 500:
            return cls._error(
                "Tavily Extract is temporarily unavailable.",
                category=ContentExtractionErrorCategory.PROVIDER,
                retryable=True,
                source_url=source_url,
                status_code=status_code,
            )

        if isinstance(error, OSError) or any(
            token in name
            for name in error_type_names
            for token in ("connection", "transport", "clienterror")
        ):
            return cls._error(
                "Tavily Extract transport could not complete the request.",
                category=ContentExtractionErrorCategory.TRANSPORT,
                retryable=True,
                source_url=source_url,
            )

        return cls._error(
            "Tavily Extract failed without a usable response.",
            category=ContentExtractionErrorCategory.PROVIDER,
            retryable=True,
            source_url=source_url,
        )

    @staticmethod
    def _status_code(error: object) -> int | None:
        match = _STATUS_CODE_PATTERN.search(str(error))
        return int(match.group("status")) if match else None

    @staticmethod
    def _error(
        message: str,
        *,
        category: ContentExtractionErrorCategory,
        retryable: bool,
        source_url: str | None = None,
        status_code: int | None = None,
    ) -> ContentExtractionError:
        return ContentExtractionError(
            message,
            provider=ContentExtractionProvider.TAVILY,
            category=category,
            retryable=retryable,
            source_url=source_url,
            status_code=status_code,
        )

    @classmethod
    def _contract_error(cls, source_url: str) -> ContentExtractionError:
        return cls._error(
            "Tavily Extract returned a response that does not match the extraction contract.",
            category=ContentExtractionErrorCategory.RESPONSE_CONTRACT,
            retryable=False,
            source_url=source_url,
        )
