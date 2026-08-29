"""Pure tests for M11 form, progress, and graph-state presentation transforms."""

import json

import pytest
from pydantic import ValidationError

from scholarpath.domain import SearchResultRejectionCounts
from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    ReviewStatus,
    SearchAttempt,
    ToolErrorRecord,
    build_walking_skeleton_fixtures,
    create_initial_state,
)
from scholarpath.tools import SearchProvider
from scholarpath.ui import (
    UiDiscoveryRoute,
    UiStage,
    build_candidate_submission,
    build_request_more_response,
    canonical_node_names_from_stream_part,
    normalize_multi_value_input,
    project_graph_state_to_ui,
)
from scholarpath.ui.controller import progress_events_from_execution_log


def test_multi_value_form_input_is_normalized_and_stably_deduplicated() -> None:
    values = normalize_multi_value_input(
        " Responsible AI ; design science\nresponsible ai,  mixed   methods "
    )

    assert values == ("Responsible AI", "design science", "mixed methods")


def test_candidate_submission_normalizes_optional_and_required_fields() -> None:
    submission = build_candidate_submission(
        proposed_research_statement="  Study responsible AI governance.  ",
        research_topics="Responsible AI; enterprise architecture",
        preferred_regions="South Africa, Netherlands",
        study_modes=("Hybrid", "hybrid", "part-time"),
        research_orientation="No preference",
        methodological_interests="design science\nmixed methods",
        exclusions="fully residential programmes",
    )

    assert submission.proposed_research_statement == "Study responsible AI governance."
    assert submission.research_topics == ("Responsible AI", "enterprise architecture")
    assert submission.preferred_regions == ("South Africa", "Netherlands")
    assert submission.study_modes == ("Hybrid", "part-time")
    assert submission.research_orientation is None
    assert submission.methodological_interests == ("design science", "mixed methods")


@pytest.mark.parametrize(
    ("statement", "topics"),
    [
        ("", "responsible AI"),
        ("Study responsible AI governance.", "  ; , \n"),
    ],
)
def test_candidate_submission_rejects_missing_required_fields(
    statement: str,
    topics: str,
) -> None:
    with pytest.raises(ValidationError):
        build_candidate_submission(
            proposed_research_statement=statement,
            research_topics=topics,
            preferred_regions="",
            study_modes=(),
            research_orientation=None,
            methodological_interests="",
            exclusions="",
        )


def test_request_more_contains_only_explicitly_revised_preferences() -> None:
    response = build_request_more_response(
        research_topics="AI assurance; responsible AI",
        preferred_regions="Netherlands",
        study_modes=(),
        research_orientation="No change",
        methodological_interests="",
        constraints="part-time only",
        exclusions="",
    )

    revision = response.revised_preferences
    assert revision.research_topics == ("AI assurance", "responsible AI")
    assert revision.preferred_regions == ("Netherlands",)
    assert revision.constraints == ("part-time only",)
    assert revision.preferred_study_modes is None
    assert revision.preferred_research_orientation is None


def test_request_more_rejects_an_empty_revision() -> None:
    with pytest.raises(ValidationError):
        build_request_more_response(
            research_topics="",
            preferred_regions="",
            study_modes=(),
            research_orientation="No change",
            methodological_interests="",
            constraints="",
            exclusions="",
        )


def test_v2_progress_filter_returns_only_canonical_node_names_without_raw_updates() -> None:
    secret_statement = "private Candidate research statement"
    raw_page = "complete extracted university page content"
    part = {
        "type": "updates",
        "data": {
            "load_candidate_preferences": {
                "candidate_profile": {"proposed_research_statement": secret_statement}
            },
            "extract_supervisor_evidence": {"raw_page_content": raw_page},
            "untrusted_node": {"api_key": "secret-provider-key"},
        },
    }

    node_names = canonical_node_names_from_stream_part(part)
    rendered = json.dumps(node_names)

    assert node_names == (
        "load_candidate_preferences",
        "extract_supervisor_evidence",
    )
    assert secret_statement not in rendered
    assert raw_page not in rendered
    assert "secret-provider-key" not in rendered
    assert "untrusted_node" not in rendered


@pytest.mark.parametrize(
    "part",
    [
        {"type": "values", "data": {"load_candidate_preferences": {}}},
        {"type": "updates", "data": "not-a-mapping"},
        {"data": {"load_candidate_preferences": {}}},
        None,
    ],
)
def test_non_v2_update_parts_do_not_create_progress_events(part: object) -> None:
    assert canonical_node_names_from_stream_part(part) == ()


def test_execution_log_projection_discards_noncanonical_records() -> None:
    events = progress_events_from_execution_log(
        (
            "load_candidate_preferences",
            "raw_state_dump",
            "plan_supervisor_searches",
        )
    )

    assert [(event.sequence, event.node_name) for event in events] == [
        (1, "load_candidate_preferences"),
        (2, "plan_supervisor_searches"),
    ]
    assert all(event.node_name in CANONICAL_NODE_NAMES for event in events)


def test_graph_state_projection_exposes_verified_evidence_but_not_raw_graph_data() -> None:
    fixtures = build_walking_skeleton_fixtures()
    state = create_initial_state(fixtures.candidate_profile)
    supervisor = fixtures.verified_supervisors[0]
    assessment = fixtures.research_fit_assessments[0]
    private_statement = fixtures.candidate_profile.proposed_research_statement
    state["raw_search_results"] = list(fixtures.raw_search_results)
    state["verified_supervisors"] = [supervisor]
    state["research_fit_assessments"] = [assessment]
    state["review_status"] = ReviewStatus.PENDING
    state["execution_log"] = [
        "load_candidate_preferences",
        "extract_supervisor_evidence",
        "raw_state_dump",
    ]

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-ui-projection",
        review_payload=None,
    )
    rendered = snapshot.model_dump_json()
    view = snapshot.verified_supervisors[0]

    assert snapshot.stage is UiStage.VERIFIED_SUPERVISORS
    assert view.supervisor_id == supervisor.supervisor_id
    assert view.research_fit_score == assessment.overall_score
    assert {item.evidence_id for item in view.evidence_sources} == {
        item.evidence_id for item in supervisor.evidence
    }
    assert {str(item.source_url) for item in view.evidence_sources} == {
        str(item.source_url) for item in supervisor.evidence
    }
    assert str(supervisor.profile_url) in {str(item) for item in view.source_links}
    assert private_statement not in rendered
    assert "raw_search_results" not in rendered
    assert "raw_state_dump" not in rendered
    assert "supporting_excerpt" not in rendered


def test_graph_error_projection_groups_exact_duplicates_and_preserves_audit_count() -> None:
    fixtures = build_walking_skeleton_fixtures()
    state = create_initial_state(fixtures.candidate_profile)
    extraction_error = ToolErrorRecord(
        node="extract_supervisor_evidence",
        code="evidence_model_output",
        message="Evidence extraction returned invalid structured output.",
        recoverable=True,
    )
    alternate_error = ToolErrorRecord(
        node="retry_alternate_evidence_source",
        code="alternate_source_unavailable",
        message="No alternate official Supervisor source could be selected.",
        recoverable=True,
    )
    distinct_error = ToolErrorRecord(
        node="extract_supervisor_evidence",
        code="page_extraction_failed",
        message="A Supervisor source page could not be extracted.",
        recoverable=False,
    )
    state["tool_errors"] = [
        extraction_error,
        extraction_error,
        alternate_error,
        alternate_error,
        alternate_error,
        alternate_error,
        alternate_error,
        distinct_error,
    ]

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-grouped-ui-errors",
        review_payload=None,
    )

    assert [(item.code, item.occurrence_count) for item in snapshot.errors] == [
        ("evidence_model_output", 2),
        ("alternate_source_unavailable", 5),
        ("page_extraction_failed", 1),
    ]
    assert [item.recoverable for item in snapshot.errors] == [True, True, False]
    assert sum(item.occurrence_count for item in snapshot.errors) == len(state["tool_errors"])
    assert len(state["tool_errors"]) == 8


def test_discovery_diagnostics_expose_counts_but_drop_queries_and_result_content() -> None:
    fixtures = build_walking_skeleton_fixtures()
    state = create_initial_state(fixtures.candidate_profile)
    private_query = 'site:private.example "Candidate research statement"'
    state["discovery_round"] = 2
    state["search_attempts"] = [
        SearchAttempt(
            provider_used=SearchProvider.YOU,
            query="older private query",
            attempt_number=1,
            result_count=5,
            plausible_supervisor_count=2,
            discovery_round=1,
        ),
        SearchAttempt(
            provider_used=SearchProvider.YOU,
            query=private_query,
            attempt_number=1,
            result_count=0,
            plausible_supervisor_count=0,
            discovery_round=2,
        ),
        SearchAttempt(
            provider_used=SearchProvider.TAVILY,
            query=private_query,
            attempt_number=1,
            result_count=40,
            plausible_supervisor_count=0,
            discovery_round=2,
        ),
    ]
    state["fallback_search_used"] = True
    state["fallback_search_round"] = 2
    state["review_status"] = ReviewStatus.DISCOVERY_INCOMPLETE
    state["execution_log"] = [
        "discover_prospective_supervisors",
        "fallback_supervisor_search",
        "enough_supervisors_found",
    ]

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-safe-discovery-diagnostics",
        review_payload=None,
    )

    diagnostics = snapshot.discovery_diagnostics
    assert diagnostics is not None
    assert diagnostics.raw_result_count == 40
    assert diagnostics.plausible_supervisor_count == 0
    assert diagnostics.retained_prospective_supervisor_count == 0
    assert diagnostics.fallback_search_used is True
    assert diagnostics.route is UiDiscoveryRoute.STOPPED_RECOVERABLY
    assert diagnostics.rejection_counts is None
    assert [attempt.provider for attempt in diagnostics.attempts] == [
        SearchProvider.YOU,
        SearchProvider.TAVILY,
    ]
    rendered = snapshot.model_dump_json()
    assert private_query not in rendered
    assert "older private query" not in rendered
    assert "originating_query" not in rendered
    assert "raw_search_results" not in rendered


def test_discovery_diagnostics_aggregate_typed_rejections_without_result_content() -> None:
    fixtures = build_walking_skeleton_fixtures()
    state = create_initial_state(fixtures.candidate_profile)
    private_query = 'site:private.example "Sensitive Candidate topic"'
    state["discovery_round"] = 1
    state["search_attempts"] = [
        SearchAttempt(
            provider_used=SearchProvider.YOU,
            query=private_query,
            attempt_number=1,
            result_count=6,
            plausible_supervisor_count=2,
            rejection_counts=SearchResultRejectionCounts(
                person_not_established=1,
                academic_context_not_established=1,
                identity_conflict=1,
                institution_not_established=1,
            ),
            discovery_round=1,
        ),
        SearchAttempt(
            provider_used=SearchProvider.TAVILY,
            query=private_query,
            attempt_number=1,
            result_count=5,
            plausible_supervisor_count=1,
            rejection_counts=SearchResultRejectionCounts(
                person_not_established=1,
                academic_context_not_established=1,
                institution_not_established=1,
                incomplete_institution=1,
            ),
            discovery_round=1,
        ),
    ]
    state["fallback_search_used"] = True
    state["fallback_search_round"] = 1

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-typed-rejection-diagnostics",
        review_payload=None,
    )

    diagnostics = snapshot.discovery_diagnostics
    assert diagnostics is not None
    assert diagnostics.rejection_counts == SearchResultRejectionCounts(
        person_not_established=2,
        academic_context_not_established=2,
        identity_conflict=1,
        institution_not_established=2,
        incomplete_institution=1,
    )
    assert diagnostics.rejection_counts.total == 8
    assert all(attempt.rejection_counts is not None for attempt in diagnostics.attempts)
    rendered = snapshot.model_dump_json()
    assert private_query not in rendered
    assert "Sensitive Candidate topic" not in rendered
    assert "originating_query" not in rendered
