"""Persistent Candidate preference memory boundaries and deterministic learning."""

from .mem0_adapter import MEMORY_SCHEMA, Mem0CandidatePreferenceAdapter
from .models import (
    CandidateMemoryKind,
    CandidateMemoryRecord,
    CandidateMemorySourceAction,
    candidate_memory_id,
    deduplicate_candidate_memories,
    make_candidate_memory_record,
    normalize_memory_value,
)
from .ports import CandidatePreferenceMemoryError, CandidatePreferenceMemoryPort
from .preference_learning import (
    PreferenceLearningAgent,
    project_memories_to_preference_revision,
)

__all__ = [
    "MEMORY_SCHEMA",
    "CandidateMemoryKind",
    "CandidateMemoryRecord",
    "CandidateMemorySourceAction",
    "CandidatePreferenceMemoryError",
    "CandidatePreferenceMemoryPort",
    "Mem0CandidatePreferenceAdapter",
    "PreferenceLearningAgent",
    "candidate_memory_id",
    "deduplicate_candidate_memories",
    "make_candidate_memory_record",
    "normalize_memory_value",
    "project_memories_to_preference_revision",
]
