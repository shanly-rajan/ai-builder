"""Deterministic M12.4 alternate official-source diagnostic tests."""

from collections.abc import Mapping

import pytest
from pydantic import ValidationError

from scholarpath.domain import SearchResult
from scholarpath.graph import (
    AlternateSourceAttempt,
    AlternateSourceRejectionCategory,
    AlternateSourceRejectionCounts,
    AlternateSourceSelectionOutcome,
    alternate_official_source_query,
    evaluate_alternate_official_sources,
    merge_alternate_source_attempts,
)
from scholarpath.tools import SearchErrorCategory
from tests.fixtures.factories import make_prospective_supervisor


def _result(
    *,
    url: str,
    title: str,
    query: str,
    description: str = "Official institutional profile.",
) -> SearchResult:
    return SearchResult.model_validate(
        {
            "url": url,
            "title": title,
            "description": description,
            "originating_query": query,
        }
    )


def test_selector_counts_every_first_failed_gate_and_preserves_first_selection() -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)
    exact_title = "Dr Amara Ndlovu | Southern Cape Institute of Technology"
    first_eligible = _result(
        url="https://www.southerncape.ac.za/people/amara-ndlovu",
        title=exact_title,
        query=query,
    )
    second_eligible = _result(
        url="https://www.southerncape.ac.za/directory/amara-ndlovu",
        title=exact_title,
        query=query,
    )
    results = (
        _result(
            url=str(supervisor.profile_url),
            title=exact_title,
            query="different internal query",
        ),
        _result(url=str(supervisor.profile_url), title=exact_title, query=query),
        _result(
            url="http://www.southerncape.ac.za/people/amara-ndlovu",
            title=exact_title,
            query=query,
        ),
        _result(
            url="https://www.southerncape.ac.za/people/nomsa-ndlovu",
            title="Dr Nomsa Ndlovu | Southern Cape Institute of Technology",
            query=query,
        ),
        _result(
            url="https://www.southerncape.ac.za/people/amara-ndlovu",
            title="Dr Amara Ndlovu | Northbridge University",
            query=query,
        ),
        _result(
            url="https://www.southerncape.ac.za/news/amara-ndlovu",
            title=exact_title,
            query=query,
        ),
        _result(
            url="https://www.unrelated.edu/people/amara-ndlovu",
            title=exact_title,
            query=query,
        ),
        _result(
            url="https://www.southerncape.ac.za/people/amara-ndlovu-publication",
            title=f"{exact_title} | Publication",
            query=query,
        ),
        first_eligible,
        second_eligible,
    )

    evaluation = evaluate_alternate_official_sources(supervisor, results, query=query)

    assert evaluation.result_count == 10
    assert evaluation.eligible_result_count == 2
    assert evaluation.outcome is AlternateSourceSelectionOutcome.SELECTED
    assert evaluation.selected_source is not None
    assert str(evaluation.selected_source.source_url) == str(first_eligible.url)
    assert evaluation.rejection_counts == AlternateSourceRejectionCounts(
        query_mismatch=1,
        same_url=1,
        https_or_host_invalid=1,
        exact_person_text_missing=1,
        exact_institution_text_missing=1,
        singular_route_mismatch=1,
        academic_host_mismatch=1,
        source_kind_unsupported=1,
    )
    assert evaluation.rejection_counts.total == 8


def test_empty_and_all_rejected_results_have_distinct_outcomes() -> None:
    supervisor = make_prospective_supervisor(1)
    query = alternate_official_source_query(supervisor)

    empty = evaluate_alternate_official_sources(supervisor, (), query=query)
    rejected = evaluate_alternate_official_sources(
        supervisor,
        (
            _result(
                url="https://www.southerncape.ac.za/people/nomsa-ndlovu",
                title="Dr Nomsa Ndlovu | Southern Cape Institute of Technology",
                query=query,
            ),
        ),
        query=query,
    )

    assert empty.outcome is AlternateSourceSelectionOutcome.NO_RESULTS
    assert empty.rejection_counts.total == 0
    assert rejected.outcome is AlternateSourceSelectionOutcome.REJECTED_ALL
    assert rejected.rejection_counts.exact_person_text_missing == 1


def test_rejection_counts_increment_and_combine_revalidate_values() -> None:
    first = AlternateSourceRejectionCounts().increment(
        AlternateSourceRejectionCategory.EXACT_PERSON_TEXT_MISSING
    )
    second = AlternateSourceRejectionCounts(
        exact_person_text_missing=2,
        exact_institution_text_missing=1,
    )

    combined = first.combine(second)

    assert combined.exact_person_text_missing == 3
    assert combined.exact_institution_text_missing == 1
    assert combined.total == 4
    with pytest.raises(ValidationError):
        AlternateSourceRejectionCounts(query_mismatch=True)


@pytest.mark.parametrize(
    "values",
    [
        {
            "outcome": "selected",
            "result_count": 1,
            "eligible_result_count": 0,
            "rejection_counts": {"exact_person_text_missing": 1},
        },
        {
            "outcome": "no_results",
            "result_count": 1,
            "eligible_result_count": 0,
            "rejection_counts": {"exact_person_text_missing": 1},
        },
        {
            "outcome": "rejected_all",
            "result_count": 1,
            "eligible_result_count": 1,
        },
        {
            "outcome": "provider_error",
            "result_count": 0,
            "eligible_result_count": 0,
        },
        {
            "outcome": "not_configured",
            "result_count": 0,
            "eligible_result_count": 0,
            "error_category": "unknown",
        },
        {
            "outcome": "rejected_all",
            "result_count": 2,
            "eligible_result_count": 0,
            "rejection_counts": {"same_url": 1},
        },
    ],
)
def test_alternate_source_attempt_rejects_inconsistent_outcomes(
    values: Mapping[str, object],
) -> None:
    with pytest.raises(ValidationError):
        AlternateSourceAttempt.model_validate(
            {
                "supervisor_id": "supervisor-001",
                "attempt_number": 1,
                "discovery_round": 1,
                **values,
            }
        )


def test_provider_error_attempt_retains_only_typed_aggregate_metadata() -> None:
    attempt = AlternateSourceAttempt(
        supervisor_id="opaque-supervisor-id",
        attempt_number=1,
        discovery_round=2,
        outcome=AlternateSourceSelectionOutcome.PROVIDER_ERROR,
        result_count=0,
        eligible_result_count=0,
        error_category=SearchErrorCategory.TIMEOUT,
    )

    rendered = attempt.model_dump_json()

    assert set(AlternateSourceAttempt.model_fields) == {
        "supervisor_id",
        "attempt_number",
        "discovery_round",
        "outcome",
        "result_count",
        "eligible_result_count",
        "rejection_counts",
        "error_category",
    }
    assert "timeout" in rendered
    for private_value in (
        "sensitive query",
        "https://private.example/profile",
        "returned result title",
        "page content",
        "Candidate research statement",
        "secret-token",
    ):
        assert private_value not in rendered


def test_alternate_source_attempt_reducer_is_idempotent_per_round_and_supervisor() -> None:
    attempt = AlternateSourceAttempt(
        supervisor_id="supervisor-001",
        attempt_number=1,
        discovery_round=2,
        outcome=AlternateSourceSelectionOutcome.NO_RESULTS,
        result_count=0,
        eligible_result_count=0,
    )
    next_round = attempt.model_copy(update={"discovery_round": 3})

    merged = merge_alternate_source_attempts([attempt], [attempt, next_round])

    assert merged == [attempt, next_round]
