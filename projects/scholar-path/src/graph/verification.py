"""Pure evidence routing and alternate official-source selection."""

from __future__ import annotations

import re
from enum import StrEnum
from urllib.parse import urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StrictBool, model_validator

from ..domain import (
    ProspectiveSupervisor,
    SearchResult,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationStatus,
)
from ..tools.content_extraction import ContentExtractionErrorCategory


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

    minimum_verified_supervisors: int = Field(default=5, ge=1)
    maximum_alternate_source_retries: int = Field(default=1, ge=0, le=1)
    stopping_condition: VerificationStoppingCondition = (
        VerificationStoppingCondition.RETRY_EACH_PARTIAL_THEN_REQUIRE_MINIMUM
    )


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


def route_after_evidence_sufficiency(
    policy: VerificationPolicy,
    verification_records: tuple[SupervisorVerificationRecord, ...],
    *,
    alternate_retry_count: int,
) -> EvidenceVerificationRoute:
    """Route from immutable verification outcomes without invoking a model or provider."""
    if alternate_retry_count < 0:
        raise ValueError("alternate_retry_count must not be negative")
    has_partial = any(
        record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
        for record in verification_records
    )
    if has_partial and alternate_retry_count < policy.maximum_alternate_source_retries:
        return EvidenceVerificationRoute.RETRY_ALTERNATE

    verified_count = sum(
        record.verification_status is not VerificationStatus.PARTIALLY_VERIFIED
        for record in verification_records
    )
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
_PERSON_PROFILE_PATH_TOKENS = {
    "academic",
    "academics",
    "faculty",
    "people",
    "person",
    "profile",
    "profiles",
    "staff",
}
_NON_PROFILE_PATH_TOKENS = {
    "article",
    "articles",
    "event",
    "events",
    "news",
    "paper",
    "papers",
    "project",
    "projects",
    "publication",
    "publications",
    "repository",
    "search",
}
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
    original_url = _canonical_url(str(supervisor.profile_url))
    person_tokens = tuple(_substantive_person_name_tokens(supervisor.full_name, casefold=True))
    institution_phrase_tokens = tuple(_word_tokens(supervisor.institution))
    institution_tokens = tuple(
        token
        for token in _word_tokens(supervisor.institution)
        if token not in _GENERIC_INSTITUTION_TOKENS and len(token) >= 2
    )

    for result in results:
        if result.originating_query != query:
            continue
        candidate_url = str(result.url)
        if _canonical_url(candidate_url) == original_url:
            continue
        parsed = urlsplit(candidate_url)
        hostname = (parsed.hostname or "").casefold()
        if parsed.scheme != "https" or not hostname:
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
        academic_organization = _academic_organization_label(hostname)
        institution_matches_hostname = bool(
            institution_tokens
            and academic_organization
            and all(token in academic_organization for token in institution_tokens)
        )
        institution_matches_text = bool(
            institution_phrase_tokens
            and any(
                _contains_token_sequence(tuple(_word_tokens(text)), institution_phrase_tokens)
                for text in result_texts
            )
        )
        abbreviation_profile_matches = bool(
            academic_organization
            and _academic_organization_is_institution_abbreviation(
                academic_organization,
                supervisor.institution,
            )
            and _is_singular_person_profile_path(parsed.path, person_tokens)
        )
        if not (
            person_matches
            and institution_matches_text
            and (institution_matches_hostname or abbreviation_profile_matches)
        ):
            continue
        source_kind = classify_evidence_source_kind(result.url, title=result.title)
        if source_kind not in _OFFICIAL_ALTERNATE_SOURCE_KINDS:
            continue
        return EvidenceSourceReference(
            supervisor_id=supervisor.supervisor_id,
            source_url=result.url,
            source_kind=source_kind,
            originating_query=result.originating_query,
        )
    return None


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
        "faculty",
        "people",
        "person",
        "profile",
        "profiles",
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


def _is_singular_person_profile_path(path: str, person_tokens: tuple[str, ...]) -> bool:
    """Return whether an academic path identifies one person rather than general content."""
    path_tokens = tuple(_word_tokens(path))
    if not path_tokens or set(path_tokens) & _NON_PROFILE_PATH_TOKENS:
        return False
    profile_positions = [
        index for index, token in enumerate(path_tokens) if token in _PERSON_PROFILE_PATH_TOKENS
    ]
    if not profile_positions:
        return False
    final_profile_position = profile_positions[-1]
    if final_profile_position == len(path_tokens) - 1:
        return False
    if _contains_token_sequence(path_tokens, person_tokens):
        return True
    identifier_tokens = path_tokens[final_profile_position + 1 :]
    return len(identifier_tokens) == 1 and identifier_tokens[0].isdigit()


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
