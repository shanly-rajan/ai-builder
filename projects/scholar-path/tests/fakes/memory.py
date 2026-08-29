"""Candidate-scoped, recording fake for persistent preference memory."""

from collections.abc import Mapping, Sequence

from scholarpath.memory import (
    CandidateMemoryRecord,
    CandidatePreferenceMemoryError,
    deduplicate_candidate_memories,
)


class FakeCandidatePreferenceMemory:
    """Provide deterministic Candidate isolation, recording, failures, and idempotency."""

    def __init__(
        self,
        seeded: Mapping[str, Sequence[CandidateMemoryRecord]] | None = None,
        *,
        load_error: Exception | None = None,
        store_error: Exception | None = None,
    ) -> None:
        self._records = {
            candidate_id: list(deduplicate_candidate_memories(records))
            for candidate_id, records in (seeded or {}).items()
        }
        self._load_error = load_error
        self._store_error = store_error
        self.load_calls: list[str] = []
        self.store_calls: list[tuple[str, tuple[CandidateMemoryRecord, ...]]] = []

    def load(self, candidate_id: str) -> tuple[CandidateMemoryRecord, ...]:
        """Return only records scoped under the requested stable Candidate ID."""
        self.load_calls.append(candidate_id)
        if self._load_error is not None:
            raise self._load_error
        return tuple(self._records.get(candidate_id, ()))

    def store(
        self,
        candidate_id: str,
        records: tuple[CandidateMemoryRecord, ...],
    ) -> tuple[CandidateMemoryRecord, ...]:
        """Record the scoped call and add only unseen deterministic record IDs."""
        batch = deduplicate_candidate_memories(records)
        self.store_calls.append((candidate_id, batch))
        if self._store_error is not None:
            raise self._store_error
        existing = self._records.setdefault(candidate_id, [])
        existing_ids = {record.memory_id for record in existing}
        stored: list[CandidateMemoryRecord] = []
        for record in batch:
            if record.memory_id not in existing_ids:
                existing.append(record)
                stored.append(record)
                existing_ids.add(record.memory_id)
        return tuple(stored)

    def records_for(self, candidate_id: str) -> tuple[CandidateMemoryRecord, ...]:
        """Inspect one Candidate scope without recording a provider call."""
        return tuple(self._records.get(candidate_id, ()))


def unavailable_candidate_memory(operation: str) -> CandidatePreferenceMemoryError:
    """Return the sanitized error normally produced by the Mem0 adapter."""
    return CandidatePreferenceMemoryError(operation)
