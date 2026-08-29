"""Provider-neutral port and sanitized typed failures for Supervisor web search."""

from enum import StrEnum
from typing import Protocol, runtime_checkable

from ..domain import SearchResult


@runtime_checkable
class SupervisorSearchPort(Protocol):
    """Execute exactly one web query and return normalized provider-neutral results."""

    def search(self, query: str) -> tuple[SearchResult, ...]:
        """Search for one query without applying ScholarPath domain reasoning."""
        ...


class SupervisorSearchError(RuntimeError):
    """Base typed error raised by a Supervisor search adapter."""


class SearchProvider(StrEnum):
    """Search providers available to the resilient discovery workflow."""

    YOU = "you.com"
    TAVILY = "tavily"


class SearchErrorCategory(StrEnum):
    """Sanitized provider failure categories used by deterministic routing."""

    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    INVALID_REQUEST = "invalid_request"
    PROVIDER = "provider"
    RESPONSE_CONTRACT = "response_contract"
    UNKNOWN = "unknown"


class SearchProviderError(SupervisorSearchError):
    """A sanitized provider failure carrying deterministic routing metadata."""

    def __init__(
        self,
        message: str,
        *,
        provider: SearchProvider,
        category: SearchErrorCategory,
        retryable: bool,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.category = category
        self.retryable = retryable
        self.status_code = status_code


class InvalidSupervisorSearchQueryError(SupervisorSearchError):
    """The caller supplied an empty search query."""


class SupervisorSearchTimeoutError(SearchProviderError):
    """The provider request exceeded ScholarPath's configured HTTP timeout."""

    def __init__(
        self,
        message: str,
        *,
        provider: SearchProvider = SearchProvider.YOU,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            category=SearchErrorCategory.TIMEOUT,
            retryable=True,
        )


class SupervisorSearchTransportError(SearchProviderError):
    """The provider could not be reached or the request could not be sent."""

    def __init__(
        self,
        message: str,
        *,
        provider: SearchProvider = SearchProvider.YOU,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            category=SearchErrorCategory.TRANSPORT,
            retryable=True,
        )


class SupervisorSearchResponseError(SearchProviderError):
    """The provider returned a non-success HTTP response."""

    def __init__(
        self,
        status_code: int,
        *,
        retryable: bool,
        retry_after: str | None = None,
        provider: SearchProvider = SearchProvider.YOU,
    ) -> None:
        if status_code in {401, 403}:
            category = SearchErrorCategory.AUTHENTICATION
        elif status_code == 429:
            category = SearchErrorCategory.RATE_LIMIT
        elif status_code in {432, 433}:
            category = SearchErrorCategory.QUOTA
        elif status_code >= 500:
            category = SearchErrorCategory.PROVIDER
        else:
            category = SearchErrorCategory.INVALID_REQUEST
        super().__init__(
            f"Supervisor search provider returned HTTP {status_code}.",
            provider=provider,
            category=category,
            retryable=retryable,
            status_code=status_code,
        )
        self.status_code = status_code
        self.retry_after = retry_after


class SupervisorSearchResponseContractError(SearchProviderError):
    """A success response could not satisfy the normalized SearchResult contract."""

    def __init__(
        self,
        message: str,
        *,
        provider: SearchProvider = SearchProvider.YOU,
    ) -> None:
        super().__init__(
            message,
            provider=provider,
            category=SearchErrorCategory.RESPONSE_CONTRACT,
            retryable=False,
        )
