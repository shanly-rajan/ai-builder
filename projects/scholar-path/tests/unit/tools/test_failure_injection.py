"""Tests for deterministic Supervisor search failure injection."""

import pytest

from scholarpath.config import DiscoveryFailureMode
from scholarpath.domain import SearchResult
from scholarpath.tools.failure_injection import FailureInjectingSupervisorSearch
from scholarpath.tools.supervisor_search import (
    SearchErrorCategory,
    SearchProvider,
    SearchProviderError,
    SupervisorSearchPort,
)


def _result(query: str) -> SearchResult:
    return SearchResult.model_validate(
        {
            "url": "https://example.edu/people/jane-doe",
            "title": "Dr Jane Doe | Example University",
            "description": "Academic profile.",
            "originating_query": query,
        }
    )


class RecordingSearch:
    """Return one normalized result while recording delegated queries."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def search(self, query: str) -> tuple[SearchResult, ...]:
        self.calls.append(query)
        return (_result(query),)


@pytest.mark.parametrize("provider", tuple(SearchProvider))
def test_off_mode_delegates_each_exact_query_without_altering_results(
    provider: SearchProvider,
) -> None:
    delegate = RecordingSearch()
    wrapper = FailureInjectingSupervisorSearch(delegate, provider)

    first = wrapper.search("first exact query")
    second = wrapper.search("second exact query")

    assert delegate.calls == ["first exact query", "second exact query"]
    assert first == (_result("first exact query"),)
    assert second == (_result("second exact query"),)


def test_you_timeout_once_fails_first_call_then_delegates() -> None:
    delegate = RecordingSearch()
    wrapper = FailureInjectingSupervisorSearch(
        delegate,
        SearchProvider.YOU,
        DiscoveryFailureMode.YOU_TIMEOUT_ONCE,
    )

    with pytest.raises(SearchProviderError) as captured:
        wrapper.search("query retried after timeout")

    results = wrapper.search("query retried after timeout")

    assert captured.value.provider is SearchProvider.YOU
    assert captured.value.category is SearchErrorCategory.TIMEOUT
    assert captured.value.retryable is True
    assert delegate.calls == ["query retried after timeout"]
    assert results == (_result("query retried after timeout"),)


def test_you_timeout_once_does_not_affect_tavily() -> None:
    delegate = RecordingSearch()
    wrapper = FailureInjectingSupervisorSearch(
        delegate,
        SearchProvider.TAVILY,
        DiscoveryFailureMode.YOU_TIMEOUT_ONCE,
    )

    results = wrapper.search("tavily query")

    assert delegate.calls == ["tavily query"]
    assert results == (_result("tavily query"),)


def test_you_retryable_error_fails_every_you_call_without_delegating() -> None:
    delegate = RecordingSearch()
    wrapper = FailureInjectingSupervisorSearch(
        delegate,
        SearchProvider.YOU,
        DiscoveryFailureMode.YOU_RETRYABLE_ERROR,
    )

    for query in ("first query", "second query"):
        with pytest.raises(SearchProviderError) as captured:
            wrapper.search(query)
        assert captured.value.provider is SearchProvider.YOU
        assert captured.value.category is SearchErrorCategory.PROVIDER
        assert captured.value.retryable is True

    assert delegate.calls == []


def test_you_retryable_error_mode_leaves_tavily_unchanged() -> None:
    delegate = RecordingSearch()
    wrapper = FailureInjectingSupervisorSearch(
        delegate,
        SearchProvider.TAVILY,
        DiscoveryFailureMode.YOU_RETRYABLE_ERROR,
    )

    assert wrapper.search("fallback query") == (_result("fallback query"),)
    assert delegate.calls == ["fallback query"]


@pytest.mark.parametrize("provider", tuple(SearchProvider))
def test_both_provider_error_mode_fails_without_delegating(
    provider: SearchProvider,
) -> None:
    delegate = RecordingSearch()
    wrapper = FailureInjectingSupervisorSearch(
        delegate,
        provider,
        DiscoveryFailureMode.BOTH_PROVIDERS_RETRYABLE_ERROR,
    )

    with pytest.raises(SearchProviderError) as captured:
        wrapper.search("query containing not-a-real-secret")

    assert captured.value.provider is provider
    assert captured.value.category is SearchErrorCategory.PROVIDER
    assert captured.value.retryable is True
    assert "not-a-real-secret" not in str(captured.value)
    assert delegate.calls == []


def test_each_wrapper_has_independent_once_only_state_and_satisfies_port() -> None:
    first = FailureInjectingSupervisorSearch(
        RecordingSearch(),
        SearchProvider.YOU,
        DiscoveryFailureMode.YOU_TIMEOUT_ONCE,
    )
    second = FailureInjectingSupervisorSearch(
        RecordingSearch(),
        SearchProvider.YOU,
        DiscoveryFailureMode.YOU_TIMEOUT_ONCE,
    )

    assert isinstance(first, SupervisorSearchPort)
    with pytest.raises(SearchProviderError):
        first.search("same deterministic query")
    with pytest.raises(SearchProviderError):
        second.search("same deterministic query")
