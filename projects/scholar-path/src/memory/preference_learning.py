"""Deterministic Candidate preference learning without model inference."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from ..domain import (
    CandidatePreferenceRevision,
    CandidateProfile,
    CandidateReviewAction,
    CandidateReviewDecision,
    SearchPlan,
)
from .models import (
    CandidateMemoryKind,
    CandidateMemoryRecord,
    CandidateMemorySourceAction,
    deduplicate_candidate_memories,
    make_candidate_memory_record,
    normalize_memory_value,
)
from .ports import CandidatePreferenceMemoryPort


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in values:
        unique.setdefault(normalize_memory_value(value), value.strip())
    return tuple(unique.values())


def project_memories_to_preference_revision(
    candidate_profile: CandidateProfile,
    records: tuple[CandidateMemoryRecord, ...],
) -> CandidatePreferenceRevision | None:
    """Merge recalled preference fields with current profile values for planning."""
    by_kind: dict[CandidateMemoryKind, list[str]] = {}
    for record in records:
        by_kind.setdefault(record.kind, []).append(record.value)

    planning_kinds = {
        CandidateMemoryKind.PREFERRED_RESEARCH_THEME,
        CandidateMemoryKind.PREFERRED_REGION,
        CandidateMemoryKind.PREFERRED_STUDY_MODE,
        CandidateMemoryKind.PREFERRED_RESEARCH_ORIENTATION,
        CandidateMemoryKind.METHODOLOGICAL_PREFERENCE,
        CandidateMemoryKind.CANDIDATE_CONSTRAINT,
        CandidateMemoryKind.EXCLUDED_RESEARCH_AREA,
        CandidateMemoryKind.USEFUL_SEARCH_CONCEPT,
    }
    if not set(by_kind).intersection(planning_kinds):
        return None

    themes = (
        *candidate_profile.research_topics,
        *by_kind.get(CandidateMemoryKind.PREFERRED_RESEARCH_THEME, ()),
        *by_kind.get(CandidateMemoryKind.USEFUL_SEARCH_CONCEPT, ()),
    )
    regions = (
        *candidate_profile.preferred_regions,
        *by_kind.get(CandidateMemoryKind.PREFERRED_REGION, ()),
    )
    study_modes = (
        *candidate_profile.preferred_study_modes,
        *by_kind.get(CandidateMemoryKind.PREFERRED_STUDY_MODE, ()),
    )
    methodologies = (
        *candidate_profile.methodological_interests,
        *by_kind.get(CandidateMemoryKind.METHODOLOGICAL_PREFERENCE, ()),
    )
    exclusions = (
        *candidate_profile.exclusions,
        *by_kind.get(CandidateMemoryKind.EXCLUDED_RESEARCH_AREA, ()),
    )
    remembered_orientations = by_kind.get(CandidateMemoryKind.PREFERRED_RESEARCH_ORIENTATION, [])
    orientation = candidate_profile.preferred_research_orientation
    if orientation is None and remembered_orientations:
        orientation = remembered_orientations[-1]

    return CandidatePreferenceRevision(
        research_topics=_ordered_unique(themes),
        preferred_regions=_ordered_unique(regions),
        preferred_study_modes=_ordered_unique(study_modes),
        preferred_research_orientation=orientation,
        methodological_interests=_ordered_unique(methodologies),
        constraints=_ordered_unique(by_kind.get(CandidateMemoryKind.CANDIDATE_CONSTRAINT, ())),
        exclusions=_ordered_unique(exclusions),
    )


class PreferenceLearningAgent:
    """Recall and persist only the finite durable Candidate preference allowlist."""

    def __init__(self, memory: CandidatePreferenceMemoryPort) -> None:
        self._memory = memory

    def load(self, candidate_id: str) -> tuple[CandidateMemoryRecord, ...]:
        """Load and deterministically deduplicate one Candidate's durable memories."""
        records = self._memory.load(candidate_id)
        ordered = sorted(records, key=lambda item: (item.recorded_at, item.memory_id))
        return deduplicate_candidate_memories(ordered)

    def store(
        self,
        candidate_id: str,
        records: tuple[CandidateMemoryRecord, ...],
    ) -> tuple[CandidateMemoryRecord, ...]:
        """Store a deduplicated batch through the scoped memory boundary."""
        deduplicated = deduplicate_candidate_memories(records)
        if not deduplicated:
            return ()
        return self._memory.store(candidate_id, deduplicated)

    def records_from_actions(
        self,
        decisions: tuple[CandidateReviewDecision, ...],
        search_plan: SearchPlan | None,
        recorded_at: datetime,
    ) -> tuple[CandidateMemoryRecord, ...]:
        """Project explicit Candidate actions into the durable memory allowlist."""
        records: list[CandidateMemoryRecord] = []
        for decision in decisions:
            if decision.action is CandidateReviewAction.APPROVE:
                if search_plan is None:
                    continue
                records.extend(
                    make_candidate_memory_record(
                        CandidateMemoryKind.USEFUL_SEARCH_CONCEPT,
                        concept,
                        CandidateMemorySourceAction.APPROVAL,
                        recorded_at,
                    )
                    for concept in search_plan.expanded_research_concepts
                )
            elif decision.action is CandidateReviewAction.REJECT:
                records.extend(
                    make_candidate_memory_record(
                        CandidateMemoryKind.REJECTED_SUPERVISOR_REASON,
                        decision.reason,
                        CandidateMemorySourceAction.REJECTION,
                        recorded_at,
                        related_supervisor_id=supervisor_id,
                    )
                    for supervisor_id in decision.supervisor_ids
                )
            elif decision.revised_preferences is not None:
                records.extend(
                    self.records_from_preference_submission(
                        decision.revised_preferences,
                        recorded_at,
                    )
                )
        return deduplicate_candidate_memories(records)

    @staticmethod
    def records_from_preference_submission(
        revision: CandidatePreferenceRevision,
        recorded_at: datetime,
    ) -> tuple[CandidateMemoryRecord, ...]:
        """Persist an explicit preference submission as atomic typed records."""
        source = CandidateMemorySourceAction.DIRECT_PREFERENCE_SUBMISSION
        field_mapping: tuple[tuple[tuple[str, ...] | None, CandidateMemoryKind], ...] = (
            (revision.research_topics, CandidateMemoryKind.PREFERRED_RESEARCH_THEME),
            (revision.preferred_regions, CandidateMemoryKind.PREFERRED_REGION),
            (revision.preferred_study_modes, CandidateMemoryKind.PREFERRED_STUDY_MODE),
            (
                (revision.preferred_research_orientation,)
                if revision.preferred_research_orientation is not None
                else None,
                CandidateMemoryKind.PREFERRED_RESEARCH_ORIENTATION,
            ),
            (
                revision.methodological_interests,
                CandidateMemoryKind.METHODOLOGICAL_PREFERENCE,
            ),
            (revision.constraints, CandidateMemoryKind.CANDIDATE_CONSTRAINT),
            (revision.exclusions, CandidateMemoryKind.EXCLUDED_RESEARCH_AREA),
        )
        records = (
            make_candidate_memory_record(kind, value, source, recorded_at)
            for values, kind in field_mapping
            if values is not None
            for value in values
        )
        return deduplicate_candidate_memories(records)
