"""Unit tests for M4 search-result and discovery-provenance contracts."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    SearchResult,
    SupervisorDiscoveryProvenance,
)
from tests.fixtures import make_prospective_supervisors


def test_search_result_preserves_metadata_and_round_trips_as_json() -> None:
    result = SearchResult.model_validate(
        {
            "url": "https://example.edu/people/dr-lee",
            "title": "Dr Jordan Lee | Example University",
            "description": "Academic profile and recent publications.",
            "publication_date": datetime(2026, 7, 4, 10, 15, tzinfo=UTC),
            "originating_query": "responsible AI university profile",
        }
    )

    restored = SearchResult.model_validate_json(result.model_dump_json())

    assert restored == result
    assert restored.publication_date == datetime(2026, 7, 4, 10, 15, tzinfo=UTC)
    assert restored.originating_query == "responsible AI university profile"


@pytest.mark.parametrize(
    "update",
    [
        {"url": "not-a-url"},
        {"title": "   "},
        {"originating_query": "   "},
        {"unexpected": "field"},
    ],
)
def test_search_result_rejects_invalid_required_data(update: dict[str, object]) -> None:
    payload: dict[str, object] = {
        "url": "https://example.edu/people/dr-lee",
        "title": "Dr Jordan Lee | Example University",
        "originating_query": "responsible AI university profile",
        **update,
    }

    with pytest.raises(ValidationError):
        SearchResult.model_validate(payload)


def test_search_result_allows_absent_publication_date_and_description() -> None:
    result = SearchResult.model_validate(
        {
            "url": "https://example.edu/people/dr-lee",
            "title": "Dr Jordan Lee | Example University",
            "originating_query": "responsible AI university profile",
        }
    )

    assert result.description == ""
    assert result.publication_date is None


def test_supervisor_discovery_provenance_rejects_duplicate_pairs() -> None:
    supervisor = make_prospective_supervisors()[0]
    provenance = SupervisorDiscoveryProvenance.model_validate(
        {
            "source_url": supervisor.profile_url,
            "originating_query": supervisor.discovery_query,
        }
    )

    with pytest.raises(ValidationError, match="provenance entries must be unique"):
        supervisor.model_copy(update={"discovery_provenance": (provenance, provenance)})
