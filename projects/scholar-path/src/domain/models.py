"""Typed, immutable data contracts for the ScholarPath domain."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
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
    IndependentReviewDecision,
    IndependentReviewFailureKind,
    IndependentReviewStatus,
    SearchSourceType,
    SourceKind,
    SupervisorLifecycleStatus,
    VerificationStatus,
)

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
Score = Annotated[int, Field(strict=True, ge=0, le=100)]
ActivityYear = Annotated[int, Field(strict=True, ge=1900, le=2100)]

_ADMISSION_LIKELIHOOD_PATTERN = re.compile(
    r"\b(?:admission|admitted|admittance)\b|"
    r"\bacceptance\s+(?:chance|likelihood|odds|probability)\b|"
    r"\bacceptance\s+(?:is|appears|seems)\s+(?:very\s+)?(?:likely|unlikely)\b|"
    r"\b(?:chance|likelihood|odds|probability|percentage)\s+of\s+"
    r"(?:acceptance|being\s+(?:accepted|admitted))\b|"
    r"\b(?:likely|unlikely)\s+to\s+be\s+(?:accepted|admitted)\b|"
    r"\b\d+(?:\.\d+)?\s*%[^.\n]{0,40}\b(?:accepted|admitted)\b",
    re.IGNORECASE,
)
_AVAILABILITY_SCORING_PATTERN = re.compile(
    r"\b(?:availability|accepting|not\s+accepting)\b|"
    r"\bconfirmed[_\s-](?:not[_\s-])?accepting\b|"
    r"\b(?:open|available)\s+(?:to|for)\s+[^.\n]{0,40}"
    r"\b(?:supervis|doctoral|phd)\w*\b|"
    r"\b(?:welcome|welcomes|welcoming|seek|seeks|seeking|recruit|recruits|recruiting|"
    r"take|takes|taking)\b[^.\n]{0,50}\b(?:doctoral|phd)\b|"
    r"\b(?:doctoral|phd)\s+(?:applications?|enquiries?|openings?|slots?)\b"
    r"[^.\n]{0,24}\b(?:open|welcome|closed|paused|being\s+accepted)\b|"
    r"\b(?:capacity|slots?)\s+(?:to|for)\s+[^.\n]{0,30}\bsupervis\w*\b",
    re.IGNORECASE,
)


def validate_research_fit_scoring_prose(values: Iterable[str]) -> None:
    """Reject admission and availability language from score-bearing fit prose."""
    combined = "\n".join(values)
    if _ADMISSION_LIKELIHOOD_PATTERN.search(combined):
        raise ValueError("Research Fit output must not contain an admission likelihood")
    if _AVAILABILITY_SCORING_PATTERN.search(combined):
        raise ValueError("Supervisor availability must remain separate from Research Fit scoring")


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
    activity_year: ActivityYear | None = None
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
        if self.activity_year is not None:
            if self.claim_type not in {
                EvidenceClaimType.PUBLICATION,
                EvidenceClaimType.PROJECT,
            }:
                raise ValueError("Only publication or project evidence may set an activity year")
            if self.activity_year > self.retrieved_at.year:
                raise ValueError("Research activity year cannot be later than retrieval year")
            if (
                self.supporting_excerpt is None
                or re.search(rf"(?<!\d){self.activity_year}(?!\d)", self.supporting_excerpt) is None
            ):
                raise ValueError(
                    "Research activity year must be explicit in the supporting excerpt"
                )
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
    constraints: tuple[NonEmptyString, ...] | None = None
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


class ResearchFitRubric(DomainModel):
    """Configurable Research Fit weights whose total is always 100 points."""

    version: NonEmptyString = "research-fit-rubric-v1"
    topic_alignment: Score = 40
    methodological_alignment: Score = 20
    research_orientation_alignment: Score = 15
    recent_research_alignment: Score = 15
    practical_constraint_alignment: Score = 10
    recent_activity_window_years: Annotated[int, Field(strict=True, ge=1, le=20)] = 5

    @model_validator(mode="after")
    def weights_must_total_one_hundred(self) -> Self:
        """Keep scoring arithmetic explicit and comparable across assessments."""
        if sum(self.weights.values()) != 100:
            raise ValueError("Research Fit rubric weights must sum to exactly 100")
        return self

    @property
    def weights(self) -> dict[str, int]:
        """Return dimension weights keyed exactly like ResearchFitBreakdown."""
        return {
            "topic_alignment": self.topic_alignment,
            "methodological_alignment": self.methodological_alignment,
            "research_orientation_alignment": self.research_orientation_alignment,
            "recent_research_alignment": self.recent_research_alignment,
            "practical_constraint_alignment": self.practical_constraint_alignment,
        }


class ResearchFitComponentAssessment(DomainModel):
    """One bounded Research Fit component with its precise evidence citations."""

    score: Score
    rationale: NonEmptyString
    supporting_evidence_ids: tuple[NonEmptyString, ...] = ()
    confidence: EvidenceConfidence
    evidence_gap: NonEmptyString | None = None

    @model_validator(mode="after")
    def score_must_be_supported_or_explicitly_missing(self) -> Self:
        """Disallow unsupported points and make every absent-evidence outcome explicit."""
        scoring_prose = [self.rationale]
        if self.evidence_gap is not None:
            scoring_prose.append(self.evidence_gap)
        validate_research_fit_scoring_prose(scoring_prose)
        if len(self.supporting_evidence_ids) != len(set(self.supporting_evidence_ids)):
            raise ValueError("Component evidence identifiers must be unique")
        if self.score > 0 and not self.supporting_evidence_ids:
            raise ValueError("A positive component score requires supporting evidence")
        if not self.supporting_evidence_ids:
            if self.score != 0:
                raise ValueError("A component without evidence must receive zero points")
            if self.confidence is not EvidenceConfidence.LOW:
                raise ValueError("A component without evidence must have low confidence")
            if self.evidence_gap is None:
                raise ValueError("A component without evidence must describe the evidence gap")
        return self


class ResearchFitBreakdown(DomainModel):
    """Evidence-cited components used to explain an overall Research Fit Score."""

    topic_alignment: ResearchFitComponentAssessment
    methodological_alignment: ResearchFitComponentAssessment
    research_orientation_alignment: ResearchFitComponentAssessment
    recent_research_alignment: ResearchFitComponentAssessment
    practical_constraint_alignment: ResearchFitComponentAssessment


_EVIDENCE_CONFIDENCE_RANK = {
    EvidenceConfidence.LOW: 1,
    EvidenceConfidence.MEDIUM: 2,
    EvidenceConfidence.HIGH: 3,
}


def derive_research_fit_confidence(
    breakdown: ResearchFitBreakdown,
    rubric: ResearchFitRubric,
) -> EvidenceConfidence:
    """Derive aggregate confidence deterministically from weighted components."""
    components = {
        "topic_alignment": breakdown.topic_alignment,
        "methodological_alignment": breakdown.methodological_alignment,
        "research_orientation_alignment": breakdown.research_orientation_alignment,
        "recent_research_alignment": breakdown.recent_research_alignment,
        "practical_constraint_alignment": breakdown.practical_constraint_alignment,
    }
    weighted_rank_total = sum(
        rubric.weights[dimension] * _EVIDENCE_CONFIDENCE_RANK[component.confidence]
        for dimension, component in components.items()
    )
    if weighted_rank_total >= 250:
        return EvidenceConfidence.HIGH
    if weighted_rank_total >= 150:
        return EvidenceConfidence.MEDIUM
    return EvidenceConfidence.LOW


class ResearchFitAssessment(DomainModel):
    """Evidence-linked Research Fit evaluation for one Verified Supervisor."""

    supervisor_id: NonEmptyString
    rubric: ResearchFitRubric = Field(default_factory=ResearchFitRubric)
    overall_score: Score
    breakdown: ResearchFitBreakdown
    rationale: NonEmptyString
    supporting_evidence_ids: tuple[NonEmptyString, ...] = ()
    confidence: EvidenceConfidence
    concerns: tuple[NonEmptyString, ...] = ()

    @model_validator(mode="after")
    def score_and_evidence_must_match_components(self) -> Self:
        """Validate deterministic arithmetic, rubric bounds, and citation aggregation."""
        validate_research_fit_scoring_prose((self.rationale, *self.concerns))
        if len(self.supporting_evidence_ids) != len(set(self.supporting_evidence_ids)):
            raise ValueError("Supporting evidence identifiers must be unique")

        components = {
            "topic_alignment": self.breakdown.topic_alignment,
            "methodological_alignment": self.breakdown.methodological_alignment,
            "research_orientation_alignment": self.breakdown.research_orientation_alignment,
            "recent_research_alignment": self.breakdown.recent_research_alignment,
            "practical_constraint_alignment": self.breakdown.practical_constraint_alignment,
        }
        for dimension, component in components.items():
            if component.score > self.rubric.weights[dimension]:
                raise ValueError(
                    f"{dimension} score exceeds its configured Research Fit rubric weight"
                )

        deterministic_total = sum(component.score for component in components.values())
        if self.overall_score != deterministic_total:
            raise ValueError(
                "Overall Research Fit Score must equal the deterministic component sum"
            )

        component_evidence_ids = {
            evidence_id
            for component in components.values()
            for evidence_id in component.supporting_evidence_ids
        }
        if set(self.supporting_evidence_ids) != component_evidence_ids:
            raise ValueError(
                "Assessment evidence identifiers must exactly match component citations"
            )
        expected_confidence = derive_research_fit_confidence(self.breakdown, self.rubric)
        if self.confidence is not expected_confidence:
            raise ValueError(
                "Assessment confidence must equal the deterministic component aggregate"
            )
        return self


def lower_evidence_confidence(confidence: EvidenceConfidence) -> EvidenceConfidence:
    """Lower confidence by one deterministic level, with LOW as the floor."""
    if confidence is EvidenceConfidence.HIGH:
        return EvidenceConfidence.MEDIUM
    return EvidenceConfidence.LOW


class ReconciledResearchFitAssessment(DomainModel):
    """Auditable independent-review overlay that preserves the M7 assessment."""

    supervisor_id: NonEmptyString
    initial_assessment: ResearchFitAssessment
    effective_score: Score
    effective_rationale: NonEmptyString
    effective_supporting_evidence_ids: tuple[NonEmptyString, ...] = ()
    effective_confidence: EvidenceConfidence
    review_status: IndependentReviewStatus
    decision: IndependentReviewDecision | None = None
    reviewer_confidence: EvidenceConfidence | None = None
    critique: NonEmptyString
    unsupported_claim_ids: tuple[NonEmptyString, ...] = ()
    overlooked_evidence_ids: tuple[NonEmptyString, ...] = ()
    requires_candidate_attention: StrictBool = False
    failure_kind: IndependentReviewFailureKind | None = None

    @model_validator(mode="after")
    def effective_view_must_match_reconciliation_status(self) -> Self:
        """Keep accepted, revised, and unavailable outcomes internally consistent."""
        validate_research_fit_scoring_prose((self.effective_rationale, self.critique))
        if self.supervisor_id != self.initial_assessment.supervisor_id:
            raise ValueError("Reconciled review and initial assessment identifiers must match")
        for name, values in (
            ("effective evidence", self.effective_supporting_evidence_ids),
            ("unsupported claims", self.unsupported_claim_ids),
            ("overlooked evidence", self.overlooked_evidence_ids),
        ):
            if len(values) != len(set(values)):
                raise ValueError(f"{name.capitalize()} identifiers must be unique")
        if set(self.unsupported_claim_ids) & set(self.overlooked_evidence_ids):
            raise ValueError("The same evidence cannot be unsupported and overlooked")

        initial_ids = self.initial_assessment.supporting_evidence_ids
        initial_id_set = set(initial_ids)
        if self.review_status is IndependentReviewStatus.ACCEPTED:
            if self.decision is not IndependentReviewDecision.ACCEPT:
                raise ValueError("An accepted review requires an accept decision")
            if self.reviewer_confidence is None or self.failure_kind is not None:
                raise ValueError("An accepted review requires reviewer confidence and no failure")
            if self.unsupported_claim_ids or self.overlooked_evidence_ids:
                raise ValueError("An accepted review cannot alter evidence references")
            if self.requires_candidate_attention:
                raise ValueError("An accepted review cannot require Candidate attention")
            if (
                self.effective_score != self.initial_assessment.overall_score
                or self.effective_rationale != self.initial_assessment.rationale
                or self.effective_supporting_evidence_ids != initial_ids
                or self.effective_confidence is not self.initial_assessment.confidence
            ):
                raise ValueError("An accepted review must preserve the initial assessment")
            return self

        if self.review_status is IndependentReviewStatus.REVISED:
            if self.decision is not IndependentReviewDecision.REVISE:
                raise ValueError("A revised review requires a revise decision")
            if self.reviewer_confidence is None or self.failure_kind is not None:
                raise ValueError("A revised review requires reviewer confidence and no failure")
            if not set(self.unsupported_claim_ids).issubset(initial_id_set):
                raise ValueError("Unsupported claims must come from the initial assessment")
            if set(self.overlooked_evidence_ids) & initial_id_set:
                raise ValueError(
                    "Overlooked evidence cannot already support the initial assessment"
                )
            expected_effective_ids = initial_id_set - set(self.unsupported_claim_ids)
            expected_effective_ids.update(self.overlooked_evidence_ids)
            if set(self.effective_supporting_evidence_ids) != expected_effective_ids:
                raise ValueError(
                    "Revised evidence must remove unsupported claims and add overlooked evidence"
                )
            if self.effective_rationale != self.critique:
                raise ValueError(
                    "A revised review must use the reviewer critique as its explanation"
                )
            if (
                _EVIDENCE_CONFIDENCE_RANK[self.effective_confidence]
                > _EVIDENCE_CONFIDENCE_RANK[self.initial_assessment.confidence]
                or _EVIDENCE_CONFIDENCE_RANK[self.effective_confidence]
                > _EVIDENCE_CONFIDENCE_RANK[self.reviewer_confidence]
            ):
                raise ValueError("A review cannot increase effective evidence confidence")
            return self

        if self.review_status is not IndependentReviewStatus.UNAVAILABLE:
            raise ValueError("Unknown independent review status")
        if self.decision is not None or self.reviewer_confidence is not None:
            raise ValueError("An unavailable review cannot retain a model decision")
        if self.failure_kind is None:
            raise ValueError("An unavailable review must identify a failure category")
        if self.unsupported_claim_ids or self.overlooked_evidence_ids:
            raise ValueError("An unavailable review cannot alter evidence references")
        if not self.requires_candidate_attention:
            raise ValueError("An unavailable review must require Candidate attention")
        if (
            self.effective_score != self.initial_assessment.overall_score
            or self.effective_rationale != self.initial_assessment.rationale
            or self.effective_supporting_evidence_ids != initial_ids
            or self.effective_confidence
            is not lower_evidence_confidence(self.initial_assessment.confidence)
        ):
            raise ValueError(
                "An unavailable review must preserve the assessment and lower confidence"
            )
        return self


class ResearchFitEvidenceError(ValueError):
    """Raised when an assessment cites evidence outside its Supervisor record."""


def validate_research_fit_evidence(
    supervisor: VerifiedSupervisor,
    assessment: ResearchFitAssessment,
) -> None:
    """Validate that every component cites suitable, direct, grounded evidence."""
    if assessment.supervisor_id != supervisor.supervisor_id:
        raise ResearchFitEvidenceError(
            "Research Fit assessment and Verified Supervisor identifiers must match."
        )

    evidence_by_id = {claim.evidence_id: claim for claim in supervisor.evidence}
    component_rules: tuple[
        tuple[str, ResearchFitComponentAssessment, frozenset[EvidenceClaimType]], ...
    ] = (
        (
            "topic_alignment",
            assessment.breakdown.topic_alignment,
            frozenset(
                {
                    EvidenceClaimType.RESEARCH_INTEREST,
                    EvidenceClaimType.PUBLICATION,
                    EvidenceClaimType.PROJECT,
                }
            ),
        ),
        (
            "methodological_alignment",
            assessment.breakdown.methodological_alignment,
            frozenset(
                {
                    EvidenceClaimType.METHODOLOGY,
                    EvidenceClaimType.RESEARCH_INTEREST,
                    EvidenceClaimType.PUBLICATION,
                    EvidenceClaimType.PROJECT,
                }
            ),
        ),
        (
            "research_orientation_alignment",
            assessment.breakdown.research_orientation_alignment,
            frozenset(
                {
                    EvidenceClaimType.RESEARCH_INTEREST,
                    EvidenceClaimType.METHODOLOGY,
                    EvidenceClaimType.PUBLICATION,
                    EvidenceClaimType.PROJECT,
                }
            ),
        ),
        (
            "recent_research_alignment",
            assessment.breakdown.recent_research_alignment,
            frozenset({EvidenceClaimType.PUBLICATION, EvidenceClaimType.PROJECT}),
        ),
        (
            "practical_constraint_alignment",
            assessment.breakdown.practical_constraint_alignment,
            frozenset({EvidenceClaimType.CURRENT_AFFILIATION}),
        ),
    )

    for dimension, component, suitable_claim_types in component_rules:
        if dimension == "practical_constraint_alignment" and component.score > 0:
            raise ResearchFitEvidenceError(
                "Practical-constraint points require typed region or study-mode evidence."
            )
        cited_claims: list[EvidenceClaim] = []
        for evidence_id in component.supporting_evidence_ids:
            claim = evidence_by_id.get(evidence_id)
            if claim is None or claim.supervisor_id != supervisor.supervisor_id:
                raise ResearchFitEvidenceError(
                    f"{dimension} references evidence outside the Verified Supervisor."
                )
            if claim.claim_type is EvidenceClaimType.AVAILABILITY:
                raise ResearchFitEvidenceError(
                    "Supervisor availability evidence must not contribute to a Research Fit Score."
                )
            if claim.claim_type not in suitable_claim_types:
                raise ResearchFitEvidenceError(
                    f"{dimension} cites an unsuitable evidence claim type: "
                    f"{claim.claim_type.value}."
                )
            if not claim.directly_supported or not evidence_claim_is_grounded_for_supervisor(
                claim,
                supervisor,
            ):
                raise ResearchFitEvidenceError(
                    f"{dimension} must cite directly supported, grounded evidence."
                )
            cited_claims.append(claim)

        if cited_claims:
            weakest_claim_rank = min(
                _EVIDENCE_CONFIDENCE_RANK[claim.confidence] for claim in cited_claims
            )
            if _EVIDENCE_CONFIDENCE_RANK[component.confidence] > weakest_claim_rank:
                raise ResearchFitEvidenceError(
                    f"{dimension} confidence exceeds its weakest cited evidence claim."
                )

        if dimension == "recent_research_alignment" and component.score > 0:
            for claim in cited_claims:
                if claim.activity_year is None:
                    raise ResearchFitEvidenceError(
                        "Recent-research points require an explicit typed activity year."
                    )
                if (
                    claim.retrieved_at.year - claim.activity_year
                    > assessment.rubric.recent_activity_window_years
                ):
                    raise ResearchFitEvidenceError(
                        "Recent-research points cite activity outside the freshness window."
                    )


class ProposedSupervisorRecommendation(DomainModel):
    """One evidence-backed ranking proposal awaiting explicit Candidate approval."""

    rank: Annotated[int, Field(strict=True, ge=1)]
    supervisor: VerifiedSupervisor
    assessment: ResearchFitAssessment
    strengths: tuple[NonEmptyString, ...] = Field(min_length=1)
    concerns: tuple[NonEmptyString, ...] = ()
    availability_status: AvailabilityStatus
    evidence_confidence: EvidenceConfidence
    independent_review: ReconciledResearchFitAssessment | None = None

    @model_validator(mode="after")
    def recommendation_must_remain_verified_and_evidence_backed(self) -> Self:
        """Keep a proposal outside the shortlisted lifecycle state until approval."""
        if self.supervisor.status is not SupervisorLifecycleStatus.VERIFIED:
            raise ValueError("A proposed recommendation must contain a Verified Supervisor")
        if self.assessment.supervisor_id != self.supervisor.supervisor_id:
            raise ValueError("Proposed recommendation Supervisor identifiers must match")
        if self.availability_status is not self.supervisor.availability_status:
            raise ValueError("Proposed availability must mirror verified evidence status")
        if self.independent_review is None:
            if self.evidence_confidence is not self.assessment.confidence:
                raise ValueError("Proposed evidence confidence must mirror the assessment")
        else:
            if self.independent_review.supervisor_id != self.supervisor.supervisor_id:
                raise ValueError("Independent review and proposed Supervisor must match")
            if self.independent_review.initial_assessment != self.assessment:
                raise ValueError("The proposal must retain the independently reviewed assessment")
            if self.evidence_confidence is not self.independent_review.effective_confidence:
                raise ValueError("Proposed confidence must mirror the independent review")
        try:
            validate_research_fit_evidence(self.supervisor, self.assessment)
        except ResearchFitEvidenceError as error:
            raise ValueError(str(error)) from error
        return self

    @property
    def effective_score(self) -> int:
        """Return the independently reconciled score when review is available."""
        if self.independent_review is not None:
            return self.independent_review.effective_score
        return self.assessment.overall_score

    @property
    def effective_rationale(self) -> str:
        """Return the independently reconciled explanation when review is available."""
        if self.independent_review is not None:
            return self.independent_review.effective_rationale
        return self.assessment.rationale


class ProposedSupervisorShortlist(DomainModel):
    """A ranked recommendation set that has not crossed the Candidate approval gate."""

    candidate_id: NonEmptyString
    recommendations: tuple[ProposedSupervisorRecommendation, ...] = Field(
        min_length=1,
        max_length=5,
    )
    generated_at: AwareDatetime
    summary: NonEmptyString

    @model_validator(mode="after")
    def recommendations_must_be_unique_and_contiguously_ranked(self) -> Self:
        """Ensure one stable proposal position per Verified Supervisor."""
        supervisor_ids = [item.supervisor.supervisor_id for item in self.recommendations]
        if len(supervisor_ids) != len(set(supervisor_ids)):
            raise ValueError("Proposed Supervisor identifiers must be unique")
        expected_ranks = list(range(1, len(self.recommendations) + 1))
        actual_ranks = [item.rank for item in self.recommendations]
        if actual_ranks != expected_ranks:
            raise ValueError("Proposed recommendation ranks must be contiguous and ordered")
        return self


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
