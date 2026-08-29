"""Canonical enumerations used by ScholarPath domain contracts."""

from enum import StrEnum


class SupervisorLifecycleStatus(StrEnum):
    """A Supervisor's persisted position in the review lifecycle."""

    PROSPECTIVE = "prospective"
    VERIFIED = "verified"
    SHORTLISTED = "shortlisted"
    REJECTED = "rejected"


class EvidenceConfidence(StrEnum):
    """Confidence assigned to an individual evidence claim or assessment."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AvailabilityStatus(StrEnum):
    """Explicit, source-backed Supervisor availability states."""

    CONFIRMED_ACCEPTING = "confirmed_accepting"
    CONFIRMED_NOT_ACCEPTING = "confirmed_not_accepting"
    NOT_STATED = "not_stated"
    CONFLICTING_EVIDENCE = "conflicting_evidence"


class SourceKind(StrEnum):
    """Kinds of sources from which factual evidence can be retrieved."""

    UNIVERSITY_PROFILE = "university_profile"
    INSTITUTIONAL_DIRECTORY = "institutional_directory"
    DEPARTMENT_PAGE = "department_page"
    PUBLICATION = "publication"
    PROJECT_PAGE = "project_page"
    RESEARCH_REPOSITORY = "research_repository"
    PERSONAL_ACADEMIC_PAGE = "personal_academic_page"
    OTHER = "other"


class SearchSourceType(StrEnum):
    """Source categories a planned search query is intended to target."""

    OFFICIAL_UNIVERSITY_PROFILE = "official_university_profile"
    DEPARTMENT_OR_RESEARCH_GROUP = "department_or_research_group"
    RECENT_PUBLICATION = "recent_publication"
    DOCTORAL_SUPERVISION_INFORMATION = "doctoral_supervision_information"


class SearchResultRejectionCategory(StrEnum):
    """Privacy-safe reasons a raw search result was not retained."""

    PERSON_NOT_ESTABLISHED = "person_not_established"
    ACADEMIC_CONTEXT_NOT_ESTABLISHED = "academic_context_not_established"
    IDENTITY_CONFLICT = "identity_conflict"
    INSTITUTION_NOT_ESTABLISHED = "institution_not_established"
    INCOMPLETE_INSTITUTION = "incomplete_institution"


class CandidateReviewAction(StrEnum):
    """Actions available to the Candidate at the human review gate."""

    APPROVE = "approve"
    REJECT = "reject"
    REQUEST_MORE = "request_more"


class EvidenceClaimType(StrEnum):
    """Factual categories supported by an evidence source."""

    IDENTITY = "identity"
    CURRENT_AFFILIATION = "current_affiliation"
    RESEARCH_INTEREST = "research_interest"
    METHODOLOGY = "methodology"
    PUBLICATION = "publication"
    PROJECT = "project"
    AVAILABILITY = "availability"


class VerificationStatus(StrEnum):
    """Outcome of applying evidence sufficiency rules."""

    VERIFIED = "verified"
    VERIFIED_WITH_CONCERNS = "verified_with_concerns"
    PARTIALLY_VERIFIED = "partially_verified"


class IndependentReviewDecision(StrEnum):
    """A model-proposed disposition for one Research Fit assessment."""

    ACCEPT = "accept"
    REVISE = "revise"


class IndependentReviewStatus(StrEnum):
    """The deterministic outcome of reconciling an independent review."""

    ACCEPTED = "accepted"
    REVISED = "revised"
    UNAVAILABLE = "unavailable"


class IndependentReviewFailureKind(StrEnum):
    """Sanitized reasons why an independent review could not be applied."""

    MODEL_INVOCATION = "model_invocation"
    INVALID_OUTPUT = "invalid_output"
    INVALID_EVIDENCE_REFERENCE = "invalid_evidence_reference"
