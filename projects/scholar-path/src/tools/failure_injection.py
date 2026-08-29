"""Deterministic search-failure wrapper for local resilience demonstrations."""

from ..config import DiscoveryFailureMode
from ..domain import SearchResult
from .supervisor_search import (
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
    SupervisorSearchPort,
)


class FailureInjectingSupervisorSearch:
    """Decorate one provider port with an explicitly configured synthetic failure."""

    def __init__(
        self,
        delegate: SupervisorSearchPort,
        provider: SearchProvider,
        mode: DiscoveryFailureMode = DiscoveryFailureMode.OFF,
    ) -> None:
        self._delegate = delegate
        self._provider = provider
        self._mode = mode
        self._you_timeout_injected = False

    def search(self, query: str) -> tuple[SearchResult, ...]:
        """Inject the configured typed failure or delegate the exact query unchanged."""
        if (
            self._mode is DiscoveryFailureMode.YOU_TIMEOUT_ONCE
            and self._provider is SearchProvider.YOU
            and not self._you_timeout_injected
        ):
            self._you_timeout_injected = True
            raise SearchProviderError(
                "Injected deterministic Supervisor search timeout.",
                provider=self._provider,
                category=SearchErrorCategory.TIMEOUT,
                retryable=True,
            )

        inject_you_error = (
            self._mode is DiscoveryFailureMode.YOU_RETRYABLE_ERROR
            and self._provider is SearchProvider.YOU
        )
        inject_both_error = self._mode is DiscoveryFailureMode.BOTH_PROVIDERS_RETRYABLE_ERROR
        if inject_you_error or inject_both_error:
            raise SearchProviderError(
                "Injected deterministic retryable Supervisor search failure.",
                provider=self._provider,
                category=SearchErrorCategory.PROVIDER,
                retryable=True,
            )

        return self._delegate.search(query)
