"""Unit tests for the safe ScholarPath checkpoint serialization boundary."""

import pytest
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from pydantic import BaseModel

from scholarpath.graph import (
    AlternateSourceAttempt,
    AlternateSourceRejectionCounts,
    AlternateSourceSelectionOutcome,
    SearchAttempt,
)
from scholarpath.graph.persistence import _checkpoint_serializer


class _UnregisteredModel(BaseModel):
    value: str


def _safe_messagepack_data(value: object) -> tuple[str, bytes]:
    return JsonPlusSerializer(allowed_msgpack_modules=None).dumps_typed(value)


def test_checkpoint_serializer_rejects_an_unregistered_application_model() -> None:
    serializer = _checkpoint_serializer()

    with pytest.raises(TypeError, match="Checkpoint model type is not registered"):
        serializer.dumps_typed(_UnregisteredModel(value="not registered"))


def test_checkpoint_serializer_rejects_a_tampered_model_marker() -> None:
    serializer = _checkpoint_serializer()
    serialized = _safe_messagepack_data(
        {
            "__scholarpath_checkpoint_model__": "malicious.module:UnexpectedType",
            "value": {},
        }
    )

    with pytest.raises(TypeError, match="unregistered ScholarPath model"):
        serializer.loads_typed(serialized)


def test_checkpoint_serializer_rejects_a_tampered_enum_marker() -> None:
    serializer = _checkpoint_serializer()
    serialized = _safe_messagepack_data(
        {
            "__scholarpath_checkpoint_enum__": "malicious.module:UnexpectedEnum",
            "value": "approved",
        }
    )

    with pytest.raises(TypeError, match="unregistered ScholarPath enum"):
        serializer.loads_typed(serialized)


def test_checkpoint_serializer_restores_pre_m11_2_search_attempts() -> None:
    serializer = _checkpoint_serializer()
    serialized = _safe_messagepack_data(
        {
            "__scholarpath_checkpoint_model__": ("scholarpath.graph.discovery:SearchAttempt"),
            "value": {
                "provider_used": "you.com",
                "query": "legacy persisted query",
                "attempt_number": 1,
                "result_count": 10,
                "plausible_supervisor_count": 4,
                "error_category": None,
                "retryable": False,
                "discovery_round": 1,
            },
        }
    )

    restored = serializer.loads_typed(serialized)

    assert isinstance(restored, SearchAttempt)
    assert restored.rejection_counts is None


def test_checkpoint_serializer_round_trips_privacy_safe_alternate_source_attempt() -> None:
    serializer = _checkpoint_serializer()
    attempt = AlternateSourceAttempt(
        supervisor_id="supervisor-001",
        attempt_number=1,
        discovery_round=2,
        outcome=AlternateSourceSelectionOutcome.REJECTED_ALL,
        result_count=2,
        eligible_result_count=0,
        rejection_counts=AlternateSourceRejectionCounts(
            exact_person_text_missing=1,
            exact_institution_text_missing=1,
        ),
    )

    restored = serializer.loads_typed(serializer.dumps_typed(attempt))

    assert restored == attempt
    assert isinstance(restored, AlternateSourceAttempt)
