"""Typed model boundary and deterministic Supervisor evidence verification."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Annotated, Protocol, Self

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    StrictInt,
    StringConstraints,
    ValidationError,
    model_validator,
)

from ..domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    ProspectiveSupervisor,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationStatus,
    derive_availability_status,
    evidence_claim_is_grounded_for_supervisor,
    missing_verification_evidence,
    supervisor_names_are_title_equivalent,
    verify_supervisor,
)
from ..tools.content_extraction import ExtractedContent

NonEmptyResponseText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
SupportingExcerpt = Annotated[
    str,
    StringConstraints(strip_whitespace=True, min_length=1, max_length=500),
]


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


class EvidenceExtractionInput(BaseModel):
    """One extracted page plus comparison hints supplied to the evidence model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    expected_name: NonEmptyResponseText
    expected_institution: NonEmptyResponseText
    expected_department: NonEmptyResponseText
    source_url: HttpUrl
    source_kind: SourceKind
    page_content: NonEmptyResponseText


class StructuredEvidenceClaimDraft(BaseModel):
    """One structurally typed claim draft returned by the evidence model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    claim_type: EvidenceClaimType
    claim: NonEmptyResponseText
    supporting_excerpt: SupportingExcerpt
    confidence: EvidenceConfidence
    directly_supported: bool
    asserted_name: NonEmptyResponseText | None = None
    asserted_institution: NonEmptyResponseText | None = None
    asserted_department: NonEmptyResponseText | None = None
    availability_status: AvailabilityStatus | None = None
    activity_year: StrictInt | None = None


class StructuredEvidenceClaim(StructuredEvidenceClaimDraft):
    """One claim draft whose cross-field semantics are internally consistent."""

    @model_validator(mode="after")
    def typed_values_must_match_the_claim(self) -> Self:
        """Reject ambiguous availability and require typed identity/affiliation facts."""
        explicit_availability = {
            AvailabilityStatus.CONFIRMED_ACCEPTING,
            AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
        }
        if self.claim_type is EvidenceClaimType.AVAILABILITY:
            if not self.directly_supported or self.availability_status not in explicit_availability:
                raise ValueError("Availability must be explicit and directly supported")
        elif self.availability_status is not None:
            raise ValueError("Only availability claims may set availability status")

        if self.activity_year is not None:
            if self.claim_type not in {
                EvidenceClaimType.PUBLICATION,
                EvidenceClaimType.PROJECT,
            }:
                raise ValueError("Only publication or project claims may set an activity year")
            if not 1900 <= self.activity_year <= 2100:
                raise ValueError("Research activity year must be between 1900 and 2100")
            if re.search(rf"(?<!\d){self.activity_year}(?!\d)", self.supporting_excerpt) is None:
                raise ValueError("Research activity year must be explicit in the excerpt")

        if self.directly_supported and self.asserted_name is None:
            raise ValueError("Every direct evidence claim must state the extracted person name")

        if (
            self.directly_supported
            and self.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
            and any(
                value is None
                for value in (
                    self.asserted_name,
                    self.asserted_institution,
                    self.asserted_department,
                )
            )
        ):
            raise ValueError(
                "Direct affiliation evidence must state the person, institution, and department"
            )
        return self


class StructuredEvidenceExtractionResult(BaseModel):
    """Complete typed model response for one retrieved source page."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    claims: list[StructuredEvidenceClaimDraft] = Field(default_factory=list)


class EvidenceVerificationModelPort(Protocol):
    """Extract typed claim drafts from one retrieved page."""

    def extract(
        self, extraction_input: EvidenceExtractionInput
    ) -> StructuredEvidenceExtractionResult:
        """Return structured claims without assigning provenance or identifiers."""
        ...


class EvidenceModelError(RuntimeError):
    """Base typed failure at the evidence-model boundary."""


class EvidenceModelInvocationError(EvidenceModelError):
    """The evidence model failed before returning a structured response."""


class EvidenceModelOutputError(EvidenceModelError):
    """The model response or its page grounding violated the evidence contract."""


def _evidence_identity_payload(
    supervisor_id: str,
    source_url: str,
    source_kind: SourceKind,
    claim_type: EvidenceClaimType,
    claim: str,
    supporting_excerpt: str | None,
    confidence: EvidenceConfidence,
    directly_supported: bool,
    availability_status: AvailabilityStatus | None,
    asserted_name: str | None,
    asserted_institution: str | None,
    asserted_department: str | None,
    activity_year: int | None,
) -> dict[str, str | bool | int | None]:
    """Return the canonical semantic fields owned by one evidence identifier."""

    def normalized_optional(value: str | None) -> str | None:
        return _normalized_text(value) if value is not None else None

    return {
        "identity_version": 3,
        "supervisor_id": supervisor_id,
        "source_url": source_url,
        "source_kind": source_kind.value,
        "claim_type": claim_type.value,
        "claim": _normalized_text(claim),
        "supporting_excerpt": normalized_optional(supporting_excerpt),
        "confidence": confidence.value,
        "directly_supported": directly_supported,
        "availability_status": availability_status.value if availability_status else None,
        "asserted_name": normalized_optional(asserted_name),
        "asserted_institution": normalized_optional(asserted_institution),
        "asserted_department": normalized_optional(asserted_department),
        "activity_year": activity_year,
    }


def deterministic_evidence_id(
    supervisor_id: str,
    source_url: str,
    source_kind: SourceKind,
    draft: StructuredEvidenceClaim,
    *,
    directly_supported: bool,
) -> str:
    """Create a stable identifier from every grounded semantic claim field."""
    payload = _evidence_identity_payload(
        supervisor_id,
        source_url,
        source_kind,
        draft.claim_type,
        draft.claim,
        draft.supporting_excerpt,
        draft.confidence,
        directly_supported,
        draft.availability_status,
        draft.asserted_name,
        draft.asserted_institution,
        draft.asserted_department,
        draft.activity_year,
    )
    identity = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:20]
    return f"evidence-{digest}"


def _claim_identity_payload(
    claim: EvidenceClaim,
) -> dict[str, str | bool | int | None]:
    """Project a persisted claim back to the collision-checking identity payload."""
    return _evidence_identity_payload(
        claim.supervisor_id,
        str(claim.source_url),
        claim.source_kind,
        claim.claim_type,
        claim.claim,
        claim.supporting_excerpt,
        claim.confidence,
        claim.directly_supported,
        claim.availability_status,
        claim.asserted_name,
        claim.asserted_institution,
        claim.asserted_department,
        claim.activity_year,
    )


def _stable_unique_claim_drafts(
    drafts: list[StructuredEvidenceClaimDraft],
) -> tuple[StructuredEvidenceClaimDraft, ...]:
    """Keep the first occurrence of each exact typed draft in provider order."""
    seen: set[str] = set()
    unique: list[StructuredEvidenceClaimDraft] = []
    for draft in drafts:
        identity = json.dumps(
            draft.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(draft)
    return tuple(unique)


def _has_same_page_availability_conflict(
    drafts: tuple[StructuredEvidenceClaimDraft, ...],
) -> bool:
    """Detect mutually exclusive explicit availability values from one page."""
    explicit_values = {
        AvailabilityStatus.CONFIRMED_ACCEPTING,
        AvailabilityStatus.CONFIRMED_NOT_ACCEPTING,
    }
    page_values = {
        draft.availability_status
        for draft in drafts
        if draft.claim_type is EvidenceClaimType.AVAILABILITY
        and draft.availability_status in explicit_values
    }
    return len(page_values) > 1


class EvidenceVerificationAgent:
    """Ground structured model output and apply deterministic verification rules."""

    def __init__(self, model: EvidenceVerificationModelPort) -> None:
        self._model = model

    def extract_claims(
        self,
        supervisor: ProspectiveSupervisor,
        extracted_content: ExtractedContent,
        source_kind: SourceKind,
    ) -> tuple[EvidenceClaim, ...]:
        """Bind grounded claim drafts to system-owned identifiers and provenance."""
        extraction_input = EvidenceExtractionInput(
            expected_name=supervisor.full_name,
            expected_institution=supervisor.institution,
            expected_department=supervisor.department,
            source_url=extracted_content.source_url,
            source_kind=source_kind,
            page_content=extracted_content.content,
        )
        try:
            response = StructuredEvidenceExtractionResult.model_validate(
                self._model.extract(extraction_input)
            )
        except EvidenceModelInvocationError:
            raise
        except (EvidenceModelOutputError, ValidationError, ValueError) as error:
            raise EvidenceModelOutputError(
                "The evidence model returned invalid structured output."
            ) from error
        except Exception as error:
            raise EvidenceModelInvocationError("The evidence model request failed.") from error

        normalized_page = _normalized_text(extracted_content.content)
        unique_drafts = _stable_unique_claim_drafts(response.claims)
        conflicting_page_availability = _has_same_page_availability_conflict(unique_drafts)
        admitted_drafts: list[StructuredEvidenceClaim] = []
        for draft in unique_drafts:
            if conflicting_page_availability and draft.claim_type is EvidenceClaimType.AVAILABILITY:
                continue
            try:
                admitted = StructuredEvidenceClaim.model_validate(draft.model_dump(mode="python"))
            except (ValidationError, ValueError):
                continue
            if _normalized_text(admitted.supporting_excerpt) not in normalized_page:
                continue
            admitted_drafts.append(admitted)

        page_identity_supported = any(
            draft.claim_type is EvidenceClaimType.IDENTITY
            and draft.directly_supported
            and draft.asserted_name is not None
            and supervisor_names_are_title_equivalent(
                draft.asserted_name,
                supervisor.full_name,
            )
            and _normalized_text(draft.asserted_name) in _normalized_text(draft.supporting_excerpt)
            and _normalized_text(draft.supporting_excerpt) in normalized_page
            for draft in admitted_drafts
        )
        claims: list[EvidenceClaim] = []
        for draft in admitted_drafts:
            try:
                provisional_claim = EvidenceClaim(
                    evidence_id="unassigned-evidence-id",
                    supervisor_id=supervisor.supervisor_id,
                    claim_type=draft.claim_type,
                    claim=draft.claim,
                    source_url=extracted_content.source_url,
                    source_kind=source_kind,
                    retrieved_at=extracted_content.retrieved_at,
                    confidence=draft.confidence,
                    directly_supported=(
                        draft.directly_supported
                        and (
                            draft.claim_type is EvidenceClaimType.IDENTITY
                            or page_identity_supported
                        )
                    ),
                    availability_status=draft.availability_status,
                    asserted_name=draft.asserted_name,
                    asserted_institution=draft.asserted_institution,
                    asserted_department=draft.asserted_department,
                    activity_year=draft.activity_year,
                    supporting_excerpt=draft.supporting_excerpt,
                )
            except (ValidationError, ValueError):
                continue
            direct_support = evidence_claim_is_grounded_for_supervisor(
                provisional_claim,
                supervisor,
            )
            evidence_id = deterministic_evidence_id(
                supervisor.supervisor_id,
                str(extracted_content.source_url),
                source_kind,
                draft,
                directly_supported=direct_support,
            )
            claims.append(
                provisional_claim.model_copy(
                    update={
                        "evidence_id": evidence_id,
                        "directly_supported": direct_support,
                    }
                )
            )
        return tuple(claims)

    def build_verification_record(
        self,
        supervisor: ProspectiveSupervisor,
        evidence: tuple[EvidenceClaim, ...],
        *,
        additional_concerns: tuple[str, ...] = (),
    ) -> SupervisorVerificationRecord:
        """Create either a genuine Verified Supervisor or a partial evidence record."""
        merged = self._merge_and_link_conflicts(evidence)
        missing = self._missing_required_evidence(supervisor, merged)
        concerns = self._verification_concerns(supervisor, merged, additional_concerns)
        availability = derive_availability_status(merged, supervisor.supervisor_id)
        if missing:
            return SupervisorVerificationRecord(
                prospective_supervisor=supervisor,
                evidence=merged,
                verification_status=VerificationStatus.PARTIALLY_VERIFIED,
                availability_status=availability,
                verification_concerns=concerns,
                missing_required_evidence=missing,
            )

        verified = verify_supervisor(
            supervisor,
            merged,
            availability_status=availability,
            verification_concerns=concerns,
        )
        return SupervisorVerificationRecord(
            prospective_supervisor=supervisor,
            evidence=merged,
            verification_status=verified.verification_status,
            availability_status=availability,
            verification_concerns=verified.verification_concerns,
            verified_supervisor=verified,
        )

    @staticmethod
    def _merge_and_link_conflicts(
        evidence: tuple[EvidenceClaim, ...],
    ) -> tuple[EvidenceClaim, ...]:
        by_id: dict[str, EvidenceClaim] = {}
        for claim in evidence:
            existing = by_id.get(claim.evidence_id)
            if existing is None:
                by_id[claim.evidence_id] = claim
                continue
            if _claim_identity_payload(existing) != _claim_identity_payload(claim):
                raise EvidenceModelOutputError(
                    "Distinct evidence claims cannot share one evidence identifier."
                )
            merged_conflicts = tuple(
                dict.fromkeys((*existing.conflicting_evidence_ids, *claim.conflicting_evidence_ids))
            )
            if merged_conflicts != existing.conflicting_evidence_ids:
                by_id[claim.evidence_id] = existing.model_copy(
                    update={"conflicting_evidence_ids": merged_conflicts}
                )
        claims = tuple(by_id.values())
        affiliations = [
            claim
            for claim in claims
            if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
            and claim.directly_supported
            and claim.asserted_institution is not None
        ]
        conflict_ids: dict[str, list[str]] = {}

        def link_conflicts(first: EvidenceClaim, second: EvidenceClaim) -> None:
            conflict_ids.setdefault(first.evidence_id, []).append(second.evidence_id)
            conflict_ids.setdefault(second.evidence_id, []).append(first.evidence_id)

        for claim in affiliations:
            assert claim.asserted_institution is not None
            for other in affiliations:
                if claim.evidence_id >= other.evidence_id or other.asserted_institution is None:
                    continue
                if _normalized_text(other.asserted_institution) != _normalized_text(
                    claim.asserted_institution
                ) or (
                    claim.asserted_department is not None
                    and other.asserted_department is not None
                    and _normalized_text(other.asserted_department)
                    != _normalized_text(claim.asserted_department)
                ):
                    link_conflicts(claim, other)

        availability_claims = [
            claim
            for claim in claims
            if claim.claim_type is EvidenceClaimType.AVAILABILITY
            and claim.directly_supported
            and claim.availability_status is not None
        ]
        for claim in availability_claims:
            for other in availability_claims:
                if (
                    claim.evidence_id < other.evidence_id
                    and claim.availability_status is not other.availability_status
                ):
                    link_conflicts(claim, other)

        linked_claims: list[EvidenceClaim] = []
        for claim in claims:
            linked_ids = tuple(
                dict.fromkeys(
                    (
                        *claim.conflicting_evidence_ids,
                        *conflict_ids.get(claim.evidence_id, ()),
                    )
                )
            )
            linked_claims.append(
                claim.model_copy(update={"conflicting_evidence_ids": linked_ids})
                if linked_ids != claim.conflicting_evidence_ids
                else claim
            )
        return tuple(linked_claims)

    @staticmethod
    def _missing_required_evidence(
        supervisor: ProspectiveSupervisor,
        evidence: tuple[EvidenceClaim, ...],
    ) -> tuple[str, ...]:
        return missing_verification_evidence(evidence, supervisor)

    @staticmethod
    def _verification_concerns(
        supervisor: ProspectiveSupervisor,
        evidence: tuple[EvidenceClaim, ...],
        additional_concerns: tuple[str, ...],
    ) -> tuple[str, ...]:
        concerns = list(additional_concerns)
        affiliations = [
            claim
            for claim in evidence
            if claim.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
            and claim.directly_supported
            and claim.asserted_institution is not None
        ]
        has_affiliation_conflict = any(
            first.evidence_id != second.evidence_id
            and first.asserted_institution is not None
            and second.asserted_institution is not None
            and (
                _normalized_text(first.asserted_institution)
                != _normalized_text(second.asserted_institution)
                or (
                    first.asserted_department is not None
                    and second.asserted_department is not None
                    and _normalized_text(first.asserted_department)
                    != _normalized_text(second.asserted_department)
                )
            )
            for first in affiliations
            for second in affiliations
        )
        if has_affiliation_conflict:
            concerns.append("Retrieved official sources conflict about the current affiliation.")
        expected_affiliation = (
            _normalized_text(supervisor.institution),
            _normalized_text(supervisor.department),
        )
        complete_affiliations = {
            (
                _normalized_text(claim.asserted_institution),
                _normalized_text(claim.asserted_department),
            )
            for claim in affiliations
            if claim.asserted_institution is not None and claim.asserted_department is not None
        }
        if complete_affiliations and expected_affiliation not in complete_affiliations:
            concerns.append(
                "Retrieved affiliation evidence differs from the discovery profile institution "
                "or department."
            )

        availability = derive_availability_status(evidence, supervisor.supervisor_id)
        if availability is AvailabilityStatus.CONFIRMED_NOT_ACCEPTING:
            concerns.append(
                "A retrieved source explicitly states that doctoral Candidates are not accepted."
            )
        elif availability is AvailabilityStatus.CONFLICTING_EVIDENCE:
            concerns.append("Retrieved sources conflict about doctoral supervision availability.")
        return tuple(dict.fromkeys(concerns))
