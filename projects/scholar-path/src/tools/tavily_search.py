"""Cancellable adapter for the official ``langchain-tavily`` search tool."""

from __future__ import annotations

import asyncio
import re
from collections.abc import Mapping
from datetime import datetime
from email.utils import parsedate_to_datetime
from typing import Protocol, cast

from langchain_core.tools import ToolException
from langchain_tavily import TavilySearch
from pydantic import ValidationError

from ..config import TavilySearchConfiguration
from ..domain import SearchResult
from .supervisor_search import (
    InvalidSupervisorSearchQueryError,
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
)

_STATUS_CODE_PATTERN = re.compile(r"\b(?:error|http)\s+(?P<status>\d{3})\b", re.IGNORECASE)
_NO_RESULTS_PREFIX = "no search results found"


class AsyncTavilySearchTool(Protocol):
    """Narrow async boundary implemented by TavilySearch and deterministic fakes."""

    async def ainvoke(self, input: dict[str, object]) -> object:
        """Invoke one Tavily query and return its provider payload."""
        ...


class TavilySearchAdapter:
    """Normalize Tavily results without applying Supervisor-domain reasoning."""

    def __init__(
        self,
        configuration: TavilySearchConfiguration,
        *,
        tool: AsyncTavilySearchTool | None = None,
    ) -> None:
        self._configuration = configuration
        self._tool = tool or cast(
            AsyncTavilySearchTool,
            TavilySearch(
                tavily_api_key=configuration.api_key.get_secret_value(),
                max_results=configuration.result_count,
                topic="general",
                search_depth="basic",
                include_answer=False,
                include_raw_content=False,
                include_images=False,
                auto_parameters=False,
                handle_tool_error=False,
            ),
        )

    def search(self, query: str) -> tuple[SearchResult, ...]:
        """Execute one exact query within the configured application deadline."""
        if not query.strip():
            raise InvalidSupervisorSearchQueryError("Supervisor search query must not be blank.")

        try:
            payload = asyncio.run(self._invoke_with_timeout(query))
        except TimeoutError:
            raise self._error(
                "Tavily search exceeded its configured timeout.",
                category=SearchErrorCategory.TIMEOUT,
                retryable=True,
            ) from None
        except ToolException as error:
            if str(error).casefold().startswith(_NO_RESULTS_PREFIX):
                return ()
            raise self._error(
                "Tavily search failed before returning results.",
                category=SearchErrorCategory.PROVIDER,
                retryable=False,
            ) from None
        except SearchProviderError:
            raise
        except Exception as error:
            raise self._map_provider_error(error) from None

        if isinstance(payload, Mapping) and "error" in payload:
            provider_error = payload["error"]
            if provider_error is None:
                raise self._contract_error()
            raise self._map_provider_error(provider_error) from None

        try:
            normalized = self._normalize_payload(payload, query)
        except (TypeError, ValueError, ValidationError):
            raise self._contract_error() from None
        return normalized[: self._configuration.result_count]

    async def _invoke_with_timeout(self, query: str) -> object:
        """Cancel the public async tool call when the application deadline expires."""
        async with asyncio.timeout(self._configuration.timeout_seconds):
            return await self._tool.ainvoke({"query": query})

    @classmethod
    def _normalize_payload(cls, payload: object, query: str) -> tuple[SearchResult, ...]:
        if not isinstance(payload, Mapping):
            raise TypeError("The Tavily response root must be an object")
        if "results" not in payload:
            raise TypeError("The Tavily response must contain results")

        results = payload["results"]
        if not isinstance(results, list):
            raise TypeError("The Tavily results field must be a list")

        normalized: list[SearchResult] = []
        for item in results:
            if not isinstance(item, Mapping):
                raise TypeError("Every Tavily result must be an object")
            content = item.get("content")
            normalized.append(
                SearchResult.model_validate(
                    {
                        "url": item.get("url"),
                        "title": item.get("title"),
                        "description": "" if content is None else content,
                        "publication_date": cls._parse_publication_date(item.get("published_date")),
                        "originating_query": query,
                    }
                )
            )
        return tuple(normalized)

    @staticmethod
    def _parse_publication_date(value: object) -> datetime | None:
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if not isinstance(value, str):
            raise TypeError("Tavily publication dates must be strings")

        date_text = value.strip()
        if not date_text:
            return None
        try:
            return datetime.fromisoformat(date_text.replace("Z", "+00:00"))
        except ValueError:
            return parsedate_to_datetime(date_text)

    @classmethod
    def _map_provider_error(cls, error: object) -> SearchProviderError:
        if isinstance(error, SearchProviderError):
            return error

        error_type_names = {error_type.__name__.casefold() for error_type in type(error).__mro__}
        if any("timeout" in name for name in error_type_names):
            return cls._error(
                "Tavily search exceeded its configured timeout.",
                category=SearchErrorCategory.TIMEOUT,
                retryable=True,
            )

        status_code = cls._status_code(error)
        if status_code in {401, 403}:
            return cls._error(
                "Tavily search authentication failed.",
                category=SearchErrorCategory.AUTHENTICATION,
                retryable=False,
                status_code=status_code,
            )
        if status_code == 429:
            return cls._error(
                "Tavily search was rate limited.",
                category=SearchErrorCategory.RATE_LIMIT,
                retryable=True,
                status_code=status_code,
            )
        if status_code in {432, 433}:
            return cls._error(
                "Tavily search quota is unavailable.",
                category=SearchErrorCategory.QUOTA,
                retryable=False,
                status_code=status_code,
            )
        if status_code in {408, 504}:
            return cls._error(
                "Tavily search exceeded its provider timeout.",
                category=SearchErrorCategory.TIMEOUT,
                retryable=True,
                status_code=status_code,
            )
        if status_code is not None and 400 <= status_code < 500:
            return cls._error(
                "Tavily search rejected the request.",
                category=SearchErrorCategory.INVALID_REQUEST,
                retryable=False,
                status_code=status_code,
            )
        if status_code is not None and status_code >= 500:
            return cls._error(
                "Tavily search provider is temporarily unavailable.",
                category=SearchErrorCategory.PROVIDER,
                retryable=True,
                status_code=status_code,
            )

        if isinstance(error, OSError) or any(
            token in name
            for name in error_type_names
            for token in ("connection", "transport", "clienterror")
        ):
            return cls._error(
                "Tavily search transport could not complete the request.",
                category=SearchErrorCategory.TRANSPORT,
                retryable=True,
            )

        return cls._error(
            "Tavily search provider failed without a usable response.",
            category=SearchErrorCategory.PROVIDER,
            retryable=True,
        )

    @staticmethod
    def _status_code(error: object) -> int | None:
        match = _STATUS_CODE_PATTERN.search(str(error))
        return int(match.group("status")) if match else None

    @staticmethod
    def _error(
        message: str,
        *,
        category: SearchErrorCategory,
        retryable: bool,
        status_code: int | None = None,
    ) -> SearchProviderError:
        return SearchProviderError(
            message,
            provider=SearchProvider.TAVILY,
            category=category,
            retryable=retryable,
            status_code=status_code,
        )

    @classmethod
    def _contract_error(cls) -> SearchProviderError:
        return cls._error(
            "Tavily returned a response that does not match the search contract.",
            category=SearchErrorCategory.RESPONSE_CONTRACT,
            retryable=False,
        )
