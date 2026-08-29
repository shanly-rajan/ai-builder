"""Typed ScholarPath agent contracts and provider adapters."""

from .evidence_verification import (
    EvidenceExtractionInput,
    EvidenceModelError,
    EvidenceModelInvocationError,
    EvidenceModelOutputError,
    EvidenceVerificationAgent,
    EvidenceVerificationModelPort,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
    deterministic_evidence_id,
)
from .openai_evidence import OpenAIEvidenceVerificationModelAdapter
from .openai_planning import OpenAIPlanningModelAdapter
from .prompts import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V1,
    RESEARCH_PLANNING_PROMPT_VERSION,
    RESEARCH_PLANNING_SYSTEM_PROMPT_V1,
)
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
    "EVIDENCE_VERIFICATION_PROMPT_VERSION",
    "EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V1",
    "EvidenceExtractionInput",
    "EvidenceModelError",
    "EvidenceModelInvocationError",
    "EvidenceModelOutputError",
    "EvidenceVerificationAgent",
    "EvidenceVerificationModelPort",
    "OpenAIPlanningModelAdapter",
    "OpenAIEvidenceVerificationModelAdapter",
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
    "StructuredEvidenceClaim",
    "StructuredEvidenceExtractionResult",
    "SupervisorDiscoveryAgent",
    "SupervisorDiscoveryResult",
    "canonical_profile_url",
    "deduplicate_prospective_supervisors",
    "deterministic_supervisor_id",
    "deterministic_evidence_id",
]
