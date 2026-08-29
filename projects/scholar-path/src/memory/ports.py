"""Provider-neutral boundary for persistent Candidate preference memory."""

from typing import Protocol

from .models import CandidateMemoryRecord


class CandidatePreferenceMemoryPort(Protocol):
    """Load and store durable preferences under one stable Candidate user ID."""

    def load(self, candidate_id: str) -> tuple[CandidateMemoryRecord, ...]:
        """Load ScholarPath preference records scoped to exactly one Candidate."""
        ...

    def store(
        self,
        candidate_id: str,
        records: tuple[CandidateMemoryRecord, ...],
    ) -> tuple[CandidateMemoryRecord, ...]:
        """Idempotently store records scoped to exactly one Candidate."""
        ...


class CandidatePreferenceMemoryError(RuntimeError):
    """Sanitized provider-boundary failure safe to record in graph state."""

    def __init__(self, operation: str) -> None:
        super().__init__(f"Candidate preference memory {operation} is unavailable.")
        self.operation = operation
