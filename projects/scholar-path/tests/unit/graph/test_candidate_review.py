"""Unit tests for typed Candidate-review resume values and interrupt projections."""

import json
from dataclasses import dataclass

import pytest
from pydantic import BaseModel, ValidationError

from scholarpath.agents.independent_review import IndependentReviewAgent
from scholarpath.agents.shortlist_synthesis import ShortlistSynthesisAgent
from scholarpath.domain import ProposedSupervisorShortlist
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateRejectResponse,
    CandidateRequestMoreResponse,
    build_candidate_review_interrupt_payload,
    build_walking_skeleton_fixtures,
    candidate_review_payload_from_graph_output,
    candidate_review_response_value,
    parse_candidate_review_response,
)
from tests.fakes import FakeIndependentReviewModel


def _proposal() -> ProposedSupervisorShortlist:
    fixtures = build_walking_skeleton_fixtures()
    reviewer = IndependentReviewAgent(FakeIndependentReviewModel())
    reviews = tuple(
        reviewer.review(fixtures.candidate_profile, supervisor, assessment)
        for supervisor, assessment in zip(
            fixtures.verified_supervisors,
            fixtures.research_fit_assessments,
            strict=True,
        )
    )
    return ShortlistSynthesisAgent(max_results=5).synthesize(
        fixtures.candidate_profile.candidate_id,
        fixtures.verified_supervisors,
        fixtures.research_fit_assessments,
        fixtures.generated_at,
        reviews,
    )


@pytest.mark.parametrize(
    ("raw_response", "expected_type"),
    [
        (
            {
                "action": "approve",
                "supervisor_ids": ["supervisor-001", "supervisor-002"],
            },
            CandidateApproveResponse,
        ),
        (
            {
                "action": "reject",
                "rejections": [
                    {
                        "supervisor_id": "supervisor-001",
                        "reason": "The research orientation is outside my intended scope.",
                    },
                    {
                        "supervisor_id": "supervisor-002",
                        "reason": "The available study mode does not meet my constraints.",
                    },
                ],
            },
            CandidateRejectResponse,
        ),
        (
            {
                "action": "request_more",
                "revised_preferences": {
                    "preferred_regions": ["South Africa"],
                    "research_topics": ["responsible AI governance"],
                    "constraints": ["part-time study required"],
                    "exclusions": ["fully residential programmes"],
                },
            },
            CandidateRequestMoreResponse,
        ),
    ],
)
def test_candidate_review_response_schemas_accept_action_specific_values(
    raw_response: dict[str, object],
    expected_type: type[BaseModel],
) -> None:
    response = parse_candidate_review_response(raw_response)
    response_value = candidate_review_response_value(response)

    assert isinstance(response, expected_type)
    assert json.loads(json.dumps(response_value)) == response_value
    assert parse_candidate_review_response(response_value) == response


@pytest.mark.parametrize(
    "raw_response",
    [
        {"action": "approve", "supervisor_ids": []},
        {
            "action": "approve",
            "supervisor_ids": ["supervisor-001", "supervisor-001"],
        },
        {
            "action": "approve",
            "supervisor_ids": [f"supervisor-{index:03d}" for index in range(1, 7)],
        },
        {
            "action": "approve",
            "supervisor_ids": ["supervisor-001"],
            "reason": "Unexpected free-form field.",
        },
        {
            "action": "reject",
            "rejections": [
                {"supervisor_id": "supervisor-001", "reason": " "},
            ],
        },
        {
            "action": "reject",
            "rejections": [
                {"supervisor_id": "supervisor-001", "reason": "First reason."},
                {"supervisor_id": "supervisor-001", "reason": "Second reason."},
            ],
        },
        {"action": "request_more", "revised_preferences": {}},
        {"action": "defer", "supervisor_ids": ["supervisor-001"]},
    ],
)
def test_candidate_review_response_schemas_reject_ambiguous_or_malformed_values(
    raw_response: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        parse_candidate_review_response(raw_response)


def test_candidate_review_interrupt_payload_projects_required_evidence_without_page_content() -> (
    None
):
    fixtures = build_walking_skeleton_fixtures()
    proposal = _proposal()

    payload = build_candidate_review_interrupt_payload(
        proposal,
        review_iteration=1,
        maximum_review_iterations=3,
    )

    assert payload.kind == "candidate_review_required"
    assert payload.candidate_id == fixtures.candidate_profile.candidate_id
    assert payload.allowed_actions == ("approve", "reject", "request_more")
    assert len(payload.proposed_supervisor_shortlist) == 5
    for item, recommendation in zip(
        payload.proposed_supervisor_shortlist,
        proposal.recommendations,
        strict=True,
    ):
        assert item.supervisor_id == recommendation.supervisor.supervisor_id
        assert item.research_fit_score == recommendation.effective_score
        assert item.evidence_confidence is recommendation.evidence_confidence
        assert item.availability_status is recommendation.availability_status
        assert item.concerns == recommendation.concerns
        assert str(recommendation.supervisor.profile_url) in {
            str(link) for link in item.source_links
        }
        assert item.independent_review_outcome.review_status == (
            recommendation.independent_review.review_status
            if recommendation.independent_review is not None
            else "not_reviewed"
        )

    serialized = payload.model_dump_json()
    assert json.loads(serialized)["kind"] == "candidate_review_required"
    for forbidden_field in (
        "candidate_profile",
        "proposed_research_statement",
        "evidence",
        "claim",
        "supporting_excerpt",
        "api_key",
        "email",
    ):
        assert f'"{forbidden_field}"' not in serialized
    assert fixtures.candidate_profile.proposed_research_statement not in serialized
    first_claim = proposal.recommendations[0].supervisor.evidence[0]
    assert first_claim.claim not in serialized
    if first_claim.supporting_excerpt is not None:
        assert first_claim.supporting_excerpt not in serialized


@dataclass(frozen=True)
class _InterruptRecord:
    value: object


def test_candidate_review_payload_round_trips_from_langgraph_interrupt_output() -> None:
    payload = build_candidate_review_interrupt_payload(
        _proposal(),
        review_iteration=2,
        maximum_review_iterations=3,
        validation_error="The previous response referenced an unknown Supervisor.",
    )
    graph_output: dict[str, object] = {
        "__interrupt__": (_InterruptRecord(payload.model_dump(mode="json")),),
    }

    restored = candidate_review_payload_from_graph_output(graph_output)

    assert restored == payload
    assert restored is not None
    assert restored.validation_error == ("The previous response referenced an unknown Supervisor.")


@pytest.mark.parametrize(
    "graph_output",
    [
        {},
        {"__interrupt__": "not-an-interrupt-sequence"},
        {"__interrupt__": ()},
    ],
)
def test_candidate_review_payload_extraction_returns_none_without_an_interrupt(
    graph_output: dict[str, object],
) -> None:
    assert candidate_review_payload_from_graph_output(graph_output) is None
