"""Typed, privacy-minimizing contracts for durable Candidate preferences."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    StringConstraints,
    model_validator,
)

NonEmptyMemoryText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CandidateMemoryKind(StrEnum):
    """Finite allowlist of durable Candidate information ScholarPath may remember."""

    PREFERRED_RESEARCH_THEME = "preferred_research_theme"
    PREFERRED_REGION = "preferred_region"
    PREFERRED_STUDY_MODE = "preferred_study_mode"
    PREFERRED_RESEARCH_ORIENTATION = "preferred_research_orientation"
    METHODOLOGICAL_PREFERENCE = "methodological_preference"
    CANDIDATE_CONSTRAINT = "candidate_constraint"
    EXCLUDED_RESEARCH_AREA = "excluded_research_area"
    REJECTED_SUPERVISOR_REASON = "rejected_supervisor_reason"
    USEFUL_SEARCH_CONCEPT = "useful_search_concept"


class CandidateMemorySourceAction(StrEnum):
    """Explicit Candidate actions that are permitted to create durable memory."""

    APPROVAL = "approval"
    REJECTION = "rejection"
    DIRECT_PREFERENCE_SUBMISSION = "direct_preference_submission"


class CandidateMemoryRecord(BaseModel):
    """One durable preference record without Candidate identity or Supervisor facts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    memory_id: NonEmptyMemoryText
    kind: CandidateMemoryKind
    value: NonEmptyMemoryText
    source_action: CandidateMemorySourceAction
    recorded_at: AwareDatetime
    related_supervisor_id: NonEmptyMemoryText | None = None

    @model_validator(mode="after")
    def rejection_relationship_must_be_explicit(self) -> Self:
        """Allow a Supervisor identifier only for a Candidate-authored rejection reason."""
        is_rejection = self.kind is CandidateMemoryKind.REJECTED_SUPERVISOR_REASON
        if is_rejection and self.related_supervisor_id is None:
            raise ValueError("A rejected Supervisor reason requires a Supervisor identifier")
        if not is_rejection and self.related_supervisor_id is not None:
            raise ValueError("Only a rejected Supervisor reason may identify a Supervisor")
        if is_rejection and self.source_action is not CandidateMemorySourceAction.REJECTION:
            raise ValueError("A rejected Supervisor reason must originate from rejection")
        expected_memory_id = candidate_memory_id(
            self.kind,
            self.value,
            related_supervisor_id=self.related_supervisor_id,
        )
        if self.memory_id != expected_memory_id:
            raise ValueError("Candidate memory identifier does not match its normalized value")
        return self


def normalize_memory_value(value: str) -> str:
    """Normalize whitespace and case only for comparison and deterministic identifiers."""
    return " ".join(value.casefold().split())


def candidate_memory_id(
    kind: CandidateMemoryKind,
    value: str,
    *,
    related_supervisor_id: str | None = None,
) -> str:
    """Build a stable semantic key without including Candidate identity or personal data."""
    normalized_supervisor_id = normalize_memory_value(related_supervisor_id or "")
    semantic_value = "\x1f".join(
        (kind.value, normalize_memory_value(value), normalized_supervisor_id)
    )
    digest = hashlib.sha256(semantic_value.encode("utf-8")).hexdigest()[:24]
    return f"candidate-memory-{digest}"


def make_candidate_memory_record(
    kind: CandidateMemoryKind,
    value: str,
    source_action: CandidateMemorySourceAction,
    recorded_at: datetime,
    *,
    related_supervisor_id: str | None = None,
) -> CandidateMemoryRecord:
    """Construct a record whose identifier is derived from its normalized meaning."""
    return CandidateMemoryRecord(
        memory_id=candidate_memory_id(
            kind,
            value,
            related_supervisor_id=related_supervisor_id,
        ),
        kind=kind,
        value=value,
        source_action=source_action,
        recorded_at=recorded_at,
        related_supervisor_id=related_supervisor_id,
    )


def deduplicate_candidate_memories(
    records: Iterable[CandidateMemoryRecord],
) -> tuple[CandidateMemoryRecord, ...]:
    """Keep the first value for each normalized semantic preference in stable order."""
    unique: dict[tuple[CandidateMemoryKind, str, str], CandidateMemoryRecord] = {}
    for record in records:
        key = (
            record.kind,
            normalize_memory_value(record.value),
            normalize_memory_value(record.related_supervisor_id or ""),
        )
        unique.setdefault(key, record)
    return tuple(unique.values())
