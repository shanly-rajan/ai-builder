"""Provider-neutral contracts and orchestration for research planning."""

from __future__ import annotations

import re
from enum import StrEnum
from typing import Protocol, Self

from pydantic import BaseModel, ConfigDict, ValidationError, field_validator, model_validator

from ..domain import (
    CandidatePreferenceRevision,
    CandidateProfile,
    PlannedSearchQuery,
    SearchPlan,
    SearchSourceType,
)
from ..memory.models import CandidateMemoryRecord

MAX_PLANNING_OUTPUT_ATTEMPTS = 2
MAX_SITE_FILTERS_PER_QUERY = 1
MAX_BOOLEAN_OPERATORS_PER_QUERY = 2
MAX_QUOTED_PHRASES_PER_QUERY = 1

_SITE_FILTER_PATTERN = re.compile(r"(?<![\w-])site\s*:\s*[^\s()]+", re.IGNORECASE)
_BOOLEAN_OPERATOR_PATTERN = re.compile(r"\b(?:AND|OR|NOT)\b")
_QUOTED_PHRASE_PATTERN = re.compile(r'"[^"\n]+"|“[^”\n]+”')


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


class PlanningInput(BaseModel):
    """Identity-free data sent across the planning model boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    proposed_research_statement: str
    research_topics: tuple[str, ...]
    preferred_study_modes: tuple[str, ...]
    preferred_research_orientation: str | None
    methodological_interests: tuple[str, ...]
    remembered_candidate_preferences: tuple[CandidatePreferenceRevision, ...]
    target_regions: tuple[str, ...]
    exclusions: tuple[str, ...]
    remembered_candidate_memories: tuple[CandidateMemoryRecord, ...] = ()

    @classmethod
    def from_candidate_profile(
        cls,
        candidate_profile: CandidateProfile,
        remembered_candidate_preferences: tuple[CandidatePreferenceRevision, ...],
        *,
        remembered_candidate_memories: tuple[CandidateMemoryRecord, ...] = (),
        target_regions: tuple[str, ...],
        exclusions: tuple[str, ...],
    ) -> Self:
        """Map planning-relevant profile data without exposing Candidate identity."""
        return cls(
            proposed_research_statement=candidate_profile.proposed_research_statement,
            research_topics=candidate_profile.research_topics,
            preferred_study_modes=candidate_profile.preferred_study_modes,
            preferred_research_orientation=candidate_profile.preferred_research_orientation,
            methodological_interests=candidate_profile.methodological_interests,
            remembered_candidate_preferences=remembered_candidate_preferences,
            remembered_candidate_memories=remembered_candidate_memories,
            target_regions=target_regions,
            exclusions=exclusions,
        )


class PlanningSearchQueryResponse(BaseModel):
    """OpenAI-compatible structured representation of one planned query."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )

    query: str
    purpose: str
    target_source_types: list[SearchSourceType]

    @field_validator("query", "purpose")
    @classmethod
    def text_must_not_be_blank(cls, value: str) -> str:
        """Reject prose fields that contain only whitespace."""
        if not value.strip():
            raise ValueError("Planning query text and purpose must not be blank")
        return value

    @field_validator("query")
    @classmethod
    def query_syntax_must_remain_provider_portable(cls, value: str) -> str:
        """Reject deterministic signs of an over-constrained provider query."""
        if len(_SITE_FILTER_PATTERN.findall(value)) > MAX_SITE_FILTERS_PER_QUERY:
            raise ValueError("Search query must contain at most one site: filter")
        if len(_BOOLEAN_OPERATOR_PATTERN.findall(value)) > MAX_BOOLEAN_OPERATORS_PER_QUERY:
            raise ValueError("Search query must contain at most two explicit Boolean operators")
        if len(_QUOTED_PHRASE_PATTERN.findall(value)) > MAX_QUOTED_PHRASES_PER_QUERY:
            raise ValueError("Search query must contain at most one quoted phrase")
        return value

    @model_validator(mode="after")
    def source_types_must_be_nonempty_and_unique(self) -> Self:
        """Require at least one distinct source category for each query."""
        if not self.target_source_types:
            raise ValueError("Each search query must target at least one source type")
        if len(self.target_source_types) != len(set(self.target_source_types)):
            raise ValueError("Target source types must be unique within a search query")
        return self


class StructuredSearchPlanResponse(BaseModel):
    """Typed model output accepted by ScholarPath's planning boundary."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        revalidate_instances="always",
        str_strip_whitespace=True,
    )

    expanded_research_concepts: list[str]
    search_queries: list[PlanningSearchQueryResponse]
    rationale: str

    @field_validator("expanded_research_concepts")
    @classmethod
    def concepts_must_be_nonempty_and_distinct(cls, values: list[str]) -> list[str]:
        """Reject empty or repeated concept expansions deterministically."""
        normalized = [_normalized_text(value) for value in values]
        if not normalized or any(not value for value in normalized):
            raise ValueError("At least one non-empty expanded research concept is required")
        if len(normalized) != len(set(normalized)):
            raise ValueError("Expanded research concepts must be distinct")
        return values

    @field_validator("rationale")
    @classmethod
    def rationale_must_not_be_blank(cls, value: str) -> str:
        """Reject an empty planning rationale."""
        if not value.strip():
            raise ValueError("Planning rationale must not be blank")
        return value

    @model_validator(mode="after")
    def queries_must_be_distinct_and_cover_required_sources(self) -> Self:
        """Enforce the M3 query count, uniqueness, and source coverage contract."""
        if not 4 <= len(self.search_queries) <= 8:
            raise ValueError("A planning response must contain four to eight search queries")
        normalized_queries = [_normalized_text(item.query) for item in self.search_queries]
        if len(normalized_queries) != len(set(normalized_queries)):
            raise ValueError("Search queries must be distinct")

        covered_sources = {
            source_type
            for query in self.search_queries
            for source_type in query.target_source_types
        }
        missing_sources = set(SearchSourceType) - covered_sources
        if missing_sources:
            missing_values = ", ".join(sorted(item.value for item in missing_sources))
            raise ValueError(f"Planning response is missing target source types: {missing_values}")
        return self


class PlanningModelPort(Protocol):
    """Provider-neutral interface implemented by planning model adapters and fakes."""

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        """Generate one typed planning response without executing any search."""
        ...


class PlanningModelError(RuntimeError):
    """Base error raised by a planning model adapter."""


class PlanningModelInvocationError(PlanningModelError):
    """A model request failed before a structured response was available."""


class PlanningModelOutputError(PlanningModelError):
    """A model response could not satisfy the structured output contract."""


class PlanningFailureKind(StrEnum):
    """Sanitized planning failure categories safe to record in graph state."""

    MODEL_INVOCATION = "model_invocation"
    INVALID_OUTPUT = "invalid_output"


class ResearchPlanningError(RuntimeError):
    """Sanitized terminal planning error raised after the bounded policy is applied."""

    def __init__(self, kind: PlanningFailureKind, attempts: int) -> None:
        super().__init__("Research planning failed at the typed model boundary.")
        self.kind = kind
        self.attempts = attempts


class ResearchPlanningAgent:
    """Map Candidate interests into a validated SearchPlan through an injected model."""

    def __init__(self, model: PlanningModelPort) -> None:
        self._model = model

    def plan(
        self,
        candidate_profile: CandidateProfile,
        remembered_candidate_preferences: tuple[CandidatePreferenceRevision, ...],
        *,
        remembered_candidate_memories: tuple[CandidateMemoryRecord, ...] = (),
        target_regions: tuple[str, ...],
        exclusions: tuple[str, ...],
    ) -> SearchPlan:
        """Generate a SearchPlan, retrying malformed structured output exactly once."""
        planning_input = PlanningInput.from_candidate_profile(
            candidate_profile,
            remembered_candidate_preferences,
            remembered_candidate_memories=remembered_candidate_memories,
            target_regions=target_regions,
            exclusions=exclusions,
        )

        for attempt in range(1, MAX_PLANNING_OUTPUT_ATTEMPTS + 1):
            try:
                response = self._model.generate(planning_input)
                validated_response = StructuredSearchPlanResponse.model_validate(response)
                return self._to_search_plan(validated_response, target_regions)
            except PlanningModelInvocationError as error:
                raise ResearchPlanningError(
                    PlanningFailureKind.MODEL_INVOCATION, attempt
                ) from error
            except (PlanningModelOutputError, ValidationError, ValueError) as error:
                if attempt == MAX_PLANNING_OUTPUT_ATTEMPTS:
                    raise ResearchPlanningError(
                        PlanningFailureKind.INVALID_OUTPUT, attempt
                    ) from error
            except Exception as error:
                raise ResearchPlanningError(
                    PlanningFailureKind.MODEL_INVOCATION, attempt
                ) from error

        raise AssertionError("The bounded planning loop must return or raise")

    @staticmethod
    def _to_search_plan(
        response: StructuredSearchPlanResponse,
        target_regions: tuple[str, ...],
    ) -> SearchPlan:
        """Convert provider output through the stricter deterministic domain contract."""
        queries = tuple(
            PlannedSearchQuery(
                query=item.query,
                purpose=item.purpose,
                target_source_types=tuple(item.target_source_types),
            )
            for item in response.search_queries
        )
        return SearchPlan(
            search_queries=queries,
            expanded_research_concepts=tuple(response.expanded_research_concepts),
            target_regions=target_regions,
            rationale=response.rationale,
        )
