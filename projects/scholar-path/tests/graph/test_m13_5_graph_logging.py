"""Graph-level contracts for privacy-safe node and transition logging."""

from collections import Counter
from io import StringIO
from typing import cast

from langgraph.types import Command

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
    LogLevel,
)
from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    CandidateApproveResponse,
    ReviewStatus,
    ScholarPathState,
    build_scholarpath_runtime,
    build_walking_skeleton_fixtures,
    candidate_review_payload_from_graph_output,
    create_initial_state,
    default_review_decision,
    run_scholarpath_graph,
)
from scholarpath.observability import parse_json_log_line
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
    make_fixed_content_outcomes,
    make_graph_content_outcomes,
)


def _event_lines(stream: StringIO) -> list[dict[str, object]]:
    return [
        cast(dict[str, object], parse_json_log_line(line))
        for line in stream.getvalue().splitlines()
        if line.strip()
    ]


def test_full_fake_route_logs_every_node_and_transition_without_private_content(
    application_log_stream: StringIO,
) -> None:
    stream = application_log_stream
    fixtures = build_walking_skeleton_fixtures()
    # The Tavily fallback executes the first three fixture-backed queries. The
    # sixth profile is therefore retained for verification but is outside the
    # default five-Supervisor approval response, which lets this test exercise
    # one bounded evidence retry without invalidating the later approval gate.
    failed_profile_url = str(fixtures.raw_search_results[5].profile_url)
    content_outcomes: dict[str, ExtractedContent | Exception] = {
        **make_fixed_content_outcomes(),
        **make_graph_content_outcomes(),
    }
    content_outcomes[failed_profile_url] = ContentExtractionError(
        "SENSITIVE-PROVIDER-EXCEPTION must never enter application logs.",
        provider=ContentExtractionProvider.TAVILY,
        category=ContentExtractionErrorCategory.EXTRACTION_FAILED,
        retryable=True,
        source_url=failed_profile_url,
    )
    fake_review_model = FakeIndependentReviewModel()
    approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )

    state = cast(
        ScholarPathState,
        run_scholarpath_graph(
            thread_id="SENSITIVE-THREAD-ID",
            candidate_review_responses=(approval,),
            planning_model=FakePlanningModel(),
            supervisor_search=FakeSupervisorSearch(),
            tavily_search=FakeSupervisorSearch(),
            content_extractor=FakeContentExtraction(content_outcomes),
            evidence_model=FakeEvidenceVerificationModel(),
            research_fit_model=FakeResearchFitModel(),
            independent_review_model=fake_review_model,
            candidate_preference_memory=FakeCandidatePreferenceMemory(),
            application_settings=ApplicationSettings(
                environment=Environment.TEST,
                log_level=LogLevel.INFO,
                discovery_failure_mode=DiscoveryFailureMode.YOU_RETRYABLE_ERROR,
            ),
            langsmith_settings=LangSmithSettings(tracing=False),
        ),
    )

    events = _event_lines(stream)
    input_nodes = Counter(
        event.get("node") for event in events if event.get("event") == "graph.node.input"
    )
    output_nodes = Counter(
        event.get("node") for event in events if event.get("event") == "graph.node.output"
    )
    execution_counts = Counter(state["execution_log"])

    assert state["review_status"] is ReviewStatus.COMPLETED
    assert state["fallback_search_used"] is True
    assert state["retry_counts"]["evidence"] == 1
    assert set(CANONICAL_NODE_NAMES) <= set(input_nodes)
    assert set(CANONICAL_NODE_NAMES) <= set(output_nodes)
    for node_name in CANONICAL_NODE_NAMES:
        assert output_nodes[node_name] == execution_counts[node_name]
        expected_inputs = execution_counts[node_name] + (node_name == "candidate_review_gate")
        assert input_nodes[node_name] == expected_inputs

    assert any(event.get("event") == "graph.node.interrupt" for event in events)
    transitions = Counter(
        (event.get("source"), event.get("target"))
        for event in events
        if event.get("event") == "graph.transition"
    )
    assert transitions == Counter(
        {
            ("__start__", "load_candidate_preferences"): 1,
            ("load_candidate_preferences", "plan_supervisor_searches"): 1,
            ("plan_supervisor_searches", "discover_prospective_supervisors"): 1,
            ("discover_prospective_supervisors", "enough_supervisors_found"): 1,
            ("enough_supervisors_found", "fallback_supervisor_search"): 1,
            ("fallback_supervisor_search", "enough_supervisors_found"): 1,
            ("enough_supervisors_found", "deduplicate_supervisors"): 1,
            ("deduplicate_supervisors", "extract_supervisor_evidence"): 1,
            ("extract_supervisor_evidence", "supervisor_evidence_sufficient"): 2,
            ("supervisor_evidence_sufficient", "retry_alternate_evidence_source"): 1,
            ("retry_alternate_evidence_source", "extract_supervisor_evidence"): 1,
            ("supervisor_evidence_sufficient", "evaluate_research_fit"): 1,
            ("evaluate_research_fit", "review_fit_assessments"): 1,
            ("review_fit_assessments", "synthesize_supervisor_shortlist"): 1,
            ("synthesize_supervisor_shortlist", "candidate_review_gate"): 1,
            ("candidate_review_gate", "learn_candidate_preferences"): 1,
            ("learn_candidate_preferences", "save_shortlisted_supervisors"): 1,
            ("save_shortlisted_supervisors", "generate_shortlist_briefing"): 1,
            ("generate_shortlist_briefing", "__end__"): 1,
        }
    )

    assert fake_review_model.call_count == len(state["research_fit_assessments"])
    assert not any(
        event.get("event") == "provider.lifecycle" and event.get("provider") == "nebius"
        for event in events
    )

    serialized = stream.getvalue()
    sensitive_values = (
        "SENSITIVE-THREAD-ID",
        fixtures.candidate_profile.candidate_id,
        fixtures.candidate_profile.proposed_research_statement,
        fixtures.raw_search_results[0].full_name,
        fixtures.raw_search_results[0].institution,
        str(fixtures.raw_search_results[0].profile_url),
        "SENSITIVE-PROVIDER-EXCEPTION",
    )
    assert all(value not in serialized for value in sensitive_values)


def test_real_graph_pause_and_resume_log_interrupt_without_premature_output_or_save(
    application_log_stream: StringIO,
) -> None:
    stream = application_log_stream
    fixtures = build_walking_skeleton_fixtures()
    runtime = build_scholarpath_runtime(
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        candidate_preference_memory=FakeCandidatePreferenceMemory(),
        alternate_evidence_search=FakeSupervisorSearch(),
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            log_level=LogLevel.INFO,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
    )
    runnable_config = runtime.runnable_config("SENSITIVE-PAUSE-THREAD")

    paused = runtime.graph.invoke(
        create_initial_state(fixtures.candidate_profile),
        config=runnable_config,
    )
    payload = candidate_review_payload_from_graph_output(paused)
    assert payload is not None

    paused_events = _event_lines(stream)
    assert (
        sum(
            event.get("event") == "graph.node.input"
            and event.get("node") == "candidate_review_gate"
            for event in paused_events
        )
        == 1
    )
    assert (
        sum(
            event.get("event") == "graph.node.interrupt"
            and event.get("node") == "candidate_review_gate"
            for event in paused_events
        )
        == 1
    )
    assert not any(
        event.get("event") == "graph.node.output" and event.get("node") == "candidate_review_gate"
        for event in paused_events
    )
    assert not any(event.get("node") == "save_shortlisted_supervisors" for event in paused_events)
    assert "SENSITIVE-PAUSE-THREAD" not in stream.getvalue()

    approved_ids = tuple(item.supervisor_id for item in payload.proposed_supervisor_shortlist[:2])
    completed = runtime.graph.invoke(
        Command(
            resume=CandidateApproveResponse(
                action="approve",
                supervisor_ids=approved_ids,
            ).model_dump(mode="json")
        ),
        config=runnable_config,
    )
    completed_state = cast(ScholarPathState, completed)
    completed_events = _event_lines(stream)

    assert completed_state["review_status"] is ReviewStatus.COMPLETED
    assert (
        sum(
            event.get("event") == "graph.node.input"
            and event.get("node") == "candidate_review_gate"
            for event in completed_events
        )
        == 2
    )
    assert (
        sum(
            event.get("event") == "graph.node.output"
            and event.get("node") == "candidate_review_gate"
            for event in completed_events
        )
        == 1
    )
    assert any(
        event.get("event") == "graph.transition"
        and event.get("source") == "candidate_review_gate"
        and event.get("target") == "learn_candidate_preferences"
        for event in completed_events
    )
    assert any(
        event.get("event") == "graph.node.input"
        and event.get("node") == "save_shortlisted_supervisors"
        for event in completed_events
    )
