"""Exercise real SDK trace parenting with an explicit recording client and fake ports."""

from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Never, cast
from unittest.mock import MagicMock
from uuid import UUID

import pytest
from langsmith import Client, trace, tracing_context
from langsmith.run_trees import RunTree

from scholarpath.evaluation.models import GraphTargetOutput
from scholarpath.evaluation.scenarios import evaluation_dataset_inputs
from scholarpath.evaluation.synthetic_tracing import safe_synthetic_payload
from scholarpath.evaluation.targets import fake_end_to_end_target
from scholarpath.evaluation.trace_case import synthetic_trace_scenario, traced_fallback_target
from scholarpath.tools import SearchErrorCategory, SearchProvider


def _forbid_live_constructor(*args: object, **kwargs: object) -> Never:
    del args, kwargs
    raise AssertionError("Synthetic graph tracing must reuse the explicit client and fake ports")


@pytest.fixture(autouse=True)
def prevent_live_provider_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in (
        "OpenAIPlanningModelAdapter",
        "YouSearchAdapter",
        "_LazyTavilySearch",
        "_LazyTavilyExtraction",
        "_LazyOpenAIEvidenceModel",
        "_LazyOpenAIResearchFitModel",
        "_LazyNebiusReviewModel",
        "_LazyMem0CandidatePreferenceMemory",
    ):
        monkeypatch.setattr(f"scholarpath.graph.workflow.{name}", _forbid_live_constructor)
    monkeypatch.setattr("scholarpath.observability.tracing.Client", _forbid_live_constructor)
    monkeypatch.setattr("langsmith.run_trees.get_cached_client", _forbid_live_constructor)


@dataclass
class RecordedSDKCalls:
    """Capture calls produced by real RunTree and LangChainTracer implementations."""

    creates: list[dict[str, object]] = field(default_factory=list)
    updates: list[dict[str, object]] = field(default_factory=list)

    def create(self, *args: object, **kwargs: object) -> None:
        assert not args
        self.creates.append(deepcopy(kwargs))

    def update(self, *args: object, **kwargs: object) -> None:
        assert not args
        self.updates.append(deepcopy(kwargs))

    def completed(self) -> list[dict[str, object]]:
        by_id = {item["id"]: dict(item) for item in self.creates}
        for update in self.updates:
            run_id = update["run_id"]
            assert run_id in by_id, "Every completed span must have an observed creation"
            by_id[run_id].update(update)
        return list(by_id.values())


@contextmanager
def _recording_parent() -> Iterator[tuple[RunTree, RecordedSDKCalls]]:
    records = RecordedSDKCalls()
    mock_client = MagicMock(spec=Client)
    mock_client.create_run.side_effect = records.create
    mock_client.update_run.side_effect = records.update
    client = cast(Client, mock_client)
    with (
        tracing_context(enabled=True, client=client, project_name="synthetic-sdk-test"),
        trace("synthetic_evaluation_case", inputs={}, client=client) as parent,
    ):
        yield parent, records
    mock_client.close.assert_not_called()


def _metadata(run: dict[str, object]) -> dict[str, object]:
    extra = run.get("extra")
    assert isinstance(extra, dict)
    metadata = extra.get("metadata")
    assert isinstance(metadata, dict)
    return cast(dict[str, object], metadata)


def test_real_sdk_records_canonical_children_under_the_existing_evaluation_parent() -> None:
    inputs = evaluation_dataset_inputs(synthetic_trace_scenario())
    original_inputs = deepcopy(inputs)

    with _recording_parent() as (parent, records):
        raw_output = traced_fallback_target(inputs)
        parent.end(outputs=raw_output)

    output = GraphTargetOutput.model_validate(raw_output)
    assert inputs == original_inputs
    assert output.fallback_search_used is True
    assert output.interrupted is True
    assert output.shortlisted_supervisor_ids == ()
    assert output.candidate_reviews == ()
    assert output.measurements.port_invocations == 31
    assert Counter(attempt.provider_used for attempt in output.search_attempts) == {
        SearchProvider.YOU: 2,
        SearchProvider.TAVILY: 3,
    }
    assert all(
        attempt.error_category is SearchErrorCategory.TIMEOUT
        for attempt in output.search_attempts[:2]
    )

    completed = records.completed()
    children = [run for run in completed if run["id"] != parent.id]
    names = Counter(str(run["name"]) for run in children)
    assert names["scholarpath_graph"] == 1
    assert names["candidate_review_gate"] == 1
    assert names["enough_supervisors_found"] == 2
    assert set(output.execution_log).issubset(names)
    assert names["you.com_supervisor_search_attempt"] == 2
    assert names["tavily_supervisor_search_attempt"] == 3
    assert "save_shortlisted_supervisors" not in names
    graph_run = next(run for run in children if run["name"] == "scholarpath_graph")
    assert graph_run["parent_run_id"] == parent.id
    known_ids = {run["id"] for run in completed}
    for child in children:
        assert isinstance(child["id"], UUID)
        assert child["trace_id"] == parent.trace_id
        assert child["parent_run_id"] in known_ids
        assert child["session_name"] == "synthetic-sdk-test"
        assert child.get("start_time") is not None
        assert child.get("end_time") is not None

    attempt_runs = [
        run for run in children if str(run["name"]).endswith("_supervisor_search_attempt")
    ]
    assert Counter(_metadata(run)["error_category"] for run in attempt_runs) == {
        "timeout": 2,
        "none": 3,
    }

    # Upload projection must not remove evidence needed by in-process evaluation.
    before_projection = deepcopy(raw_output)
    safe_output = safe_synthetic_payload(raw_output)
    assert safe_output != raw_output
    assert raw_output == before_projection
    assert output.verification_records[0].evidence[0].source_url is not None
    assert output.verification_records[0].evidence[0].claim_summary


def test_default_fake_target_still_disables_child_tracing_under_an_active_parent() -> None:
    inputs = evaluation_dataset_inputs(synthetic_trace_scenario())

    with _recording_parent() as (parent, records):
        raw_output = fake_end_to_end_target(inputs)
        parent.end(outputs=raw_output)

    assert [run["name"] for run in records.creates] == ["synthetic_evaluation_case"]
    assert {run["id"] for run in records.completed()} == {parent.id}
    output = GraphTargetOutput.model_validate(raw_output)
    assert output.interrupted is True
    assert output.shortlisted_supervisor_ids == ()
    assert output.measurements.port_invocations == 31
