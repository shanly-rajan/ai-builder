"""Typed, immutable data contracts for the ScholarPath domain."""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Annotated, Any, Literal, Self

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictBool,
    StringConstraints,
    model_validator,
)

from .enums import (
    AvailabilityStatus,
    CandidateReviewAction,
    EvidenceClaimType,
    EvidenceConfidence,
    SearchSourceType,
    SourceKind,
    SupervisorLifecycleStatus,
    VerificationStatus,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Score = Annotated[int, Field(strict=True, ge=0, le=100)]

_AVAILABILITY_AUDIENCE_PATTERN = (
    r"(?:(?:new\s+)?(?:doctoral|phd)\s+"
    r"(?:candidates?|students?|applicants?|applications?|enquiries?)|"
    r"applications?\s+from\s+(?:new\s+)?(?:doctoral|phd)\s+"
    r"(?:candidates?|students?|applicants?))"
)
_EXPLICIT_NOT_ACCEPTING_PATTERN = re.compile(
    rf"^(?:"
    rf"(?:(?:is|are)\s+)?(?:(?:currently|presently)\s+)?"
    rf"(?:not\s+(?:(?:currently|presently)\s+)?accepting|no\s+longer\s+accepting)|"
    rf"(?:is|are)n['’]t\s+accepting|will\s+not\s+be\s+accepting|"
    rf"does\s+not\s+accept|cannot\s+accept"
    rf")\s+{_AVAILABILITY_AUDIENCE_PATTERN}\b"
)
_EXPLICIT_ACCEPTING_PATTERN = re.compile(
    rf"^(?:(?:is|are)\s+)?(?:(?:currently|presently)\s+)?"
    rf"accepting\s+{_AVAILABILITY_AUDIENCE_PATTERN}\b"
)
_TITLED_PERSON_PATTERN = re.compile(
    r"\b(?:Dr|Prof|Professor)\.?\s+[A-Z][A-Za-z'’-]*"
    r"(?:\s+(?:al|bin|da|de|del|di|la|le|van|von))?\s+[A-Z][A-Za-z'’-]*\b"
)
_DIRECT_SUBJECT_RELATIONS: dict[EvidenceClaimType, frozenset[str]] = {
    EvidenceClaimType.CURRENT_AFFILIATION: frozenset({"are", "has", "holds", "is", "serves"}),
    EvidenceClaimType.RESEARCH_INTEREST: frozenset(
        {
            "examines",
            "focuses",
            "investigates",
            "researches",
            "specialises",
            "specializes",
            "studies",
            "works",
        }
    ),
    EvidenceClaimType.METHODOLOGY: frozenset({"applies", "employs", "has", "uses", "works"}),
    EvidenceClaimType.PUBLICATION: frozenset(
        {"authored", "coauthored", "has", "published", "wrote"}
    ),
    EvidenceClaimType.PROJECT: frozenset({"develops", "directs", "has", "heads", "leads"}),
    EvidenceClaimType.AVAILABILITY: frozenset(
        {"are", "aren't", "aren’t", "cannot", "does", "is", "isn't", "isn’t", "will"}
    ),
}


class DomainModel(BaseModel):
    """Base contract that rejects unknown data and prevents in-place mutation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
        revalidate_instances="always",
    )

    def model_copy(
        self,
        *,
        update: Mapping[str, Any] | None = None,
        deep: bool = False,
    ) -> Self:
        """Copy safely, revalidating every requested field update."""
        if update is None:
            return super().model_copy(deep=deep)
        data = self.model_dump(mode="python", round_trip=True)
        data.update(update)
        return self.__class__.model_validate(data)


class CandidateProfile(DomainModel):
    """Structured doctoral interests and constraints supplied by the Candidate."""

    candidate_id: NonEmptyString
    proposed_research_statement: NonEmptyString
    research_topics: tuple[NonEmptyString, ...] = Field(min_length=1)
    preferred_regions: tuple[NonEmptyString, ...] = ()
    preferred_study_modes: tuple[NonEmptyString, ...] = ()
    preferred_research_orientation: NonEmptyString | None = None
    methodological_interests: tuple[NonEmptyString, ...] = ()
    exclusions: tuple[NonEmptyString, ...] = ()


class PlannedSearchQuery(DomainModel):
    """One executable query plus its purpose and intended evidence sources."""

    query: NonEmptyString
    purpose: NonEmptyString
    target_source_types: tuple[SearchSourceType, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def target_source_types_must_be_unique(self) -> Self:
        """Prevent duplicated source categories within one planned query."""
        if len(self.target_source_types) != len(set(self.target_source_types)):
            raise ValueError("Target source types must be unique within a search query")
        return self


class SearchPlan(DomainModel):
    """Validated, executable search strategy prepared from Candidate interests."""

    search_queries: tuple[PlannedSearchQuery, ...] = Field(min_length=4, max_length=8)
    expanded_research_concepts: tuple[NonEmptyString, ...] = Field(min_length=1)
    target_regions: tuple[NonEmptyString, ...] = ()
    rationale: NonEmptyString

    @model_validator(mode="after")
    def queries_must_be_distinct_and_cover_required_sources(self) -> Self:
        """Enforce distinct queries and complete source-category coverage."""
        normalized_queries = [
            " ".join(search.query.casefold().split()) for search in self.search_queries
        ]
        if len(normalized_queries) != len(set(normalized_queries)):
            raise ValueError("Search queries must be distinct")

        covered_sources = {
            source_type
            for search in self.search_queries
            for source_type in search.target_source_types
        }
        missing_sources = set(SearchSourceType) - covered_sources
        if missing_sources:
            missing_values = ", ".join(sorted(item.value for item in missing_sources))
            raise ValueError(f"Search plan is missing target source types: {missing_values}")
        return self


class SearchResult(DomainModel):
    """One provider-neutral web result returned for an exact search query."""

    url: HttpUrl
    title: NonEmptyString
    description: str = ""
    publication_date: datetime | None = None
    originating_query: NonEmptyString


class SupervisorDiscoveryProvenance(DomainModel):
    """A paired source URL and query that led to one Supervisor discovery."""

    source_url: HttpUrl
    originating_query: NonEmptyString


class SupervisorProfile(DomainModel):
    """Identity and discovery provenance shared across Supervisor records."""

    supervisor_id: NonEmptyString
    full_name: NonEmptyString
    institution: NonEmptyString
    department: NonEmptyString
    profile_url: HttpUrl
    discovery_source: NonEmptyString
    discovery_query: NonEmptyString
    discovery_provenance: tuple[SupervisorDiscoveryProvenance, ...] = ()

    @model_validator(mode="after")
    def discovery_provenance_must_be_unique(self) -> Self:
        """Keep exact source/query pairs without duplicated provenance entries."""
        pairs = [
            (str(item.source_url), item.originating_query) for item in self.discovery_provenance
        ]
        if len(pairs) != len(set(pairs)):
            raise ValueError("Supervisor discovery provenance entries must be unique")
        return self


class ProspectiveSupervisor(SupervisorProfile):
    """A discovered Supervisor whose evidence is not yet fully verified."""

    status: Literal[SupervisorLifecycleStatus.PROSPECTIVE] = SupervisorLifecycleStatus.PROSPECTIVE


class EvidenceClaim(DomainModel):
    """One provenance-preserving factual claim about a Supervisor."""

    evidence_id: NonEmptyString
    supervisor_id: NonEmptyString
    claim_type: EvidenceClaimType
    claim: NonEmptyString
    source_url: HttpUrl
    source_kind: SourceKind
    retrieved_at: AwareDatetime
    confidence: EvidenceConfidence
    directly_supported: StrictBool
    availability_status: AvailabilityStatus | None = None
    asserted_name: NonEmptyString | None = None
    asserted_institution: NonEmptyString | None = None
    asserted_department: NonEmptyString | None = None
    supporting_excerpt: NonEmptyString | None = None
    conflicting_evidence_ids: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def availability_value_must_match_claim_type(self) -> Self:
        """Represent availability outcomes as typed facts rather than prose."""
        explicit_values = {
            AvailabilityStatus.CONFIRMED_ACCEPTING,
            AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
        }
        if self.claim_type is EvidenceClaimType.AVAILABILITY:
            if self.availability_status not in explicit_values:
                raise ValueError(
                    "Availability evidence must assert accepting or not-accepting status"
                )
        elif self.availability_status is not None:
            raise ValueError("Only availability evidence may assert an availability status")
        if len(self.conflicting_evidence_ids) != len(set(self.conflicting_evidence_ids)):
            raise ValueError("Conflicting evidence identifiers must be unique")
        if self.evidence_id in self.conflicting_evidence_ids:
            raise ValueError("An evidence claim cannot conflict with itself")
        return self


class CandidatePreferenceRevision(DomainModel):
    """Partial preference changes supplied during Candidate review."""

    research_topics: tuple[NonEmptyString, ...] | None = None
    preferred_regions: tuple[NonEmptyString, ...] | None = None
    preferred_study_modes: tuple[NonEmptyString, ...] | None = None
    preferred_research_orientation: NonEmptyString | None = None
    methodological_interests: tuple[NonEmptyString, ...] | None = None
    exclusions: tuple[NonEmptyString, ...] | None = None

    @model_validator(mode="after")
    def at_least_one_preference_must_change(self) -> Self:
        """Reject an empty object that does not express a revision."""
        if all(value is None for value in self.__dict__.values()):
            raise ValueError("At least one revised preference is required")
        return self


class CandidateReviewDecision(DomainModel):
    """An explicit Candidate decision for one or more Verified Supervisors."""

    action: CandidateReviewAction
    supervisor_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    reason: NonEmptyString
    revised_preferences: CandidatePreferenceRevision | None = None

    @model_validator(mode="after")
    def supervisor_ids_must_be_unique(self) -> Self:
        """Ensure each Supervisor is addressed exactly once by a decision."""
        if len(self.supervisor_ids) != len(set(self.supervisor_ids)):
            raise ValueError("Supervisor identifiers must be unique")
        return self


def _normalized_grounding_text(value: str) -> str:
    """Normalize case and whitespace without changing factual wording."""
    return " ".join(value.casefold().split())


def _contains_exact_normalized_phrase(text: str, phrase: str) -> bool:
    """Find one normalized phrase without accepting a longer word as an exact match."""
    normalized_text = _normalized_grounding_text(text)
    normalized_phrase = _normalized_grounding_text(phrase)
    if not normalized_phrase:
        return False
    return (
        re.search(
            rf"(?<!\w){re.escape(normalized_phrase)}(?!\w)",
            normalized_text,
        )
        is not None
    )


def _availability_polarity_matches_excerpt(claim: EvidenceClaim) -> bool:
    """Check explicit availability wording without asking a model to infer polarity."""
    assert claim.asserted_name is not None
    assert claim.supporting_excerpt is not None
    excerpt = _normalized_grounding_text(claim.supporting_excerpt)
    asserted_name = _normalized_grounding_text(claim.asserted_name)
    subject_statement = excerpt[len(asserted_name) :].lstrip(" ,:;-—")
    has_not_accepting = _EXPLICIT_NOT_ACCEPTING_PATTERN.search(subject_statement) is not None
    has_accepting = _EXPLICIT_ACCEPTING_PATTERN.search(subject_statement) is not None
    if claim.availability_status is AvailabilityStatus.CONFIRMED_ACCEPTING:
        return has_accepting and not has_not_accepting
    if claim.availability_status is AvailabilityStatus.CONFIRMED_NOT_ACCEPTING:
        return has_not_accepting and not has_accepting
    return False


def _excerpt_has_direct_supervisor_subject(claim: EvidenceClaim) -> bool:
    """Require a conservative subject-led statement and reject a second titled person."""
    assert claim.asserted_name is not None
    assert claim.supporting_excerpt is not None
    excerpt = _normalized_grounding_text(claim.supporting_excerpt)
    asserted_name = _normalized_grounding_text(claim.asserted_name)
    if not excerpt.startswith(asserted_name):
        return False

    titled_people = {
        re.sub(
            r"['’]s$",
            "",
            _normalized_grounding_text(match.group(0)).rstrip("."),
        )
        for match in _TITLED_PERSON_PATTERN.finditer(claim.supporting_excerpt)
    }
    if any(person != asserted_name.rstrip(".") for person in titled_people):
        return False

    remainder = excerpt[len(asserted_name) :].lstrip(" ,:;-—")
    if remainder.startswith(("'s", "’s")):
        return True
    first_word = remainder.split(maxsplit=1)[0] if remainder else ""
    return first_word in _DIRECT_SUBJECT_RELATIONS.get(claim.claim_type, frozenset())


def evidence_claim_is_grounded_for_supervisor(
    claim: EvidenceClaim,
    supervisor: SupervisorProfile,
) -> bool:
    """Return whether one direct claim is owned, subject-bound, and excerpt-grounded."""
    if not claim.directly_supported or claim.supervisor_id != supervisor.supervisor_id:
        return False
    if claim.asserted_name is None or claim.supporting_excerpt is None:
        return False
    if _normalized_grounding_text(claim.asserted_name) != _normalized_grounding_text(
        supervisor.full_name
    ):
        return False
    if not _contains_exact_normalized_phrase(claim.supporting_excerpt, claim.asserted_name):
        return False
    if claim.claim_type is not EvidenceClaimType.IDENTITY and not (
        _excerpt_has_direct_supervisor_subject(claim)
    ):
        return False

    if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION:
        if claim.asserted_institution is None or claim.asserted_department is None:
            return False
        if not _contains_exact_normalized_phrase(
            claim.supporting_excerpt,
            claim.asserted_institution,
        ):
            return False
        if not _contains_exact_normalized_phrase(
            claim.supporting_excerpt,
            claim.asserted_department,
        ):
            return False

    if claim.claim_type is EvidenceClaimType.AVAILABILITY:
        return _availability_polarity_matches_excerpt(claim)
    return True


def missing_verification_evidence(
    evidence: tuple[EvidenceClaim, ...], supervisor: SupervisorProfile
) -> tuple[str, ...]:
    """Return required evidence categories absent for one Supervisor."""
    grounded_direct_evidence = tuple(
        claim for claim in evidence if evidence_claim_is_grounded_for_supervisor(claim, supervisor)
    )
    has_identity = any(
        claim.claim_type is EvidenceClaimType.IDENTITY for claim in grounded_direct_evidence
    )
    has_affiliation = any(
        claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
        for claim in grounded_direct_evidence
    )
    direct_claim_types = {claim.claim_type for claim in grounded_direct_evidence}
    missing: list[str] = []
    if not has_identity:
        missing.append(EvidenceClaimType.IDENTITY.value)
    if not has_affiliation:
        missing.append(EvidenceClaimType.CURRENT_AFFILIATION.value)
    research_claim_types = {
        EvidenceClaimType.RESEARCH_INTEREST,
        EvidenceClaimType.PUBLICATION,
    }
    if direct_claim_types.isdisjoint(research_claim_types):
        missing.append("research_interest_or_publication")
    return tuple(missing)


def derive_availability_status(
    evidence: tuple[EvidenceClaim, ...], supervisor_id: str
) -> AvailabilityStatus:
    """Derive an availability state from directly supported typed claims."""
    values = {
        claim.availability_status
        for claim in evidence
        if claim.supervisor_id == supervisor_id
        and claim.claim_type is EvidenceClaimType.AVAILABILITY
        and claim.directly_supported
        and claim.availability_status is not None
    }
    if values == {
        AvailabilityStatus.CONFIRMED_ACCEPTING,
        AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
    }:
        return AvailabilityStatus.CONFLICTING_EVIDENCE
    if AvailabilityStatus.CONFIRMED_ACCEPTING in values:
        return AvailabilityStatus.CONFIRMED_ACCEPTING
    if AvailabilityStatus.CONFIRMED_NOT_ACCEPTING in values:
        return AvailabilityStatus.CONFIRMED_NOT_ACCEPTING
    return AvailabilityStatus.NOT_STATED


class VerifiedSupervisor(SupervisorProfile):
    """A Supervisor whose identity, affiliation, and research evidence is sufficient."""

    evidence: tuple[EvidenceClaim, ...] = Field(min_length=1)
    status: Literal[
        SupervisorLifecycleStatus.VERIFIED,
        SupervisorLifecycleStatus.SHORTLISTED,
        SupervisorLifecycleStatus.REJECTED,
    ] = SupervisorLifecycleStatus.VERIFIED
    verification_status: VerificationStatus = VerificationStatus.VERIFIED
    availability_status: AvailabilityStatus = AvailabilityStatus.NOT_STATED
    verification_concerns: tuple[NonEmptyString, ...] = ()
    candidate_review_decision: CandidateReviewDecision | None = None

    @model_validator(mode="after")
    def evidence_must_be_sufficient_and_consistent(self) -> Self:
        """Enforce evidence ownership, sufficiency, and availability provenance."""
        if self.verification_status is VerificationStatus.PARTIALLY_VERIFIED:
            raise ValueError("A Verified Supervisor cannot be partially verified")
        evidence_ids = [claim.evidence_id for claim in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Evidence identifiers must be unique")

        foreign_evidence_ids = [
            claim.evidence_id
            for claim in self.evidence
            if claim.supervisor_id != self.supervisor_id
        ]
        if foreign_evidence_ids:
            raise ValueError("Every evidence claim must reference this Supervisor")

        evidence_id_set = set(evidence_ids)
        for claim in self.evidence:
            unknown_conflicts = set(claim.conflicting_evidence_ids) - evidence_id_set
            if unknown_conflicts:
                raise ValueError("Conflicting evidence identifiers must exist in the record")

        missing = missing_verification_evidence(self.evidence, self)
        if missing:
            raise ValueError(
                f"Missing directly supported verification evidence: {', '.join(missing)}"
            )
        ungrounded_direct_claims = [
            f"{claim.claim_type.value}:{claim.evidence_id}"
            for claim in self.evidence
            if claim.directly_supported
            and not evidence_claim_is_grounded_for_supervisor(claim, self)
        ]
        if ungrounded_direct_claims:
            raise ValueError(
                "Directly supported evidence claims must be grounded for this Supervisor: "
                + ", ".join(ungrounded_direct_claims)
            )

        supported_availability_values = {
            claim.availability_status
            for claim in self.evidence
            if claim.claim_type is EvidenceClaimType.AVAILABILITY
            and claim.directly_supported
            and claim.availability_status is not None
        }
        expected_availability_values = {
            AvailabilityStatus.NOT_STATED: set(),
            AvailabilityStatus.CONFIRMED_ACCEPTING: {AvailabilityStatus.CONFIRMED_ACCEPTING},
            AvailabilityStatus.CONFIRMED_NOT_ACCEPTING: {
                AvailabilityStatus.CONFIRMED_NOT_ACCEPTING
            },
            AvailabilityStatus.CONFLICTING_EVIDENCE: {
                AvailabilityStatus.CONFIRMED_ACCEPTING,
                AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
            },
        }
        if supported_availability_values != expected_availability_values[self.availability_status]:
            raise ValueError(
                "Availability status must match the directly supported availability evidence"
            )
        if self.availability_status is AvailabilityStatus.CONFLICTING_EVIDENCE:
            availability_source_urls = {
                str(claim.source_url)
                for claim in self.evidence
                if claim.claim_type is EvidenceClaimType.AVAILABILITY and claim.directly_supported
            }
            if len(availability_source_urls) < 2:
                raise ValueError("Conflicting availability requires distinct evidence sources")

        has_concerns = bool(self.verification_concerns)
        if has_concerns != (self.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS):
            raise ValueError("Verification status and verification concerns must be consistent")

        decision = self.candidate_review_decision
        if self.status is SupervisorLifecycleStatus.VERIFIED:
            if decision is not None and (
                decision.action is not CandidateReviewAction.REQUEST_MORE
                or self.supervisor_id not in decision.supervisor_ids
            ):
                raise ValueError("A verified record may only retain a scoped request-more decision")
        else:
            required_action = (
                CandidateReviewAction.APPROVE
                if self.status is SupervisorLifecycleStatus.SHORTLISTED
                else CandidateReviewAction.REJECT
            )
            if (
                decision is None
                or decision.action is not required_action
                or self.supervisor_id not in decision.supervisor_ids
            ):
                raise ValueError(
                    f"The {self.status.value} status requires the matching Candidate decision"
                )
        return self


class SupervisorVerificationRecord(DomainModel):
    """Evidence outcome that preserves partial work without weakening lifecycle rules."""

    prospective_supervisor: ProspectiveSupervisor
    evidence: tuple[EvidenceClaim, ...] = ()
    verification_status: VerificationStatus
    availability_status: AvailabilityStatus = AvailabilityStatus.NOT_STATED
    verification_concerns: tuple[NonEmptyString, ...] = ()
    missing_required_evidence: tuple[NonEmptyString, ...] = ()
    verified_supervisor: VerifiedSupervisor | None = None

    @model_validator(mode="after")
    def outcome_must_match_its_evidence(self) -> Self:
        """Separate partial verification from the Verified Supervisor lifecycle state."""
        evidence_ids = [claim.evidence_id for claim in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("Verification-record evidence identifiers must be unique")
        if any(
            claim.supervisor_id != self.prospective_supervisor.supervisor_id
            for claim in self.evidence
        ):
            raise ValueError("Every verification-record claim must reference this Supervisor")

        evidence_id_set = set(evidence_ids)
        for claim in self.evidence:
            unknown_conflicts = set(claim.conflicting_evidence_ids) - evidence_id_set
            if unknown_conflicts:
                raise ValueError("Conflicting evidence identifiers must exist in the record")

        ungrounded_direct_claims = [
            f"{claim.claim_type.value}:{claim.evidence_id}"
            for claim in self.evidence
            if claim.directly_supported
            and not evidence_claim_is_grounded_for_supervisor(
                claim,
                self.prospective_supervisor,
            )
        ]
        if ungrounded_direct_claims:
            raise ValueError(
                "Directly supported verification-record claims must be grounded for this "
                "Supervisor: " + ", ".join(ungrounded_direct_claims)
            )

        expected_missing = missing_verification_evidence(
            self.evidence,
            self.prospective_supervisor,
        )

        expected_availability = derive_availability_status(
            self.evidence,
            self.prospective_supervisor.supervisor_id,
        )
        if self.availability_status is not expected_availability:
            raise ValueError("Verification availability must match direct evidence")

        if self.verification_status is VerificationStatus.PARTIALLY_VERIFIED:
            if self.verified_supervisor is not None:
                raise ValueError("Partial verification cannot contain a Verified Supervisor")
            if self.missing_required_evidence != expected_missing:
                raise ValueError(
                    "Partial verification must identify the exact missing required evidence"
                )
            return self

        if expected_missing or self.missing_required_evidence:
            raise ValueError("A completed verification cannot retain missing evidence")
        verified = self.verified_supervisor
        if verified is None:
            raise ValueError("Completed verification must contain a Verified Supervisor")
        if verified.supervisor_id != self.prospective_supervisor.supervisor_id:
            raise ValueError("Verification outcome and Verified Supervisor must match")
        if verified.evidence != self.evidence:
            raise ValueError("Verified Supervisor must retain the complete evidence collection")
        if verified.verification_status is not self.verification_status:
            raise ValueError("Verification statuses must match")
        if verified.availability_status is not self.availability_status:
            raise ValueError("Availability statuses must match")
        if verified.verification_concerns != self.verification_concerns:
            raise ValueError("Verification concerns must match")
        return self


class ResearchFitBreakdown(DomainModel):
    """Dimension scores used to explain an overall Research Fit Score."""

    topic_alignment: Score
    methodological_alignment: Score
    research_orientation_alignment: Score
    recent_research_alignment: Score
    practical_constraint_alignment: Score


class ResearchFitAssessment(DomainModel):
    """Evidence-linked Research Fit evaluation for one Verified Supervisor."""

    supervisor_id: NonEmptyString
    overall_score: Score
    breakdown: ResearchFitBreakdown
    rationale: NonEmptyString
    supporting_evidence_ids: tuple[NonEmptyString, ...] = Field(min_length=1)
    confidence: EvidenceConfidence
    concerns: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def supporting_evidence_ids_must_be_unique(self) -> Self:
        """Prevent the same evidence reference from appearing more than once."""
        if len(self.supporting_evidence_ids) != len(set(self.supporting_evidence_ids)):
            raise ValueError("Supporting evidence identifiers must be unique")
        return self


class ResearchFitEvidenceError(ValueError):
    """Raised when an assessment cites evidence outside its Supervisor record."""


def validate_research_fit_evidence(
    supervisor: VerifiedSupervisor,
    assessment: ResearchFitAssessment,
) -> None:
    """Validate assessment ownership and evidence references across two contracts."""
    if assessment.supervisor_id != supervisor.supervisor_id:
        raise ResearchFitEvidenceError(
            "Research Fit assessment and Verified Supervisor identifiers must match."
        )
    evidence_ids = {claim.evidence_id for claim in supervisor.evidence}
    unknown_ids = [
        evidence_id
        for evidence_id in assessment.supporting_evidence_ids
        if evidence_id not in evidence_ids
    ]
    if unknown_ids:
        raise ResearchFitEvidenceError(
            "Research Fit assessment references evidence outside the Verified Supervisor."
        )


class SupervisorShortlist(DomainModel):
    """Candidate-approved Supervisor records and a briefing."""

    candidate_id: NonEmptyString
    shortlisted_supervisors: tuple[VerifiedSupervisor, ...] = Field(min_length=1)
    generated_at: AwareDatetime
    briefing: NonEmptyString

    @model_validator(mode="after")
    def supervisors_must_be_uniquely_shortlisted(self) -> Self:
        """Accept only unique records already moved through the approval gate."""
        supervisor_ids = [supervisor.supervisor_id for supervisor in self.shortlisted_supervisors]
        if len(supervisor_ids) != len(set(supervisor_ids)):
            raise ValueError("Shortlisted Supervisor identifiers must be unique")
        if any(
            supervisor.status is not SupervisorLifecycleStatus.SHORTLISTED
            for supervisor in self.shortlisted_supervisors
        ):
            raise ValueError("Every Supervisor in a shortlist must have shortlisted status")
        return self
