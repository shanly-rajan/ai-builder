"""Canonical enumerations used by ScholarPath domain contracts."""

from __future__ import annotations

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
    RESEARCH_DEGREE_SUPERVISION_INFORMATION = "research_degree_supervision_information"

    @classmethod
    def _missing_(cls, value: object) -> SearchSourceType | None:
        """Load the legacy serialized supervision category as its neutral replacement."""
        if value == "doctoral_supervision_information":
            return cls.RESEARCH_DEGREE_SUPERVISION_INFORMATION
        return None


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


class GroundingFailureReason(StrEnum):
    """Fixed, privacy-safe reasons an evidence claim did not pass grounding."""

    NOT_DIRECTLY_SUPPORTED = "not_directly_supported"
    SUPERVISOR_ID_MISMATCH = "supervisor_id_mismatch"
    ASSERTED_NAME_MISSING = "asserted_name_missing"
    SUPPORTING_EXCERPT_MISSING = "supporting_excerpt_missing"
    SUPERVISOR_NAME_MISMATCH = "supervisor_name_mismatch"
    IDENTITY_NAME_NOT_IN_EXCERPT = "identity_name_not_in_excerpt"
    # Retained for historical diagnostics; new context failures use precise codes.
    PROFILE_IDENTITY_CONTEXT_INVALID = "profile_identity_context_invalid"
    CONTEXT_IDENTITY_REFERENCE_MISSING = "context_identity_reference_missing"
    CONTEXT_IDENTITY_NOT_FOUND = "context_identity_not_found"
    CONTEXT_IDENTITY_TYPE_MISMATCH = "context_identity_type_mismatch"
    CONTEXT_IDENTITY_NOT_DIRECTLY_SUPPORTED = "context_identity_not_directly_supported"
    CONTEXT_SUPERVISOR_ID_MISMATCH = "context_supervisor_id_mismatch"
    CONTEXT_SOURCE_KIND_MISMATCH = "context_source_kind_mismatch"
    CONTEXT_SOURCE_URL_MISMATCH = "context_source_url_mismatch"
    CONTEXT_RETRIEVAL_TIME_MISMATCH = "context_retrieval_time_mismatch"
    CONTEXT_IDENTITY_REFERENCE_CHAINED = "context_identity_reference_chained"
    CONTEXT_IDENTITY_NAME_MISSING = "context_identity_name_missing"
    CONTEXT_IDENTITY_EXCERPT_MISSING = "context_identity_excerpt_missing"
    CONTEXT_CLAIM_NAME_MISSING = "context_claim_name_missing"
    CONTEXT_IDENTITY_NAME_NOT_IN_EXCERPT = "context_identity_name_not_in_excerpt"
    CONTEXT_IDENTITY_NAME_MISMATCH = "context_identity_name_mismatch"
    CONTEXT_IDENTITY_NOT_GROUNDED = "context_identity_not_grounded"
    CONTEXT_CONFLICTING_PERSON = "context_conflicting_person"
    CONTEXT_SUBJECT_PATTERN_MISSING = "context_subject_pattern_missing"
    SUBJECT_NOT_ESTABLISHED = "subject_not_established"
    AFFILIATION_FIELDS_MISSING = "affiliation_fields_missing"
    INSTITUTION_NOT_IN_EXCERPT = "institution_not_in_excerpt"
    DEPARTMENT_NOT_IN_EXCERPT = "department_not_in_excerpt"
    AVAILABILITY_POLARITY_NOT_SUPPORTED = "availability_polarity_not_supported"
    MODEL_NOT_DIRECTLY_SUPPORTED = "model_not_directly_supported"
    GROUNDED_IDENTITY_MISSING = "grounded_identity_missing"
    PROFILE_SOURCE_INELIGIBLE = "profile_source_ineligible"
    PROFILE_ROUTE_INELIGIBLE = "profile_route_ineligible"
    PROFILE_SUBJECT_MISMATCH = "profile_subject_mismatch"


class VerificationStatus(StrEnum):
    """Outcome of applying evidence sufficiency rules."""

    VERIFIED = "verified"
    VERIFIED_WITH_CONCERNS = "verified_with_concerns"
    PARTIALLY_VERIFIED = "partially_verified"


class VerificationEvidenceStandard(StrEnum):
    """Closed evidence standards that may authorize lifecycle verification."""

    STRICT = "strict"
    IDENTITY_ONLY_MVP = "identity_only_mvp"


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
