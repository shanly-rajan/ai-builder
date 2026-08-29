"""Pure tests for M11 form, progress, and graph-state presentation transforms."""

import json

import pytest
from pydantic import ValidationError

from scholarpath.graph import (
    CANONICAL_NODE_NAMES,
    ReviewStatus,
    build_walking_skeleton_fixtures,
    create_initial_state,
)
from scholarpath.ui import (
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
