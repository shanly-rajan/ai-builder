"""Typed ScholarPath agent contracts and provider adapters."""

from .openai_planning import OpenAIPlanningModelAdapter
from .prompts import RESEARCH_PLANNING_PROMPT_VERSION, RESEARCH_PLANNING_SYSTEM_PROMPT_V1
from .research_planning import (
    MAX_PLANNING_OUTPUT_ATTEMPTS,
    PlanningFailureKind,
    PlanningInput,
    PlanningModelError,
    PlanningModelInvocationError,
    PlanningModelOutputError,
    PlanningModelPort,
    PlanningSearchQueryResponse,
    ResearchPlanningAgent,
    ResearchPlanningError,
    StructuredSearchPlanResponse,
)
from .supervisor_discovery import (
    SupervisorDiscoveryAgent,
    SupervisorDiscoveryResult,
    canonical_profile_url,
    deduplicate_prospective_supervisors,
    deterministic_supervisor_id,
)

__all__ = [
    "MAX_PLANNING_OUTPUT_ATTEMPTS",
    "OpenAIPlanningModelAdapter",
    "PlanningFailureKind",
    "PlanningInput",
    "PlanningModelError",
    "PlanningModelInvocationError",
    "PlanningModelOutputError",
    "PlanningModelPort",
    "PlanningSearchQueryResponse",
    "RESEARCH_PLANNING_PROMPT_VERSION",
    "RESEARCH_PLANNING_SYSTEM_PROMPT_V1",
    "ResearchPlanningAgent",
    "ResearchPlanningError",
    "StructuredSearchPlanResponse",
    "SupervisorDiscoveryAgent",
    "SupervisorDiscoveryResult",
    "canonical_profile_url",
    "deduplicate_prospective_supervisors",
    "deterministic_supervisor_id",
]
