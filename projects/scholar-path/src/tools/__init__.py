"""Provider-neutral tool contracts and concrete search adapters."""

from .content_extraction import (
    ContentExtractionError,
    ContentExtractionErrorCategory,
    ContentExtractionPort,
    ContentExtractionProvider,
    ExtractedContent,
)
from .failure_injection import FailureInjectingSupervisorSearch
from .supervisor_search import (
    InvalidSupervisorSearchQueryError,
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
    SupervisorSearchError,
    SupervisorSearchPort,
    SupervisorSearchResponseContractError,
    SupervisorSearchResponseError,
    SupervisorSearchTimeoutError,
    SupervisorSearchTransportError,
)
from .tavily_extraction import TavilyExtractionAdapter
from .tavily_search import TavilySearchAdapter
from .you_search import YouSearchAdapter

__all__ = [
    "ContentExtractionError",
    "ContentExtractionErrorCategory",
    "ContentExtractionPort",
    "ContentExtractionProvider",
    "ExtractedContent",
    "FailureInjectingSupervisorSearch",
    "InvalidSupervisorSearchQueryError",
    "SearchErrorCategory",
    "SearchProvider",
    "SearchProviderError",
    "SupervisorSearchError",
    "SupervisorSearchPort",
    "SupervisorSearchResponseContractError",
    "SupervisorSearchResponseError",
    "SupervisorSearchTimeoutError",
    "SupervisorSearchTransportError",
    "TavilySearchAdapter",
    "TavilyExtractionAdapter",
    "YouSearchAdapter",
]
