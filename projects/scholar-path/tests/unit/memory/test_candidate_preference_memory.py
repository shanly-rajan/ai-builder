"""Unit tests for typed, Candidate-scoped preference learning."""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from scholarpath.domain import (
    CandidatePreferenceRevision,
    CandidateReviewAction,
    CandidateReviewDecision,
)
from scholarpath.memory import (
    CandidateMemoryKind,
    CandidateMemoryRecord,
    CandidateMemorySourceAction,
    PreferenceLearningAgent,
    deduplicate_candidate_memories,
    make_candidate_memory_record,
)
from tests.fakes import FakeCandidatePreferenceMemory
from tests.fixtures import make_search_plan, make_verified_supervisor

RECORDED_AT = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)


def _memory(
    kind: CandidateMemoryKind,
    value: str,
    *,
    source_action: CandidateMemorySourceAction = (
        CandidateMemorySourceAction.DIRECT_PREFERENCE_SUBMISSION
    ),
    recorded_at: datetime = RECORDED_AT,
    related_supervisor_id: str | None = None,
) -> CandidateMemoryRecord:
    return make_candidate_memory_record(
        kind,
        value,
        source_action,
        recorded_at,
        related_supervisor_id=related_supervisor_id,
    )


def test_candidate_memory_record_round_trips_without_candidate_personal_data() -> None:
    record = _memory(CandidateMemoryKind.PREFERRED_REGION, "Netherlands")

    restored = CandidateMemoryRecord.model_validate_json(record.model_dump_json())

    assert restored == record
    assert set(type(record).model_fields) == {
        "memory_id",
        "kind",
        "value",
        "source_action",
        "recorded_at",
        "related_supervisor_id",
    }
    assert "candidate_id" not in type(record).model_fields


def test_candidate_memory_record_rejects_a_tampered_semantic_identifier() -> None:
    payload = _memory(CandidateMemoryKind.PREFERRED_REGION, "Netherlands").model_dump(mode="python")
    payload["memory_id"] = "candidate-memory-tampered"

    with pytest.raises(ValidationError, match="identifier does not match"):
        CandidateMemoryRecord.model_validate(payload)


@pytest.mark.parametrize(
    ("field_name", "field_value"),
    [
        ("institution", "Northbridge University"),
        ("publication", "A purported publication"),
        ("availability_status", "confirmed_accepting"),
        ("evidence_url", "https://evidence.example.test/source"),
        ("research_fit_score", 91),
    ],
)
def test_candidate_memory_schema_rejects_supervisor_factual_fields(
    field_name: str,
    field_value: object,
) -> None:
    payload = _memory(
        CandidateMemoryKind.PREFERRED_RESEARCH_THEME,
        "responsible AI governance",
    ).model_dump(mode="python")
    payload[field_name] = field_value

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        CandidateMemoryRecord.model_validate(payload)


def test_candidate_a_cannot_retrieve_candidate_b_memories() -> None:
    candidate_a_record = _memory(CandidateMemoryKind.PREFERRED_REGION, "South Africa")
    candidate_b_record = _memory(CandidateMemoryKind.PREFERRED_REGION, "Netherlands")
    memory = FakeCandidatePreferenceMemory(
        {
            "candidate-a": (candidate_a_record,),
            "candidate-b": (candidate_b_record,),
        }
    )
    agent = PreferenceLearningAgent(memory)

    loaded_for_a = agent.load("candidate-a")
    loaded_for_b = agent.load("candidate-b")
    loaded_for_unknown = agent.load("candidate-unknown")

    assert loaded_for_a == (candidate_a_record,)
    assert loaded_for_b == (candidate_b_record,)
    assert loaded_for_unknown == ()
    assert candidate_b_record not in loaded_for_a
    assert memory.load_calls == ["candidate-a", "candidate-b", "candidate-unknown"]


def test_duplicate_preferences_are_normalized_and_retained_once() -> None:
    first = _memory(CandidateMemoryKind.PREFERRED_REGION, "Netherlands")
    normalized_duplicate = _memory(
        CandidateMemoryKind.PREFERRED_REGION,
        "  NETHERLANDS  ",
        recorded_at=RECORDED_AT + timedelta(minutes=1),
    )
    distinct = _memory(CandidateMemoryKind.PREFERRED_REGION, "South Africa")

    deduplicated = deduplicate_candidate_memories((first, normalized_duplicate, first, distinct))

    assert deduplicated == (first, distinct)
    assert first.memory_id == normalized_duplicate.memory_id


def test_preference_learning_outputs_only_candidate_actions_and_search_concepts() -> None:
    supervisor = make_verified_supervisor(1)
    search_plan = make_search_plan()
    rejection_reason = "The research orientation does not match my intended direction."
    decisions = (
        CandidateReviewDecision(
            action=CandidateReviewAction.APPROVE,
            supervisor_ids=(supervisor.supervisor_id,),
            reason="The Candidate approved this recommendation.",
        ),
        CandidateReviewDecision(
            action=CandidateReviewAction.REJECT,
            supervisor_ids=(supervisor.supervisor_id,),
            reason=rejection_reason,
        ),
        CandidateReviewDecision(
            action=CandidateReviewAction.REQUEST_MORE,
            supervisor_ids=(supervisor.supervisor_id,),
            reason="The Candidate directly submitted revised preferences.",
            revised_preferences=CandidatePreferenceRevision(
                research_topics=("public-sector AI assurance",),
                preferred_regions=("Netherlands",),
                preferred_study_modes=("part-time",),
                preferred_research_orientation="applied",
                methodological_interests=("design science",),
                constraints=("remote participation",),
                exclusions=("purely theoretical programmes",),
            ),
        ),
    )
    records = PreferenceLearningAgent(FakeCandidatePreferenceMemory()).records_from_actions(
        decisions, search_plan, RECORDED_AT
    )

    values_by_kind = {
        kind: {record.value for record in records if record.kind is kind}
        for kind in CandidateMemoryKind
    }
    assert values_by_kind[CandidateMemoryKind.USEFUL_SEARCH_CONCEPT] == set(
        search_plan.expanded_research_concepts
    )
    assert values_by_kind[CandidateMemoryKind.REJECTED_SUPERVISOR_REASON] == {rejection_reason}
    assert values_by_kind[CandidateMemoryKind.PREFERRED_RESEARCH_THEME] == {
        "public-sector AI assurance"
    }
    assert values_by_kind[CandidateMemoryKind.PREFERRED_REGION] == {"Netherlands"}

    serialized = "\n".join(record.model_dump_json() for record in records)
    forbidden_supervisor_facts = (
        supervisor.full_name,
        supervisor.institution,
        supervisor.department,
        str(supervisor.profile_url),
        supervisor.availability_status.value,
        *(claim.claim for claim in supervisor.evidence),
        *(str(claim.source_url) for claim in supervisor.evidence),
    )
    assert all(fact not in serialized for fact in forbidden_supervisor_facts)
    assert "overall_score" not in serialized
    assert "research_fit_score" not in serialized
