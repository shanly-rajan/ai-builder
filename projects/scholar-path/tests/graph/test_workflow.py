"""Graph tests for the deterministic ScholarPath M2 walking skeleton."""

from collections.abc import Callable

import pytest

from scholarpath.domain import (
    CandidatePreferenceRevision,
    CandidateReviewAction,
    CandidateReviewDecision,
    ProspectiveSupervisor,
    SupervisorLifecycleStatus,
    SupervisorShortlist,
    VerifiedSupervisor,
)
from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    build_scholarpath_graph,
    render_scholarpath_mermaid,
    run_scholarpath_graph,
)

HAPPY_PATH_LOG = [
    "load_candidate_preferences",
    "plan_supervisor_searches",
    "discover_prospective_supervisors",
    "enough_supervisors_found",
    "deduplicate_supervisors",
    "extract_supervisor_evidence",
    "supervisor_evidence_sufficient",
    "evaluate_research_fit",
    "review_fit_assessments",
    "synthesize_supervisor_shortlist",
    "candidate_review_gate_stub",
    "save_shortlisted_supervisors",
    "generate_shortlist_briefing",
]
RANKED_IDS = (
    "supervisor-001",
    "supervisor-002",
    "supervisor-004",
    "supervisor-003",
    "supervisor-005",
)
RANKED_IDS_AFTER_REJECTION = (
    "supervisor-001",
    "supervisor-002",
    "supervisor-004",
    "supervisor-003",
    "supervisor-006",
)


def _decision(
    action: CandidateReviewAction,
    supervisor_ids: tuple[str, ...] = RANKED_IDS,
    *,
    revised_preferences: CandidatePreferenceRevision | None = None,
) -> CandidateReviewDecision:
    return CandidateReviewDecision(
        action=action,
        supervisor_ids=supervisor_ids,
        reason=f"Deterministic fixture decision: {action.value}.",
        revised_preferences=revised_preferences,
    )


def test_normal_happy_path_has_the_exact_node_sequence() -> None:
    final_state = run_scholarpath_graph()

    assert final_state["execution_log"] == HAPPY_PATH_LOG
    assert final_state["retry_counts"] == {"discovery": 0, "evidence": 0, "review": 0}
    assert final_state["tool_errors"] == []
    assert len(final_state["shortlisted_supervisors"]) == 5


def test_insufficient_results_route_through_fallback_search() -> None:
    config = GraphFixtureConfig(primary_discovery_count=3, fallback_discovery_count=5)

    final_state = run_scholarpath_graph(config)

    log = final_state["execution_log"]
    assert log[:7] == [
        "load_candidate_preferences",
        "plan_supervisor_searches",
        "discover_prospective_supervisors",
        "enough_supervisors_found",
        "fallback_supervisor_search",
        "enough_supervisors_found",
        "deduplicate_supervisors",
    ]
    assert final_state["retry_counts"]["discovery"] == 1
    assert len(final_state["raw_search_results"]) == 8
    assert len(final_state["prospective_supervisors"]) == 8
    assert len({item.supervisor_id for item in final_state["prospective_supervisors"]}) == 8


def test_insufficient_evidence_routes_through_alternate_retrieval() -> None:
    config = GraphFixtureConfig(initial_evidence_count=2, alternate_evidence_count=6)

    final_state = run_scholarpath_graph(config)

    log = final_state["execution_log"]
    first_extract = log.index("extract_supervisor_evidence")
    assert log[first_extract : first_extract + 5] == [
        "extract_supervisor_evidence",
        "supervisor_evidence_sufficient",
        "retry_alternate_evidence_source",
        "extract_supervisor_evidence",
        "supervisor_evidence_sufficient",
    ]
    assert final_state["retry_counts"]["evidence"] == 1
    assert len(final_state["verified_supervisors"]) == 6
    assert len(final_state["research_fit_assessments"]) == 6


def test_candidate_approval_reaches_end_with_shortlisted_statuses() -> None:
    final_state = run_scholarpath_graph()

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert final_state["execution_log"][-2:] == [
        "save_shortlisted_supervisors",
        "generate_shortlist_briefing",
    ]
    assert final_state["candidate_feedback"][-1].action is CandidateReviewAction.APPROVE
    assert all(
        supervisor.status is SupervisorLifecycleStatus.SHORTLISTED
        for supervisor in final_state["shortlisted_supervisors"]
    )


def test_candidate_rejection_records_feedback_and_returns_to_planning() -> None:
    reject = _decision(CandidateReviewAction.REJECT, ("supervisor-005",))
    approve_remaining = _decision(
        CandidateReviewAction.APPROVE,
        RANKED_IDS_AFTER_REJECTION,
    )
    config = GraphFixtureConfig(review_decisions=(reject, approve_remaining))

    final_state = run_scholarpath_graph(config)

    rejected = final_state["rejected_supervisors"]
    assert [item.supervisor_id for item in rejected] == ["supervisor-005"]
    assert rejected[0].status is SupervisorLifecycleStatus.REJECTED
    assert [decision.action for decision in final_state["candidate_feedback"]] == [
        CandidateReviewAction.REJECT,
        CandidateReviewAction.APPROVE,
    ]
    assert final_state["execution_log"].count("plan_supervisor_searches") == 2
    assert final_state["execution_log"].count("candidate_review_gate_stub") == 2
    assert final_state["retry_counts"]["review"] == 1
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    shortlisted_ids = tuple(item.supervisor_id for item in final_state["shortlisted_supervisors"])
    assert shortlisted_ids == RANKED_IDS_AFTER_REJECTION
    assert all(
        item.status is SupervisorLifecycleStatus.SHORTLISTED
        for item in final_state["shortlisted_supervisors"]
    )
    assert final_state["supervisor_shortlist"] is not None
    assert final_state["supervisor_shortlist"].shortlisted_supervisors == tuple(
        final_state["shortlisted_supervisors"]
    )


def test_request_more_records_preferences_and_returns_to_search_planning() -> None:
    revision = CandidatePreferenceRevision(preferred_regions=("Netherlands",))
    request_more = _decision(
        CandidateReviewAction.REQUEST_MORE,
        revised_preferences=revision,
    )
    approve = _decision(CandidateReviewAction.APPROVE)
    config = GraphFixtureConfig(review_decisions=(request_more, approve))

    final_state = run_scholarpath_graph(config)

    assert [decision.action for decision in final_state["candidate_feedback"]] == [
        CandidateReviewAction.REQUEST_MORE,
        CandidateReviewAction.APPROVE,
    ]
    assert final_state["candidate_preferences"][-1] == revision
    assert final_state["search_plan"] is not None
    assert final_state["search_plan"].target_regions == ("Netherlands",)
    assert final_state["execution_log"].count("plan_supervisor_searches") == 2
    assert final_state["execution_log"].count("candidate_review_gate_stub") == 2
    assert final_state["retry_counts"]["review"] == 1
    assert final_state["rejected_supervisors"] == []
    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len({item.supervisor_id for item in final_state["shortlisted_supervisors"]}) == 5


@pytest.mark.parametrize(
    ("config_factory", "error_code", "last_node", "retry_key", "retry_node", "node_count"),
    [
        (
            lambda: GraphFixtureConfig(
                primary_discovery_count=2,
                fallback_discovery_count=0,
                max_discovery_retries=1,
            ),
            "discovery_retry_exhausted",
            "enough_supervisors_found",
            "discovery",
            "fallback_supervisor_search",
            1,
        ),
        (
            lambda: GraphFixtureConfig(
                initial_evidence_count=2,
                alternate_evidence_count=2,
                max_evidence_retries=1,
            ),
            "evidence_retry_exhausted",
            "supervisor_evidence_sufficient",
            "evidence",
            "retry_alternate_evidence_source",
            1,
        ),
        (
            lambda: GraphFixtureConfig(
                review_decisions=(
                    _decision(CandidateReviewAction.REQUEST_MORE),
                    _decision(CandidateReviewAction.REQUEST_MORE),
                ),
                max_review_retries=1,
            ),
            "review_retry_exhausted",
            "candidate_review_gate_stub",
            "review",
            "plan_supervisor_searches",
            2,
        ),
    ],
)
def test_retry_exhaustion_stops_cleanly_without_recursion_failure(
    config_factory: Callable[[], GraphFixtureConfig],
    error_code: str,
    last_node: str,
    retry_key: str,
    retry_node: str,
    node_count: int,
) -> None:
    final_state = run_scholarpath_graph(config_factory())

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert len(final_state["tool_errors"]) == 1
    assert final_state["tool_errors"][0].code == error_code
    assert final_state["tool_errors"][0].recoverable is False
    assert final_state["execution_log"][-1] == last_node
    assert final_state["execution_log"].count(retry_node) == node_count
    assert final_state["retry_counts"][retry_key] == 1
    assert "generate_shortlist_briefing" not in final_state["execution_log"]
    assert final_state["supervisor_shortlist"] is None


def test_maximum_configured_discovery_retries_exhaust_through_domain_state() -> None:
    config = GraphFixtureConfig(
        primary_discovery_count=2,
        fallback_discovery_count=0,
        max_discovery_retries=5,
    )

    final_state = run_scholarpath_graph(config)

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["retry_counts"]["discovery"] == 5
    assert final_state["execution_log"].count("fallback_supervisor_search") == 5
    assert final_state["execution_log"].count("enough_supervisors_found") == 6
    assert final_state["tool_errors"][0].code == "discovery_retry_exhausted"


def test_maximum_configured_review_retries_exhaust_through_domain_state() -> None:
    request_more = _decision(CandidateReviewAction.REQUEST_MORE)
    config = GraphFixtureConfig(
        review_decisions=(request_more,) * 6,
        max_review_retries=5,
    )

    final_state = run_scholarpath_graph(config)

    assert final_state["review_status"] is ReviewStatus.RETRY_EXHAUSTED
    assert final_state["retry_counts"]["review"] == 5
    assert final_state["execution_log"].count("plan_supervisor_searches") == 6
    assert final_state["execution_log"].count("candidate_review_gate_stub") == 6
    assert final_state["tool_errors"][0].code == "review_retry_exhausted"


def test_graph_paths_never_use_candidate_as_a_supervisor_label() -> None:
    graph = build_scholarpath_graph().get_graph()
    graph_node_names = set(graph.nodes)
    candidate_nodes = {name for name in graph_node_names if "candidate" in name.casefold()}

    assert set(CANONICAL_NODE_NAMES) <= graph_node_names
    assert candidate_nodes == {"load_candidate_preferences", "candidate_review_gate_stub"}

    mermaid = render_scholarpath_mermaid().casefold()
    for banned_phrase in (
        "supervisor candidate",
        "supervisor_candidate",
        "supervisor-candidate",
        "approved candidate",
    ):
        assert banned_phrase not in mermaid

    final_state = run_scholarpath_graph()
    supervisor_collections: tuple[list[ProspectiveSupervisor] | list[VerifiedSupervisor], ...] = (
        final_state["prospective_supervisors"],
        final_state["verified_supervisors"],
        final_state["proposed_shortlist"],
        final_state["shortlisted_supervisors"],
        final_state["rejected_supervisors"],
    )
    assert all(
        "candidate" not in supervisor.supervisor_id.casefold()
        for collection in supervisor_collections
        for supervisor in collection
    )
    assert all(
        isinstance(supervisor, ProspectiveSupervisor)
        for supervisor in final_state["prospective_supervisors"]
    )
    assert all(
        isinstance(supervisor, VerifiedSupervisor)
        for collection in supervisor_collections[1:]
        for supervisor in collection
    )


def test_final_state_satisfies_supervisor_shortlist_validation() -> None:
    final_state: ScholarPathState = run_scholarpath_graph()
    shortlist = final_state["supervisor_shortlist"]

    assert shortlist is not None
    restored = SupervisorShortlist.model_validate_json(shortlist.model_dump_json())
    assert restored == shortlist
    assert restored.candidate_id == final_state["candidate_profile"].candidate_id
    assert tuple(item.supervisor_id for item in restored.shortlisted_supervisors) == RANKED_IDS
    assert final_state["shortlist_briefing"] is not None
    reconstructed = SupervisorShortlist(
        candidate_id=final_state["candidate_profile"].candidate_id,
        shortlisted_supervisors=tuple(final_state["shortlisted_supervisors"]),
        generated_at=restored.generated_at,
        briefing=final_state["shortlist_briefing"],
    )
    assert reconstructed == restored
    assert all(
        supervisor.candidate_review_decision is not None
        and supervisor.candidate_review_decision.action is CandidateReviewAction.APPROVE
        for supervisor in restored.shortlisted_supervisors
    )
    assert len({item.supervisor_id for item in restored.shortlisted_supervisors}) == 5
    assert all(item.evidence for item in restored.shortlisted_supervisors)
