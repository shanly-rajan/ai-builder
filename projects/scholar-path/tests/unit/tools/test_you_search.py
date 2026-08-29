"""Mock-transport tests for the You.com Web Search adapter."""

import json
from collections.abc import Callable

import httpx
import pytest
from pydantic import SecretStr

from scholarpath.config import YouSearchConfiguration
from scholarpath.tools import (
    InvalidSupervisorSearchQueryError,
    SupervisorSearchPort,
    SupervisorSearchResponseContractError,
    SupervisorSearchResponseError,
    SupervisorSearchTimeoutError,
    SupervisorSearchTransportError,
    YouSearchAdapter,
)


def _configuration(**overrides: object) -> YouSearchConfiguration:
    return YouSearchConfiguration.model_validate(
        {
            "api_key": SecretStr("not-a-real-you-secret"),
            "endpoint": "https://ydc-index.io/v1/search",
            "timeout_seconds": 3.5,
            "result_count": 10,
            **overrides,
        }
    )


def _adapter(
    handler: Callable[[httpx.Request], httpx.Response],
    **configuration_overrides: object,
) -> YouSearchAdapter:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return YouSearchAdapter(_configuration(**configuration_overrides), client=client)


def test_request_uses_current_official_post_contract_and_configured_limits() -> None:
    query = "enterprise architecture professor university"

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert str(request.url) == "https://ydc-index.io/v1/search"
        assert request.headers["X-API-Key"] == "not-a-real-you-secret"
        assert request.headers["Content-Type"] == "application/json"
        assert json.loads(request.content) == {"query": query, "count": 7}
        assert request.extensions["timeout"] == {
            "connect": 3.5,
            "read": 3.5,
            "write": 3.5,
            "pool": 3.5,
        }
        assert "not-a-real-you-secret" not in str(request.url)
        return httpx.Response(200, json={"results": {"web": []}})

    results = _adapter(handler, result_count=7).search(query)

    assert results == ()


def test_web_and_news_results_are_normalized_in_stable_order() -> None:
    query = "responsible AI academics"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            request=request,
            json={
                "results": {
                    "web": [
                        {
                            "url": "https://example.edu/people/dr-lee",
                            "title": "Dr Jordan Lee | Example University",
                            "description": "Academic profile.",
                        }
                    ],
                    "news": [
                        {
                            "url": "https://example.org/research/update",
                            "title": "Research update",
                            "description": "Publication coverage.",
                            "page_age": "2026-07-04T10:15:00",
                        }
                    ],
                }
            },
        )

    results = _adapter(handler).search(query)

    assert [result.title for result in results] == [
        "Dr Jordan Lee | Example University",
        "Research update",
    ]
    assert str(results[0].url) == "https://example.edu/people/dr-lee"
    assert results[0].description == "Academic profile."
    assert results[0].publication_date is None
    assert results[1].publication_date is not None
    assert results[1].publication_date.isoformat() == "2026-07-04T10:15:00"
    assert all(result.originating_query == query for result in results)


@pytest.mark.parametrize("payload", [{}, {"results": {}}, {"results": None}])
def test_empty_or_missing_result_sets_return_an_empty_tuple(payload: object) -> None:
    adapter = _adapter(lambda request: httpx.Response(200, request=request, json=payload))

    assert adapter.search("doctoral supervision university") == ()


def test_normalized_results_are_capped_by_the_configured_limit() -> None:
    payload = {
        "results": {
            "web": [
                {
                    "url": f"https://example.edu/profile/{index}",
                    "title": f"Profile {index}",
                    "description": "Profile.",
                }
                for index in range(3)
            ]
        }
    }
    adapter = _adapter(
        lambda request: httpx.Response(200, request=request, json=payload),
        result_count=2,
    )

    assert len(adapter.search("academic profiles")) == 2


def test_timeout_is_mapped_to_a_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("synthetic timeout", request=request)

    with pytest.raises(SupervisorSearchTimeoutError):
        _adapter(handler).search("academic profiles")


def test_transport_failure_is_mapped_to_a_typed_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("synthetic connection failure", request=request)

    with pytest.raises(SupervisorSearchTransportError):
        _adapter(handler).search("academic profiles")


@pytest.mark.parametrize(
    ("status_code", "retryable"),
    [(401, False), (403, False), (422, False), (429, True), (500, True)],
)
def test_non_success_responses_are_sanitized_typed_errors(
    status_code: int, retryable: bool
) -> None:
    adapter = _adapter(
        lambda request: httpx.Response(
            status_code,
            request=request,
            headers={"Retry-After": "2"},
            text="provider body containing secret material",
        )
    )

    with pytest.raises(SupervisorSearchResponseError) as captured:
        adapter.search("academic profiles")

    assert captured.value.status_code == status_code
    assert captured.value.retryable is retryable
    assert captured.value.retry_after == "2"
    assert "secret material" not in str(captured.value)


@pytest.mark.parametrize(
    "response_factory",
    [
        lambda request: httpx.Response(200, request=request, content=b"not-json"),
        lambda request: httpx.Response(200, request=request, json={"results": []}),
        lambda request: httpx.Response(
            200,
            request=request,
            json={"results": {"web": [{"title": "Missing URL"}]}},
        ),
    ],
)
def test_malformed_success_responses_are_typed_contract_errors(
    response_factory: Callable[[httpx.Request], httpx.Response],
) -> None:
    with pytest.raises(SupervisorSearchResponseContractError):
        _adapter(response_factory).search("academic profiles")


def test_blank_query_is_rejected_before_http_is_called() -> None:
    def unexpected_request(request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"Unexpected request: {request.url}")

    adapter = _adapter(unexpected_request)

    with pytest.raises(InvalidSupervisorSearchQueryError):
        adapter.search("   ")


def test_adapter_satisfies_the_provider_neutral_search_port() -> None:
    adapter = _adapter(lambda request: httpx.Response(200, request=request, json={"results": {}}))

    assert isinstance(adapter, SupervisorSearchPort)
