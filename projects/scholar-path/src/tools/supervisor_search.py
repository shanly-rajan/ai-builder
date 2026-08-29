"""Provider-neutral port and typed failures for Supervisor web search."""

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


class InvalidSupervisorSearchQueryError(SupervisorSearchError):
    """The caller supplied an empty search query."""


class SupervisorSearchTimeoutError(SupervisorSearchError):
    """The provider request exceeded ScholarPath's configured HTTP timeout."""


class SupervisorSearchTransportError(SupervisorSearchError):
    """The provider could not be reached or the request could not be sent."""


class SupervisorSearchResponseError(SupervisorSearchError):
    """The provider returned a non-success HTTP response."""

    def __init__(
        self,
        status_code: int,
        *,
        retryable: bool,
        retry_after: str | None = None,
    ) -> None:
        super().__init__(f"Supervisor search provider returned HTTP {status_code}.")
        self.status_code = status_code
        self.retryable = retryable
        self.retry_after = retry_after


class SupervisorSearchResponseContractError(SupervisorSearchError):
    """A success response could not satisfy the normalized SearchResult contract."""
