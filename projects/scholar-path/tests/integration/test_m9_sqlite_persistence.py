"""Offline integration tests for durable M9 Candidate-review checkpoints."""

from datetime import datetime
from pathlib import Path
from typing import Any, cast

import pytest
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.types import Command

from scholarpath.graph import (
    CANDIDATE_REVIEW_GATE,
    AlternateSourceAttempt,
    AlternateSourceSelectionOutcome,
    CandidateApproveResponse,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    UtcClockPort,
    alternate_official_source_query,
    build_scholarpath_graph,
    candidate_review_payload_from_graph_output,
    candidate_review_response_value,
    create_initial_state,
    open_local_sqlite_checkpointer,
)
from scholarpath.tools import (
    ContentExtractionError,
    ContentExtractionErrorCategory,
    ContentExtractionProvider,
    ExtractedContent,
)
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_graph_content_outcomes,
)

THREAD_ID = "candidate-research-run-001"


class _FixedUtcClock:
    """Return the fixture timestamp so both application instances are identical."""

    def __init__(self, timestamp: datetime) -> None:
        self._timestamp = timestamp

    def now(self) -> datetime:
        return self._timestamp


def _build_graph(
    fixture_config: GraphFixtureConfig,
    checkpointer: BaseCheckpointSaver[Any],
    *,
    content_extractor: FakeContentExtraction | None = None,
    alternate_evidence_search: FakeSupervisorSearch | None = None,
) -> CompiledStateGraph[ScholarPathState, None, ScholarPathState, ScholarPathState]:
    clock: UtcClockPort = _FixedUtcClock(fixture_config.fixtures.generated_at)
    return build_scholarpath_graph(
        fixture_config,
        checkpointer=checkpointer,
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=FakeSupervisorSearch(),
        content_extractor=content_extractor or FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        candidate_preference_memory=FakeCandidatePreferenceMemory(),
        alternate_evidence_search=alternate_evidence_search or FakeSupervisorSearch(),
        utc_clock=clock,
    )


def test_sqlite_checkpoint_can_be_inspected_after_close_and_resumed_after_reopen(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "nested" / "scholarpath-checkpoints.sqlite3"
    fixture_config = GraphFixtureConfig()
    runnable_config: RunnableConfig = {
        "configurable": {"thread_id": THREAD_ID},
        "recursion_limit": 80,
    }

    with open_local_sqlite_checkpointer(database_path) as first_checkpointer:
        first_graph = _build_graph(fixture_config, first_checkpointer)
        paused_output = cast(
            dict[str, object],
            first_graph.invoke(
                create_initial_state(fixture_config.fixtures.candidate_profile),
                config=runnable_config,
            ),
        )
        payload = candidate_review_payload_from_graph_output(paused_output)
        paused_snapshot = first_graph.get_state(runnable_config)
        paused_state = cast(ScholarPathState, paused_snapshot.values)

        assert payload is not None
        assert paused_snapshot.next == (CANDIDATE_REVIEW_GATE,)
        assert paused_state["review_status"] is ReviewStatus.PROPOSED
        assert paused_state["shortlisted_supervisors"] == []
        assert paused_state["supervisor_shortlist"] is None
        assert "save_shortlisted_supervisors" not in paused_state["execution_log"]

    assert database_path.is_file()
    assert database_path.stat().st_size > 0

    with open_local_sqlite_checkpointer(database_path) as reopened_checkpointer:
        reopened_graph = _build_graph(fixture_config, reopened_checkpointer)
        reopened_snapshot = reopened_graph.get_state(runnable_config)
        reopened_state = cast(ScholarPathState, reopened_snapshot.values)

        assert reopened_snapshot.next == (CANDIDATE_REVIEW_GATE,)
        assert reopened_state["candidate_profile"] == fixture_config.fixtures.candidate_profile
        assert reopened_state["proposed_shortlist"] is not None
        assert reopened_state["shortlisted_supervisors"] == []

        assert payload is not None
        approval = CandidateApproveResponse(
            action="approve",
            supervisor_ids=tuple(
                item.supervisor_id for item in payload.proposed_supervisor_shortlist
            ),
        )
        completed_state = cast(
            ScholarPathState,
            reopened_graph.invoke(
                Command(resume=candidate_review_response_value(approval)),
                config=runnable_config,
            ),
        )

        assert completed_state["review_status"] is ReviewStatus.COMPLETED
        assert completed_state["supervisor_shortlist"] is not None
        assert (
            tuple(
                supervisor.supervisor_id
                for supervisor in completed_state["supervisor_shortlist"].shortlisted_supervisors
            )
            == approval.supervisor_ids
        )
        assert completed_state["execution_log"].count(CANDIDATE_REVIEW_GATE) == 1
        assert completed_state["execution_log"][-2:] == [
            "save_shortlisted_supervisors",
            "generate_shortlist_briefing",
        ]


@pytest.mark.parametrize("relative_path", [".", "existing-directory"])
def test_local_sqlite_checkpointer_rejects_a_directory_path(
    tmp_path: Path,
    relative_path: str,
) -> None:
    database_path = tmp_path if relative_path == "." else tmp_path / relative_path
    database_path.mkdir(parents=True, exist_ok=True)

    with (
        pytest.raises(ValueError, match="must identify a file"),
        open_local_sqlite_checkpointer(database_path),
    ):
        pytest.fail("A directory must not be opened as a SQLite checkpoint file")


def test_sqlite_checkpoint_restores_typed_alternate_source_diagnostics(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "alternate-diagnostics.sqlite3"
    fixture_config = GraphFixtureConfig()
    supervisor = fixture_config.fixtures.raw_search_results[0].to_prospective_supervisor()
    primary_url = str(supervisor.profile_url)
    content_outcomes: dict[str, ExtractedContent | Exception] = {**make_graph_content_outcomes()}
    content_outcomes[primary_url] = ContentExtractionError(
        "Synthetic extraction failure.",
        provider=ContentExtractionProvider.TAVILY,
        category=ContentExtractionErrorCategory.EXTRACTION_FAILED,
        retryable=True,
        source_url=primary_url,
    )
    alternate_query = alternate_official_source_query(supervisor)
    runnable_config: RunnableConfig = {
        "configurable": {"thread_id": "alternate-diagnostic-thread"},
        "recursion_limit": 80,
    }

    with open_local_sqlite_checkpointer(database_path) as checkpointer:
        graph = _build_graph(
            fixture_config,
            checkpointer,
            content_extractor=FakeContentExtraction(content_outcomes),
            alternate_evidence_search=FakeSupervisorSearch({alternate_query: ()}),
        )
        graph.invoke(
            create_initial_state(fixture_config.fixtures.candidate_profile),
            config=runnable_config,
        )
        state = cast(ScholarPathState, graph.get_state(runnable_config).values)
        assert len(state["alternate_source_attempts"]) == 1
        assert state["alternate_source_attempts"][0].outcome is (
            AlternateSourceSelectionOutcome.NO_RESULTS
        )

    with open_local_sqlite_checkpointer(database_path) as reopened_checkpointer:
        reopened_graph = _build_graph(fixture_config, reopened_checkpointer)
        reopened_state = cast(
            ScholarPathState,
            reopened_graph.get_state(runnable_config).values,
        )

    assert len(reopened_state["alternate_source_attempts"]) == 1
    restored = reopened_state["alternate_source_attempts"][0]
    assert isinstance(restored, AlternateSourceAttempt)
    assert restored.outcome is AlternateSourceSelectionOutcome.NO_RESULTS
    assert restored.result_count == 0
