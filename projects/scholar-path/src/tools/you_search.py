"""Transport-only adapter for the current You.com Web Search API."""

from collections.abc import Mapping
from typing import Any

import httpx
from pydantic import ValidationError

from ..config import YouSearchConfiguration
from ..domain import SearchResult
from .supervisor_search import (
    InvalidSupervisorSearchQueryError,
    SupervisorSearchResponseContractError,
    SupervisorSearchResponseError,
    SupervisorSearchTimeoutError,
    SupervisorSearchTransportError,
)


class YouSearchAdapter:
    """Normalize You.com transport responses without interpreting Supervisor data."""

    def __init__(
        self,
        configuration: YouSearchConfiguration,
        *,
        client: httpx.Client | None = None,
    ) -> None:
        self._configuration = configuration
        self._client = client or httpx.Client()

    def search(self, query: str) -> tuple[SearchResult, ...]:
        """POST one exact query and return at most the configured number of results."""
        if not query.strip():
            raise InvalidSupervisorSearchQueryError("Supervisor search query must not be blank.")

        try:
            response = self._client.post(
                str(self._configuration.endpoint),
                headers={
                    "X-API-Key": self._configuration.api_key.get_secret_value(),
                    "Content-Type": "application/json",
                },
                json={"query": query, "count": self._configuration.result_count},
                timeout=self._configuration.timeout_seconds,
            )
        except httpx.TimeoutException as error:
            raise SupervisorSearchTimeoutError(
                "The You.com Web Search request exceeded its configured timeout."
            ) from error
        except httpx.RequestError as error:
            raise SupervisorSearchTransportError(
                "The You.com Web Search request could not be completed."
            ) from error

        if not 200 <= response.status_code < 300:
            raise SupervisorSearchResponseError(
                response.status_code,
                retryable=response.status_code == 429 or response.status_code >= 500,
                retry_after=response.headers.get("Retry-After"),
            )

        try:
            payload = response.json()
            normalized = self._normalize_payload(payload, query)
        except (TypeError, ValueError, ValidationError) as error:
            raise SupervisorSearchResponseContractError(
                "You.com returned a response that does not match the search contract."
            ) from error
        return normalized[: self._configuration.result_count]

    @staticmethod
    def _normalize_payload(payload: Any, query: str) -> tuple[SearchResult, ...]:
        """Convert web and news sections in stable order into SearchResult records."""
        if not isinstance(payload, Mapping):
            raise TypeError("The response root must be an object")

        results = payload.get("results")
        if results is None:
            return ()
        if not isinstance(results, Mapping):
            raise TypeError("The results field must be an object")

        normalized: list[SearchResult] = []
        for section_name in ("web", "news"):
            section = results.get(section_name)
            if section is None:
                continue
            if not isinstance(section, list):
                raise TypeError(f"The {section_name} result section must be a list")
            for item in section:
                if not isinstance(item, Mapping):
                    raise TypeError("Every search result must be an object")
                description = item.get("description")
                normalized.append(
                    SearchResult.model_validate(
                        {
                            "url": item.get("url"),
                            "title": item.get("title"),
                            "description": "" if description is None else description,
                            "snippets": item.get("snippets"),
                            "publication_date": item.get("page_age"),
                            "originating_query": query,
                        }
                    )
                )
        return tuple(normalized)
