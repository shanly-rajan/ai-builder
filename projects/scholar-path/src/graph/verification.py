"""Pure evidence routing and alternate official-source selection."""

from __future__ import annotations

import re
from collections.abc import Mapping
from enum import StrEnum
from typing import Annotated, Final, Self, cast
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, model_validator

from ..domain import (
    ProspectiveSupervisor,
    SearchResult,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationEvidenceStandard,
    VerificationStatus,
    is_singular_person_profile_url,
)
from ..tools.content_extraction import ContentExtractionErrorCategory
from ..tools.supervisor_search import SearchErrorCategory

STRICT_MINIMUM_VERIFIED_SUPERVISORS: Final = 5
IDENTITY_ONLY_MVP_MINIMUM_VERIFIED_SUPERVISORS: Final = 3


def default_minimum_verified_supervisors(
    standard: VerificationEvidenceStandard,
) -> int:
    """Return the deterministic cohort floor selected by the evidence standard."""
    if standard is VerificationEvidenceStandard.IDENTITY_ONLY_MVP:
        return IDENTITY_ONLY_MVP_MINIMUM_VERIFIED_SUPERVISORS
    return STRICT_MINIMUM_VERIFIED_SUPERVISORS


class EvidenceVerificationRoute(StrEnum):
    """Deterministic routes available after evidence sufficiency evaluation."""

    RETRY_ALTERNATE = "retry_alternate_evidence_source"
    EVALUATE_RESEARCH_FIT = "evaluate_research_fit"
    STOP_PARTIAL = "__end__"


class VerificationStoppingCondition(StrEnum):
    """Explicit condition for continuing beyond evidence verification."""

    RETRY_EACH_PARTIAL_THEN_REQUIRE_MINIMUM = "retry_each_partial_then_require_minimum"


class VerificationPolicy(BaseModel):
    """Bounded deterministic policy for Supervisor evidence verification."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    minimum_verified_supervisors: int = Field(
        default=STRICT_MINIMUM_VERIFIED_SUPERVISORS,
        ge=1,
    )
    verification_evidence_standard: VerificationEvidenceStandard = (
        VerificationEvidenceStandard.STRICT
    )
    maximum_alternate_source_retries: int = Field(default=1, ge=0, le=1)
    stopping_condition: VerificationStoppingCondition = (
        VerificationStoppingCondition.RETRY_EACH_PARTIAL_THEN_REQUIRE_MINIMUM
    )

    @model_validator(mode="before")
    @classmethod
    def apply_standard_specific_minimum(cls, data: object) -> object:
        """Use a smaller cohort only when the MVP standard explicitly opts in."""
        if not isinstance(data, Mapping):
            return data
        values = dict(cast(Mapping[str, object], data))
        if "minimum_verified_supervisors" in values:
            return values
        standard = values.get(
            "verification_evidence_standard",
            VerificationEvidenceStandard.STRICT,
        )
        if standard in {
            VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
            VerificationEvidenceStandard.IDENTITY_ONLY_MVP.value,
        }:
            values["minimum_verified_supervisors"] = IDENTITY_ONLY_MVP_MINIMUM_VERIFIED_SUPERVISORS
        return values


class EvidenceSourceReference(BaseModel):
    """One official alternate URL selected from search without using its snippet as evidence."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    supervisor_id: str = Field(min_length=1)
    source_url: HttpUrl
    source_kind: SourceKind
    originating_query: str = Field(min_length=1)


class EvidenceExtractionAttempt(BaseModel):
    """Sanitized audit record for one known-page extraction attempt."""

    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    supervisor_id: str = Field(min_length=1)
    source_url: HttpUrl
    source_kind: SourceKind
    attempt_number: int = Field(ge=1, le=2)
    discovery_round: int = Field(ge=1)
    alternate_source: StrictBool
    successful: StrictBool
    error_category: ContentExtractionErrorCategory | None = None

    @model_validator(mode="after")
    def error_must_match_success(self) -> EvidenceExtractionAttempt:
        """Prevent ambiguous audit records."""
        if self.successful == (self.error_category is not None):
            raise ValueError("Successful extraction attempts cannot carry an error category")
        return self


class AlternateSourceRejectionCategory(StrEnum):
    """First deterministic gate that excluded one alternate-source result."""

    QUERY_MISMATCH = "query_mismatch"
    SAME_URL = "same_url"
    HTTPS_OR_HOST_INVALID = "https_or_host_invalid"
    EXACT_PERSON_TEXT_MISSING = "exact_person_text_missing"
    EXACT_INSTITUTION_TEXT_MISSING = "exact_institution_text_missing"
    SINGULAR_ROUTE_MISMATCH = "singular_route_mismatch"
    ACADEMIC_HOST_MISMATCH = "academic_host_mismatch"
    SOURCE_KIND_UNSUPPORTED = "source_kind_unsupported"


class AlternateSourceSelectionOutcome(StrEnum):
    """Sanitized outcome of one bounded alternate official-source search."""

    SELECTED = "selected"
    NO_RESULTS = "no_results"
    REJECTED_ALL = "rejected_all"
    PROVIDER_ERROR = "provider_error"
    NOT_CONFIGURED = "not_configured"


class AlternateSourceRejectionCounts(BaseModel):
    """Aggregate first-failed-gate counts with no query or result content."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    query_mismatch: Annotated[int, Field(strict=True, ge=0)] = 0
    same_url: Annotated[int, Field(strict=True, ge=0)] = 0
    https_or_host_invalid: Annotated[int, Field(strict=True, ge=0)] = 0
    exact_person_text_missing: Annotated[int, Field(strict=True, ge=0)] = 0
    exact_institution_text_missing: Annotated[int, Field(strict=True, ge=0)] = 0
    singular_route_mismatch: Annotated[int, Field(strict=True, ge=0)] = 0
    academic_host_mismatch: Annotated[int, Field(strict=True, ge=0)] = 0
    source_kind_unsupported: Annotated[int, Field(strict=True, ge=0)] = 0

    @property
    def total(self) -> int:
        """Return the number of results rejected by exactly one selector gate."""
        return sum(getattr(self, category.value) for category in AlternateSourceRejectionCategory)

    def increment(self, category: AlternateSourceRejectionCategory) -> Self:
        """Return a fully revalidated count object with one gate incremented."""
        values = self.model_dump(mode="python")
        values[category.value] += 1
        return self.__class__.model_validate(values)

    def combine(self, other: Self) -> Self:
        """Return a fully revalidated field-wise aggregate."""
        return self.__class__.model_validate(
            {
                category.value: getattr(self, category.value) + getattr(other, category.value)
                for category in AlternateSourceRejectionCategory
            }
        )


class AlternateSourceAttempt(BaseModel):
    """Privacy-safe audit record for one Supervisor's alternate-source search."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    supervisor_id: str = Field(min_length=1)
    attempt_number: Annotated[int, Field(strict=True, ge=1)]
    discovery_round: Annotated[int, Field(strict=True, ge=1)]
    outcome: AlternateSourceSelectionOutcome
    result_count: Annotated[int, Field(strict=True, ge=0)]
    eligible_result_count: Annotated[int, Field(strict=True, ge=0)]
    rejection_counts: AlternateSourceRejectionCounts = Field(
        default_factory=AlternateSourceRejectionCounts
    )
    error_category: SearchErrorCategory | None = None

    @model_validator(mode="after")
    def outcome_must_match_aggregate_counts(self) -> Self:
        """Make every result and provider failure auditable without raw content."""
        accounted_results = self.eligible_result_count + self.rejection_counts.total
        provider_returned_results = self.outcome in {
            AlternateSourceSelectionOutcome.SELECTED,
            AlternateSourceSelectionOutcome.NO_RESULTS,
            AlternateSourceSelectionOutcome.REJECTED_ALL,
        }
        if provider_returned_results:
            if self.error_category is not None:
                raise ValueError("Provider-returned alternate results cannot carry an error")
            if accounted_results != self.result_count:
                raise ValueError("Alternate-source counts must account for every result")

        if self.outcome is AlternateSourceSelectionOutcome.SELECTED:
            if self.eligible_result_count < 1:
                raise ValueError("A selected alternate source requires an eligible result")
        elif self.outcome is AlternateSourceSelectionOutcome.NO_RESULTS:
            if self.result_count != 0:
                raise ValueError("A no-results outcome requires zero results")
        elif self.outcome is AlternateSourceSelectionOutcome.REJECTED_ALL:
            if self.result_count < 1 or self.eligible_result_count != 0:
                raise ValueError("A rejected-all outcome requires only rejected results")
        elif self.outcome is AlternateSourceSelectionOutcome.PROVIDER_ERROR:
            if self.error_category is None or self.result_count != 0 or accounted_results != 0:
                raise ValueError("A provider error requires one typed error and zero results")
        elif self.outcome is AlternateSourceSelectionOutcome.NOT_CONFIGURED and (
            self.error_category is not None or self.result_count != 0 or accounted_results != 0
        ):
            raise ValueError("An unconfigured search requires no provider result or error")
        return self


class AlternateSourceSelectionEvaluation(BaseModel):
    """Ephemeral typed selector result; only aggregate fields are persisted."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    selected_source: EvidenceSourceReference | None = None
    result_count: Annotated[int, Field(strict=True, ge=0)]
    eligible_result_count: Annotated[int, Field(strict=True, ge=0)]
    rejection_counts: AlternateSourceRejectionCounts

    @model_validator(mode="after")
    def selection_must_match_counts(self) -> Self:
        """Require a selected reference exactly when at least one result was eligible."""
        if self.eligible_result_count + self.rejection_counts.total != self.result_count:
            raise ValueError("Alternate-source evaluation must account for every result")
        if (self.selected_source is None) == (self.eligible_result_count > 0):
            raise ValueError("The first eligible result must be selected")
        return self

    @property
    def outcome(self) -> AlternateSourceSelectionOutcome:
        """Derive the successful provider outcome from aggregate counts."""
        if self.selected_source is not None:
            return AlternateSourceSelectionOutcome.SELECTED
        if self.result_count == 0:
            return AlternateSourceSelectionOutcome.NO_RESULTS
        return AlternateSourceSelectionOutcome.REJECTED_ALL


def route_after_evidence_sufficiency(
    policy: VerificationPolicy,
    verification_records: tuple[SupervisorVerificationRecord, ...],
    *,
    alternate_retry_count: int,
) -> EvidenceVerificationRoute:
    """Route from immutable verification outcomes without invoking a model or provider."""
    if alternate_retry_count < 0:
        raise ValueError("alternate_retry_count must not be negative")
    verified_count = sum(
        record.verification_status is not VerificationStatus.PARTIALLY_VERIFIED
        for record in verification_records
    )
    if (
        policy.verification_evidence_standard is VerificationEvidenceStandard.IDENTITY_ONLY_MVP
        and verified_count >= policy.minimum_verified_supervisors
    ):
        return EvidenceVerificationRoute.EVALUATE_RESEARCH_FIT

    has_partial = any(
        record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
        for record in verification_records
    )
    if has_partial and alternate_retry_count < policy.maximum_alternate_source_retries:
        return EvidenceVerificationRoute.RETRY_ALTERNATE

    if verified_count >= policy.minimum_verified_supervisors:
        return EvidenceVerificationRoute.EVALUATE_RESEARCH_FIT
    return EvidenceVerificationRoute.STOP_PARTIAL


_PERSON_TITLES = {
    "assistant",
    "associate",
    "dr",
    "emerita",
    "emeritus",
    "prof",
    "professor",
}
_GENERIC_INSTITUTION_TOKENS = {
    "and",
    "centre",
    "college",
    "department",
    "for",
    "institute",
    "of",
    "school",
    "technology",
    "the",
    "university",
}
_INSTITUTION_ACRONYM_STOP_TOKENS = {"and", "for", "of", "the"}
_NAMED_INSTITUTION_MARKERS = {"college", "institute", "university"}
_OFFICIAL_ALTERNATE_SOURCE_KINDS = {
    SourceKind.DEPARTMENT_PAGE,
    SourceKind.INSTITUTIONAL_DIRECTORY,
    SourceKind.UNIVERSITY_PROFILE,
}


def alternate_official_source_query(supervisor: ProspectiveSupervisor) -> str:
    """Build one deterministic query used only to locate a stronger official page."""
    person_name = " ".join(_substantive_person_name_tokens(supervisor.full_name))
    return f'"{person_name}" "{supervisor.institution}" official university profile department'


def select_alternate_official_source(
    supervisor: ProspectiveSupervisor,
    results: tuple[SearchResult, ...],
    *,
    query: str,
) -> EvidenceSourceReference | None:
    """Select the first plausible official page without treating its snippet as evidence."""
    return evaluate_alternate_official_sources(supervisor, results, query=query).selected_source


def evaluate_alternate_official_sources(
    supervisor: ProspectiveSupervisor,
    results: tuple[SearchResult, ...],
    *,
    query: str,
) -> AlternateSourceSelectionEvaluation:
    """Select the first official profile and count every result's first failed gate."""
    original_url = _canonical_url(str(supervisor.profile_url))
    person_tokens = tuple(_substantive_person_name_tokens(supervisor.full_name, casefold=True))
    institution_phrase_tokens = tuple(_word_tokens(supervisor.institution))
    institution_tokens = tuple(
        token
        for token in _word_tokens(supervisor.institution)
        if token not in _GENERIC_INSTITUTION_TOKENS and len(token) >= 2
    )
    selected_source: EvidenceSourceReference | None = None
    eligible_result_count = 0
    rejection_counts = AlternateSourceRejectionCounts()

    for result in results:
        if result.originating_query != query:
            rejection_counts = rejection_counts.increment(
                AlternateSourceRejectionCategory.QUERY_MISMATCH
            )
            continue
        candidate_url = str(result.url)
        if _canonical_url(candidate_url) == original_url:
            rejection_counts = rejection_counts.increment(AlternateSourceRejectionCategory.SAME_URL)
            continue
        parsed = urlsplit(candidate_url)
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not hostname:
            rejection_counts = rejection_counts.increment(
                AlternateSourceRejectionCategory.HTTPS_OR_HOST_INVALID
            )
            continue
        result_texts = (result.title, result.description)
        person_matches = bool(
            person_tokens
            and any(
                _contains_token_sequence(
                    tuple(token for token in _word_tokens(text) if token not in _PERSON_TITLES),
                    person_tokens,
                )
                for text in result_texts
            )
        )
        if not person_matches:
            rejection_counts = rejection_counts.increment(
                AlternateSourceRejectionCategory.EXACT_PERSON_TEXT_MISSING
            )
            continue
        academic_organization = _academic_organization_label(hostname)
        institution_matches_hostname = bool(
            institution_tokens
            and academic_organization
            and all(token in academic_organization for token in institution_tokens)
        )
        institution_abbreviation_matches = bool(
            academic_organization
            and _academic_organization_is_institution_abbreviation(
                academic_organization,
                supervisor.institution,
            )
        )
        institution_matches_official_host = (
            institution_matches_hostname or institution_abbreviation_matches
        )
        institution_matches_sparse_official_host = bool(
            academic_organization
            and _academic_organization_strongly_matches_institution(
                academic_organization,
                supervisor.institution,
            )
        )
        institution_matches_text = bool(
            institution_phrase_tokens
            and any(
                _contains_token_sequence(tuple(_word_tokens(text)), institution_phrase_tokens)
                for text in result_texts
            )
        )
        title_names_conflicting_institution = _title_names_conflicting_institution(
            result.title,
            institution_phrase_tokens,
        )
        if not institution_matches_text and not (
            institution_matches_sparse_official_host and not title_names_conflicting_institution
        ):
            rejection_counts = rejection_counts.increment(
                AlternateSourceRejectionCategory.EXACT_INSTITUTION_TEXT_MISSING
            )
            continue
        singular_person_profile = is_singular_person_profile_url(
            candidate_url
        ) and _profile_path_matches_expected_person_or_identifier(
            parsed.path,
            person_tokens,
        )
        if not singular_person_profile:
            rejection_counts = rejection_counts.increment(
                AlternateSourceRejectionCategory.SINGULAR_ROUTE_MISMATCH
            )
            continue
        if not institution_matches_official_host:
            rejection_counts = rejection_counts.increment(
                AlternateSourceRejectionCategory.ACADEMIC_HOST_MISMATCH
            )
            continue
        source_kind = classify_evidence_source_kind(result.url, title=result.title)
        if source_kind not in _OFFICIAL_ALTERNATE_SOURCE_KINDS:
            rejection_counts = rejection_counts.increment(
                AlternateSourceRejectionCategory.SOURCE_KIND_UNSUPPORTED
            )
            continue
        eligible_result_count += 1
        source_reference = EvidenceSourceReference(
            supervisor_id=supervisor.supervisor_id,
            source_url=result.url,
            source_kind=source_kind,
            originating_query=result.originating_query,
        )
        if selected_source is None:
            selected_source = source_reference
    return AlternateSourceSelectionEvaluation(
        selected_source=selected_source,
        result_count=len(results),
        eligible_result_count=eligible_result_count,
        rejection_counts=rejection_counts,
    )


def classify_evidence_source_kind(
    source_url: str | HttpUrl,
    *,
    title: str = "",
) -> SourceKind:
    """Classify a known source conservatively from URL and optional result title."""
    parsed = urlsplit(str(source_url))
    tokens = set(_word_tokens(f"{parsed.hostname or ''} {parsed.path} {title}"))
    academic_hostname = _is_academic_hostname((parsed.hostname or "").casefold())
    if tokens & {"publication", "publications", "article", "articles", "paper", "papers"}:
        return SourceKind.PUBLICATION
    if (
        tokens & {"repository", "repositories", "researchportal"}
        or {
            "research",
            "portal",
        }
        <= tokens
    ):
        return SourceKind.RESEARCH_REPOSITORY
    if tokens & {"project", "projects"}:
        return SourceKind.PROJECT_PAGE
    if academic_hostname and is_singular_person_profile_url(str(source_url)):
        if tokens & {"directories", "directory", "staff"}:
            return SourceKind.INSTITUTIONAL_DIRECTORY
        return SourceKind.UNIVERSITY_PROFILE
    if academic_hostname and tokens & {
        "department",
        "school",
        "centre",
        "center",
        "group",
        "laboratory",
        "lab",
    }:
        return SourceKind.DEPARTMENT_PAGE
    if academic_hostname and tokens & {"directory", "directories", "staff"}:
        return SourceKind.INSTITUTIONAL_DIRECTORY
    if academic_hostname and tokens & {
        "academic",
        "academics",
        "faculty",
        "people",
        "person",
        "persons",
        "profile",
        "profiles",
        "researcher",
        "researchers",
    }:
        return SourceKind.UNIVERSITY_PROFILE
    return SourceKind.OTHER


def _canonical_url(value: str) -> str:
    parsed = urlsplit(value)
    return urlunsplit(
        (
            parsed.scheme.casefold(),
            parsed.netloc.casefold(),
            parsed.path.rstrip("/") or "/",
            parsed.query,
            "",
        )
    )


def _word_tokens(value: str) -> list[str]:
    return re.findall(r"[^\W_]+", value.casefold(), re.UNICODE)


def _substantive_person_name_tokens(value: str, *, casefold: bool = False) -> list[str]:
    """Remove only leading academic titles while retaining the substantive person name."""
    tokens = re.findall(r"[^\W_]+", value, re.UNICODE)
    while tokens and tokens[0].casefold() in _PERSON_TITLES:
        tokens.pop(0)
    if casefold:
        return [token.casefold() for token in tokens]
    return tokens


def _contains_token_sequence(haystack: tuple[str, ...], needle: tuple[str, ...]) -> bool:
    if not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[index : index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def _title_names_conflicting_institution(
    title: str,
    expected_institution_tokens: tuple[str, ...],
) -> bool:
    """Reject an explicit competing institution while allowing sparse profile titles.

    Search metadata is used only to choose a page for extraction. A controlled academic
    hostname may establish the expected institution when a sparse title names only the
    person, but it must not override a different University, College, or Institute named
    in that title. The retrieved page still has to provide directly grounded current-
    affiliation evidence before verification can succeed.
    """
    title_tokens = tuple(_word_tokens(title))
    if not title_tokens or _contains_token_sequence(title_tokens, expected_institution_tokens):
        return False
    return bool(set(title_tokens) & _NAMED_INSTITUTION_MARKERS)


def _is_academic_hostname(hostname: str) -> bool:
    return _academic_organization_label(hostname) is not None


def _academic_organization_is_institution_abbreviation(
    academic_organization: str,
    institution: str,
) -> bool:
    """Match a controlled academic hostname label to an explicit institution acronym."""
    organization = "".join(_word_tokens(academic_organization))
    institution_tokens = _word_tokens(institution)
    if len(organization) < 2 or not institution_tokens:
        return False
    if organization in institution_tokens:
        return True
    meaningful_tokens = tuple(
        token for token in institution_tokens if token not in _GENERIC_INSTITUTION_TOKENS
    )
    if (
        len(organization) >= 2
        and len(meaningful_tokens) == 1
        and meaningful_tokens[0].startswith(organization)
    ):
        return True
    acronym = "".join(
        token[0] for token in institution_tokens if token not in _INSTITUTION_ACRONYM_STOP_TOKENS
    )
    return len(acronym) >= 2 and organization == acronym


def _academic_organization_strongly_matches_institution(
    academic_organization: str,
    institution: str,
) -> bool:
    """Require an exact institution token, full label, or acronym for sparse metadata."""
    organization = "".join(_word_tokens(academic_organization))
    institution_tokens = _word_tokens(institution)
    if len(organization) < 2 or not institution_tokens:
        return False
    meaningful_tokens = tuple(
        token for token in institution_tokens if token not in _GENERIC_INSTITUTION_TOKENS
    )
    if organization in institution_tokens or organization == "".join(meaningful_tokens):
        return True
    acronym = "".join(
        token[0] for token in institution_tokens if token not in _INSTITUTION_ACRONYM_STOP_TOKENS
    )
    return len(acronym) >= 2 and organization == acronym


def _profile_path_matches_expected_person_or_identifier(
    path: str,
    person_tokens: tuple[str, ...],
) -> bool:
    """Bind a structurally singular profile path to the expected person or one opaque ID."""
    path_tokens = tuple(_word_tokens(path))
    if _contains_token_sequence(path_tokens, person_tokens):
        return True
    return bool(path_tokens and path_tokens[-1].isdigit())


def _academic_organization_label(hostname: str) -> str | None:
    """Return the controlled organization label immediately before an academic suffix."""
    labels = hostname.rstrip(".").split(".")
    if len(labels) >= 2 and labels[-1] == "edu":
        return labels[-2]
    if (
        len(labels) >= 3
        and labels[-2] in {"ac", "edu"}
        and len(labels[-1]) == 2
        and labels[-1].isalpha()
    ):
        return labels[-3]
    return None
