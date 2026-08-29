"""Typed, immutable data contracts for the ScholarPath domain."""

from __future__ import annotations

from collections.abc import Mapping
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


class SupervisorProfile(DomainModel):
    """Identity and discovery provenance shared across Supervisor records."""

    supervisor_id: NonEmptyString
    full_name: NonEmptyString
    institution: NonEmptyString
    department: NonEmptyString
    profile_url: HttpUrl
    discovery_source: NonEmptyString
    discovery_query: NonEmptyString


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


def missing_verification_evidence(
    evidence: tuple[EvidenceClaim, ...], supervisor_id: str
) -> tuple[str, ...]:
    """Return required evidence categories absent for one Supervisor."""
    direct_claim_types = {
        claim.claim_type
        for claim in evidence
        if claim.supervisor_id == supervisor_id and claim.directly_supported
    }
    missing: list[str] = []
    if EvidenceClaimType.IDENTITY not in direct_claim_types:
        missing.append(EvidenceClaimType.IDENTITY.value)
    if EvidenceClaimType.CURRENT_AFFILIATION not in direct_claim_types:
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

        missing = missing_verification_evidence(self.evidence, self.supervisor_id)
        if missing:
            raise ValueError(
                f"Missing directly supported verification evidence: {', '.join(missing)}"
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
