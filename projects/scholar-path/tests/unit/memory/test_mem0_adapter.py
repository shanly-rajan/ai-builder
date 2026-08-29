"""Network-free contract tests for the hosted Mem0 adapter."""

from datetime import UTC, datetime
from typing import Any

import pytest
from pydantic import SecretStr

from scholarpath.config import Mem0MemoryConfiguration
from scholarpath.memory import (
    MEMORY_SCHEMA,
    CandidateMemoryKind,
    CandidateMemoryRecord,
    CandidateMemorySourceAction,
    CandidatePreferenceMemoryError,
    Mem0CandidatePreferenceAdapter,
    make_candidate_memory_record,
)


class _RecordingMem0Client:
    """Emulate the narrow SDK surface without importing or contacting Mem0."""

    def __init__(self, results: list[object] | None = None) -> None:
        self.results = list(results or ())
        self.get_all_calls: list[dict[str, object]] = []
        self.add_calls: list[tuple[object, dict[str, object]]] = []
        self.get_all_error: Exception | None = None
        self.add_error: Exception | None = None

    def get_all(self, **kwargs: object) -> dict[str, Any]:
        self.get_all_calls.append(kwargs)
        if self.get_all_error is not None:
            raise self.get_all_error
        return {"results": list(self.results)}

    def add(self, messages: object, **kwargs: object) -> dict[str, Any]:
        self.add_calls.append((messages, kwargs))
        if self.add_error is not None:
            raise self.add_error
        assert isinstance(messages, list)
        first_message = messages[0]
        assert isinstance(first_message, dict)
        content = first_message["content"]
        assert isinstance(content, str)
        metadata = kwargs["metadata"]
        assert isinstance(metadata, dict)
        self.results.append({"memory": content, "metadata": metadata})
        return {"status": "PENDING", "event_id": "synthetic-event"}


def _configuration() -> Mem0MemoryConfiguration:
    return Mem0MemoryConfiguration(
        api_key=SecretStr("not-a-real-mem0-secret"),
        timeout_seconds=5,
        memory_limit=25,
        telemetry=False,
    )


def _record(value: str = "Netherlands") -> CandidateMemoryRecord:
    return make_candidate_memory_record(
        CandidateMemoryKind.PREFERRED_REGION,
        value,
        CandidateMemorySourceAction.DIRECT_PREFERENCE_SUBMISSION,
        datetime(2026, 8, 29, 12, 0, tzinfo=UTC),
    )


def _mem0_result(record: CandidateMemoryRecord) -> dict[str, object]:
    return {
        "memory": record.model_dump_json(),
        "metadata": {
            "schema": MEMORY_SCHEMA,
            "record_key": record.memory_id,
            "memory_kind": record.kind.value,
        },
    }


def test_mem0_load_is_exactly_candidate_scoped_and_ignores_untrusted_records() -> None:
    record = _record()
    client = _RecordingMem0Client(
        [
            _mem0_result(record),
            {"memory": "not ScholarPath JSON", "metadata": {"schema": MEMORY_SCHEMA}},
            {"memory": record.model_dump_json(), "metadata": {"schema": "other-app"}},
        ]
    )
    adapter = Mem0CandidatePreferenceAdapter(_configuration(), client=client)

    loaded = adapter.load("candidate-a")

    assert loaded == (record,)
    assert client.get_all_calls == [
        {
            "filters": {"user_id": "candidate-a"},
            "page": 1,
            "page_size": 25,
        }
    ]


def test_mem0_store_uses_direct_import_candidate_scope_and_is_idempotent() -> None:
    record = _record("part-time study")
    client = _RecordingMem0Client()
    adapter = Mem0CandidatePreferenceAdapter(_configuration(), client=client)

    first_store = adapter.store("candidate-a", (record, record))
    second_store = adapter.store("candidate-a", (record,))

    assert first_store == (record,)
    assert second_store == ()
    assert len(client.add_calls) == 1
    messages, options = client.add_calls[0]
    assert messages == [{"role": "user", "content": record.model_dump_json()}]
    assert options["user_id"] == "candidate-a"
    assert options["infer"] is False
    assert options["metadata"] == {
        "schema": MEMORY_SCHEMA,
        "memory_kind": record.kind.value,
        "record_key": record.memory_id,
        "source_action": record.source_action.value,
    }
    assert "institution" not in record.model_dump_json()
    assert "evidence_url" not in record.model_dump_json()
    assert "research_fit_score" not in record.model_dump_json()


@pytest.mark.parametrize("operation", ["load", "store"])
def test_mem0_provider_failures_are_mapped_to_sanitized_typed_errors(operation: str) -> None:
    client = _RecordingMem0Client()
    sensitive_error = RuntimeError("provider detail containing secret-token")
    if operation == "load":
        client.get_all_error = sensitive_error
    else:
        client.add_error = sensitive_error
    adapter = Mem0CandidatePreferenceAdapter(_configuration(), client=client)

    with pytest.raises(CandidatePreferenceMemoryError) as captured:
        if operation == "load":
            adapter.load("candidate-a")
        else:
            adapter.store("candidate-a", (_record(),))

    assert captured.value.operation == operation
    assert "secret-token" not in str(captured.value)
