"""Deterministic extraction and deduplication for Prospective Supervisors."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from ..domain import (
    ProspectiveSupervisor,
    SearchPlan,
    SearchResult,
    SearchResultRejectionCategory,
    SearchResultRejectionCounts,
    SupervisorDiscoveryProvenance,
)

_TITLE_SPLIT_PATTERN = re.compile(r"\s*(?:\||—|–|\s-\s)\s*")
_ACADEMIC_PREFIX_PATTERN = re.compile(
    r"^(Associate Professor|Assistant Professor|Professor|Prof\.?|Dr\.?)\s+(.+)$",
    re.IGNORECASE,
)
_ACADEMIC_PREFIX_SEARCH_PATTERN = re.compile(
    r"\b(Associate Professor|Assistant Professor|Professor|Prof\.?|Dr\.?)\s+"
    r"([^,.;|—–]+)",
    re.IGNORECASE,
)
_ACADEMIC_SUFFIX_PATTERN = re.compile(
    r"^(?P<name>.+?),\s*"
    r"(?P<role>Associate Professor|Assistant Professor|Professor|Prof\.?|Dr\.?|Lecturer|"
    r"Researcher|Research Fellow|Research Scientist|Reader|Principal Investigator)"
    r"(?:\s+(?:at|of|in)\b.*)?$",
    re.IGNORECASE,
)
_ACADEMIC_ROLE_PATTERN = re.compile(
    r"\b(professor|lecturer|researcher|research fellow|research scientist|"
    r"faculty member|academic|reader|principal investigator)\b",
    re.IGNORECASE,
)
_STRONG_INSTITUTION_PATTERN = re.compile(
    r"\b(university|institute|college|polytechnic|academy)\b", re.IGNORECASE
)
_SCHOOL_PATTERN = re.compile(r"\bschool\b", re.IGNORECASE)
_INSTITUTION_ABBREVIATION_PATTERN = re.compile(r"^[A-Z][A-Z.&-]{2,11}$")
_INSTITUTION_ACRONYM_NAME_PATTERN = re.compile(
    r"^[A-Z][A-Z.&-]{1,11}(?:\s+[A-ZÀ-ÖØ-Þ][^\W\d_.'’\-]*){1,3}$",
    re.UNICODE,
)
_ACADEMIC_ROLE_AT_INSTITUTION_PATTERN = re.compile(
    r"^(?:(?:associate|assistant|adjunct|full|senior)\s+)?"
    r"(?:professor|lecturer|researcher|research fellow|research scientist|reader|"
    r"principal investigator)\s+at\s+(?:the\s+)?",
    re.IGNORECASE,
)
_DEPARTMENT_PATTERN = re.compile(
    r"\b(department of|faculty of|school of|centre for|center for)\b", re.IGNORECASE
)
_RESEARCH_CONTEXT_PATTERN = re.compile(
    r"\b(academic|faculty|publication|publications|research|researches|researching|scholar)\b",
    re.IGNORECASE,
)
_SINGULAR_PERSON_PROFILE_URL_PATTERN = re.compile(
    r"/(?:people|persons?|profiles?|staff(?:-directory)?|faculty|researchers?|academics?|"
    r"academic-staff)/(?P<profile_slug>[^/?#]+)(?:[/?#]|$)",
    re.IGNORECASE,
)
_UNNAMED_ACADEMIC_ROLE_PATTERN = re.compile(
    r"\b(?:(?:associate|assistant|adjunct|full|senior)\s+)?"
    r"(?:professor|lecturer|researcher|research fellow|research scientist|reader|"
    r"principal investigator)\s+(?:of|in|at)\b",
    re.IGNORECASE,
)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_NAME_PARTICLES = {
    "al",
    "bin",
    "da",
    "de",
    "del",
    "den",
    "der",
    "di",
    "dos",
    "du",
    "la",
    "le",
    "van",
    "von",
}
_NAME_PARTICLE_ALTERNATION = "|".join(sorted(_NAME_PARTICLES))
_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][^\W\d_]*(?:[-'’][^\W\d_]+)*\.?"
_NAME_TOKEN_PATTERN = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*", re.UNICODE)
_NAME_SEQUENCE = (
    rf"{_NAME_WORD}(?:\s+(?:(?:{_NAME_PARTICLE_ALTERNATION})\s+){{0,2}}"
    rf"{_NAME_WORD}){{1,3}}"
)
_UNTITLED_ACADEMIC_PATTERN = re.compile(
    rf"\b(?P<name>{_NAME_SEQUENCE})\s+"
    r"(?i:(?:is|serves\s+as|works\s+as|,\s*)\s+(?:an?\s+)?"
    r"(?:(?:associate|assistant|adjunct|full|senior|academic)\s+)?"
    r"(?:professor|lecturer|researcher|research fellow|research scientist|reader|"
    r"principal investigator))\b",
    re.UNICODE,
)
_LAST_FIRST_NAME_PATTERN = re.compile(
    rf"^(?P<last>(?:(?:{_NAME_PARTICLE_ALTERNATION})\s+){{0,2}}{_NAME_WORD}"
    rf"(?:\s+(?:(?:{_NAME_PARTICLE_ALTERNATION})\s+){{0,2}}{_NAME_WORD})?)"
    rf",\s*(?P<first>{_NAME_WORD}(?:\s+{_NAME_WORD})?)$",
    re.UNICODE,
)
_NAME_STOP_WORDS = {
    "academic",
    "academy",
    "and",
    "at",
    "center",
    "centre",
    "college",
    "department",
    "directory",
    "dr",
    "experts",
    "faculty",
    "from",
    "group",
    "home",
    "institute",
    "is",
    "lab",
    "laboratory",
    "lecturer",
    "polytechnic",
    "prof",
    "professor",
    "profile",
    "research",
    "researcher",
    "school",
    "staff",
    "team",
    "university",
}
_NON_INSTITUTION_ACRONYM_SUFFIXES = {
    "article",
    "directory",
    "experts",
    "faculty",
    "home",
    "news",
    "press",
    "profile",
    "publication",
    "publications",
    "research",
    "staff",
    "team",
}
_DANGLING_INSTITUTION_SUFFIXES = {"and", "at", "for", "of", "the", "with"}
_NON_INSTITUTION_ACTIVITY_PATTERN = re.compile(
    r"\b(program(?:me)?s?|courses?|workshops?|seminars?|conferences?|webinars?|"
    r"events?|training)\b",
    re.IGNORECASE,
)
_INSTITUTION_HOST_ATTRIBUTION_PATTERN = re.compile(
    r"\b(?:(?:hosted|offered|presented|organi[sz]ed|sponsored|delivered|provided|run)\s+)?"
    r"by\s*[:\-]?\s+(?:the\s+)?[^,.;|]{0,80}\b"
    r"(?:university|institute|college|polytechnic|academy|school)\b",
    re.IGNORECASE,
)
_NON_INSTITUTION_PAGE_ARTIFACT_PATTERN = re.compile(
    r"\bcopyright\b|\b(?:and\s+is|is\s+part\s+of|as\s+well\s+as|strategic\s+alliance)\b",
    re.IGNORECASE,
)
_MAX_BOUNDED_DESCRIPTION_CHARACTERS = 1_000


class SupervisorDiscoveryResult(BaseModel):
    """Structured discovery output containing only Prospective Supervisors."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    prospective_supervisors: tuple[ProspectiveSupervisor, ...] = ()
    result_count: int = Field(default=0, ge=0)
    plausible_supervisor_count: int = Field(default=0, ge=0)
    duplicate_result_count: int = Field(default=0, ge=0)
    rejection_counts: SearchResultRejectionCounts = Field(
        default_factory=SearchResultRejectionCounts
    )

    @model_validator(mode="after")
    def quality_counts_are_consistent(self) -> SupervisorDiscoveryResult:
        """Keep every routing metric consistent with the structured collection."""
        if self.plausible_supervisor_count > self.result_count:
            raise ValueError("plausible_supervisor_count must not exceed result_count")
        if self.duplicate_result_count > self.plausible_supervisor_count:
            raise ValueError("duplicate_result_count must not exceed plausible_supervisor_count")
        unique_count = self.plausible_supervisor_count - self.duplicate_result_count
        if len(self.prospective_supervisors) != unique_count:
            raise ValueError("prospective_supervisors must match the unique quality count")
        if self.rejection_counts.total + self.plausible_supervisor_count != self.result_count:
            raise ValueError(
                "rejection_counts and plausible_supervisor_count must account for every result"
            )
        return self


def _normalized_identity_text(value: str, *, remove_title: bool = False) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    if remove_title:
        normalized = re.sub(
            r"^(?:associate professor|assistant professor|professor|prof\.?|dr\.?)\s+",
            "",
            normalized,
        )
    return " ".join(re.sub(r"[_\W]+", " ", normalized).split())


def _accent_folded_identity_text(value: str, *, remove_title: bool = False) -> str:
    """Fold accents only for URL-slug identity comparison, never stored display data."""
    decomposed = unicodedata.normalize("NFKD", value)
    without_combining_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return _normalized_identity_text(without_combining_marks, remove_title=remove_title)


def _accent_folded_length_preserving_text(value: str) -> str:
    """Fold one code point at a time so regex match offsets still address the source text."""
    folded_characters: list[str] = []
    for character in value:
        decomposed = unicodedata.normalize("NFKD", character)
        base_character = next(
            (item for item in decomposed if not unicodedata.combining(item)),
            character,
        )
        folded_characters.append(base_character)
    return "".join(folded_characters)


def canonical_profile_url(value: str) -> str:
    """Remove tracking-only URL variance while retaining functional query parameters."""
    parsed = urlsplit(value)
    scheme = parsed.scheme.casefold()
    hostname = (parsed.hostname or "").casefold()
    port = parsed.port
    if port is not None and not (
        (scheme == "http" and port == 80) or (scheme == "https" and port == 443)
    ):
        hostname = f"{hostname}:{port}"
    path = re.sub(r"/{2,}", "/", parsed.path)
    path = "" if path == "/" else path.rstrip("/")
    query_items = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_QUERY_KEYS
    ]
    return urlunsplit((scheme, hostname, path, urlencode(sorted(query_items)), ""))


def deterministic_supervisor_id(
    full_name: str,
    institution: str,
    profile_url: str,
) -> str:
    """Create a stable identifier from the same fields used for deterministic deduplication."""
    canonical_url = canonical_profile_url(profile_url)
    identity = "|".join(
        (
            _normalized_identity_text(full_name, remove_title=True),
            _normalized_identity_text(institution),
            canonical_url,
        )
    )
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return f"supervisor-{digest}"


def _deduplication_key(supervisor: ProspectiveSupervisor) -> tuple[str, str, str]:
    return (
        _normalized_identity_text(supervisor.full_name, remove_title=True),
        _normalized_identity_text(supervisor.institution),
        canonical_profile_url(str(supervisor.profile_url)),
    )


def _legacy_discovery_provenance(
    supervisor: ProspectiveSupervisor,
) -> SupervisorDiscoveryProvenance:
    payload = {
        "source_url": supervisor.discovery_source,
        "originating_query": supervisor.discovery_query,
    }
    try:
        return SupervisorDiscoveryProvenance.model_validate(payload)
    except ValidationError:
        return SupervisorDiscoveryProvenance(
            source_url=supervisor.profile_url,
            originating_query=supervisor.discovery_query,
        )


def deduplicate_prospective_supervisors(
    supervisors: Iterable[ProspectiveSupervisor],
) -> tuple[ProspectiveSupervisor, ...]:
    """Merge equivalent Supervisor records and retain paired provenance in stable order."""
    merged: list[ProspectiveSupervisor] = []
    positions: dict[tuple[str, str, str], int] = {}
    for supervisor in supervisors:
        if not supervisor.discovery_provenance:
            supervisor = supervisor.model_copy(
                update={"discovery_provenance": (_legacy_discovery_provenance(supervisor),)}
            )
        key = _deduplication_key(supervisor)
        position = positions.get(key)
        if position is None:
            positions[key] = len(merged)
            merged.append(supervisor)
            continue

        current = merged[position]
        provenance = list(current.discovery_provenance)
        known_pairs = {(str(item.source_url), item.originating_query) for item in provenance}
        for item in supervisor.discovery_provenance:
            pair = (str(item.source_url), item.originating_query)
            if pair not in known_pairs:
                known_pairs.add(pair)
                provenance.append(item)
        merged[position] = current.model_copy(update={"discovery_provenance": tuple(provenance)})
    return tuple(merged)


def _clean_name_tokens(value: str) -> tuple[str, ...]:
    name_text = re.split(r"[,;|()]+", value, maxsplit=1)[0].strip(" .:-")
    tokens: list[str] = []
    for raw_token in name_text.split():
        token = raw_token.strip(".,:;()[]{}")
        normalized = token.casefold()
        if normalized in _NAME_STOP_WORDS:
            break
        if _NAME_TOKEN_PATTERN.fullmatch(token) is None:
            break
        if not (token[0].isupper() or normalized in _NAME_PARTICLES):
            break
        tokens.append(token)
        if len(tokens) == 5:
            break
    substantive = [token for token in tokens if token.casefold() not in _NAME_PARTICLES]
    if len(substantive) < 2 or len(substantive[-1]) == 1:
        return ()
    return tuple(tokens)


def _result_context(result: SearchResult) -> str:
    """Combine only provider summaries and bounded snippets, never retrieved pages."""
    bounded_description = result.description[:_MAX_BOUNDED_DESCRIPTION_CHARACTERS]
    return ". ".join(part for part in (bounded_description, *result.snippets) if part)


def _bounded_context_clauses(context: str) -> tuple[str, ...]:
    """Split bounded context without treating titles or middle initials as sentences."""
    clauses: list[str] = []
    start = 0
    for index, character in enumerate(context):
        if character not in ".;!?|":
            continue
        if character == ".":
            token_start = index - 1
            while token_start >= start and context[token_start].isalpha():
                token_start -= 1
            preceding_token = context[token_start + 1 : index]
            if (
                len(preceding_token) == 1
                and preceding_token.isupper()
                or preceding_token.casefold() in {"dr", "mr", "mrs", "ms", "prof"}
            ):
                continue
        clause = context[start:index].strip()
        if clause:
            clauses.append(clause)
        start = index + 1
    final_clause = context[start:].strip()
    if final_clause:
        clauses.append(final_clause)
    return tuple(clauses)


def _title_name_tokens(value: str) -> tuple[str, ...]:
    last_first_match = _LAST_FIRST_NAME_PATTERN.fullmatch(value.strip(" .:-"))
    if last_first_match is not None:
        return _clean_name_tokens(
            f"{last_first_match.group('first')} {last_first_match.group('last')}"
        )
    return _clean_name_tokens(value)


def _titled_identity_from_segment(segment: str) -> str | None:
    """Extract one explicit prefix- or suffix-role identity from a title segment."""
    prefix_match = _ACADEMIC_PREFIX_PATTERN.match(segment)
    if prefix_match is not None:
        tokens = _clean_name_tokens(prefix_match.group(2))
        if tokens:
            return f"{prefix_match.group(1)} {' '.join(tokens)}"

    suffix_match = _ACADEMIC_SUFFIX_PATTERN.match(segment)
    if suffix_match is None:
        return None
    tokens = _clean_name_tokens(suffix_match.group("name"))
    return " ".join(tokens) if tokens else None


def _title_segment_names_different_person(segment: str, full_name: str) -> bool:
    """Prevent a co-mentioned person's title segment from supplying owner attributes."""
    segment_identity = _titled_identity_from_segment(segment)
    if segment_identity is None:
        return False
    return _accent_folded_identity_text(
        segment_identity,
        remove_title=True,
    ) != _accent_folded_identity_text(full_name, remove_title=True)


def _clean_institution_segment(value: str) -> str:
    """Remove a role prefix and resolve a strong institution from a title breadcrumb."""
    stripped = re.sub(r"\s*·\s*", " ", value).strip(" .,:;-[]{}()")
    stripped = _ACADEMIC_ROLE_AT_INSTITUTION_PATTERN.sub("", stripped).strip(" .,:;-[]{}()")
    if _is_non_institution_activity_or_host_label(stripped):
        return stripped
    strong_breadcrumb_fragments = tuple(
        fragment.strip(" .,:;-")
        for fragment in stripped.split(":")
        if _STRONG_INSTITUTION_PATTERN.search(fragment)
    )
    return strong_breadcrumb_fragments[-1] if strong_breadcrumb_fragments else stripped


def _is_plausible_acronym_institution(value: str) -> bool:
    """Accept compact institution labels while rejecting common result-page labels."""
    if _INSTITUTION_ABBREVIATION_PATTERN.fullmatch(value):
        return True
    if not _INSTITUTION_ACRONYM_NAME_PATTERN.fullmatch(value):
        return False
    return _has_plausible_institution_suffix(value)


def _has_plausible_institution_suffix(value: str) -> bool:
    """Reject page labels and truncated institution phrases using their final token."""
    suffix = value.rsplit(maxsplit=1)[-1].casefold()
    return suffix not in (_NON_INSTITUTION_ACRONYM_SUFFIXES | _DANGLING_INSTITUTION_SUFFIXES)


def _is_non_institution_activity_or_host_label(value: str) -> bool:
    """Reject event, course, and host labels that do not establish affiliation."""
    return bool(
        _NON_INSTITUTION_ACTIVITY_PATTERN.search(value)
        or _INSTITUTION_HOST_ATTRIBUTION_PATTERN.search(value)
        or _NON_INSTITUTION_PAGE_ARTIFACT_PATTERN.search(value)
    )


def _is_context_supported_two_letter_institution(value: str, context: str) -> bool:
    """Accept a two-letter label only when bounded context states an affiliation to it."""
    if re.fullmatch(r"[A-Z]{2}", value) is None:
        return False
    return bool(
        re.search(
            rf"\b(?:at|from|with)\s+(?:the\s+)?{re.escape(value)}\b",
            context,
            re.IGNORECASE,
        )
    )


def _contextual_academic_names(context: str) -> tuple[str, ...]:
    """Extract named academic-role statements from bounded provider context."""
    names: list[str] = []
    seen: set[str] = set()
    for match in _ACADEMIC_PREFIX_SEARCH_PATTERN.finditer(context):
        tokens = _clean_name_tokens(match.group(2))
        if not tokens:
            continue
        name = f"{match.group(1)} {' '.join(tokens)}"
        normalized = _normalized_identity_text(name, remove_title=True)
        if normalized not in seen:
            seen.add(normalized)
            names.append(name)
    for match in _UNTITLED_ACADEMIC_PATTERN.finditer(context):
        tokens = _clean_name_tokens(match.group("name"))
        if not tokens:
            continue
        name = " ".join(tokens)
        normalized = _normalized_identity_text(name, remove_title=True)
        if normalized not in seen:
            seen.add(normalized)
            names.append(name)
    return tuple(names)


def _singular_profile_url_identity(profile_url: str) -> str | None:
    """Return the normalized identity encoded by one singular profile slug, if present."""
    match = _SINGULAR_PERSON_PROFILE_URL_PATTERN.search(profile_url)
    if match is None:
        return None
    profile_slug = re.sub(
        r"\.(?:html?|aspx?)$",
        "",
        unquote(match.group("profile_slug")),
        flags=re.IGNORECASE,
    )
    slug_identity = _accent_folded_identity_text(profile_slug, remove_title=True)
    slug_identity = " ".join(token for token in slug_identity.split() if not token.isdecimal())
    return slug_identity or None


def _singular_profile_url_supports_identity(profile_url: str, full_name: str) -> bool:
    """Require the singular profile slug to identify the same person as the title."""
    slug_identity = _singular_profile_url_identity(profile_url)
    title_identity = _accent_folded_identity_text(full_name, remove_title=True)
    return slug_identity == title_identity or (
        slug_identity is not None
        and slug_identity.replace(" ", "") == title_identity.replace(" ", "")
    )


def _singular_profile_url_names_different_person(
    profile_url: str,
    full_name: str,
) -> bool:
    """Detect a different person-like slug without treating opaque profile IDs as names."""
    slug_identity = _singular_profile_url_identity(profile_url)
    if slug_identity is None:
        return False
    slug_tokens = slug_identity.split()
    slug_looks_like_person = len(slug_tokens) >= 2 and all(
        token.isalpha() and token not in _NAME_STOP_WORDS for token in slug_tokens
    )
    title_identity = _accent_folded_identity_text(full_name, remove_title=True)
    identities_match = slug_identity == title_identity or slug_identity.replace(
        " ", ""
    ) == title_identity.replace(
        " ",
        "",
    )
    return slug_looks_like_person and not identities_match


def _identity_matches_search_topic(full_name: str, search_plan: SearchPlan) -> bool:
    """Reject untitled identities that reproduce a planned research-topic phrase."""
    normalized_identity = _normalized_identity_text(full_name, remove_title=True)
    normalized_concepts = {
        _normalized_identity_text(concept) for concept in search_plan.expanded_research_concepts
    }
    if normalized_identity in normalized_concepts:
        return True
    bounded_identity = f" {normalized_identity} "
    return any(
        bounded_identity in f" {_normalized_identity_text(item.query)} "
        for item in search_plan.search_queries
    )


def _context_explicitly_supports_scholarly_identity(
    context: str,
    full_name: str,
) -> bool:
    """Recognize only explicit same-person scholarly statements in bounded context."""
    normalized_name = _accent_folded_identity_text(full_name, remove_title=True)
    if not context or not normalized_name:
        return False

    name = re.escape(normalized_name)
    scholarly_noun = (
        r"(?:research(?: interests?| projects?| expertise)?|publications?|scholarly work|"
        r"academic expertise)"
    )
    direct_scholarly_patterns = (
        rf"\b{name}\s+s\s+(?:current |recent |stated )?{scholarly_noun}\b",
        rf"\b{name}\s+researches\b",
        rf"\b{name}\s+(?:publishes|published)\s+"
        rf"(?:\w+\s+){{0,6}}{scholarly_noun}\b",
        rf"\b{name}\s+(?:leads|conducts|undertakes|works on|focuses on|"
        rf"specialises in|specializes in)\s+(?:\w+\s+){{0,6}}{scholarly_noun}\b",
        rf"\b{name}\s+(?:is known for|has|brings|offers)\s+"
        rf"(?:\w+\s+){{0,6}}{scholarly_noun}\b",
        rf"\b{scholarly_noun}\s+(?:of|by)\s+{name}\b",
    )
    negated_scholarly_patterns = (
        rf"\b{name}\s+(?:has|offers|brings)\s+(?:no|not|without)\s+"
        rf"(?:\w+\s+){{0,3}}{scholarly_noun}\b",
        rf"\b{name}\s+(?:has\s+not|does\s+not|did\s+not|cannot|can\s+not)\s+"
        rf"(?:\w+\s+){{0,4}}(?:publish|published|conduct|undertake|have|offer)\w*\b",
        rf"\b{name}\s+(?:lacks?|lacking|without)\s+"
        rf"(?:\w+\s+){{0,3}}{scholarly_noun}\b",
        rf"\b{name}\s+s\s+(?:current |recent |stated )?{scholarly_noun}\s+"
        r"(?:(?:is|are|was|were)\s+)?(?:not|unavailable|absent)\b",
        rf"\b(?:no|not|without)\s+{scholarly_noun}\s+(?:of|by)\s+{name}\b",
    )
    normalized_clauses = tuple(
        _accent_folded_identity_text(clause)
        for clause in _bounded_context_clauses(context)
        if clause.strip()
    )
    return any(
        re.search(pattern, clause)
        for clause in normalized_clauses
        if not any(re.search(pattern, clause) for pattern in negated_scholarly_patterns)
        for pattern in direct_scholarly_patterns
    )


def _extract_name(
    result: SearchResult,
    title_segments: tuple[str, ...],
    search_plan: SearchPlan,
) -> tuple[str | None, SearchResultRejectionCategory | None, bool]:
    """Return a supported person identity or one privacy-safe rejection category."""
    title_name: str | None = None
    title_has_academic_prefix = False
    named_title_segments: list[str] = []
    named_title_segment_indexes: set[int] = set()
    for index, segment in enumerate(title_segments):
        named_identity = _titled_identity_from_segment(segment)
        if named_identity is None:
            continue
        if index == 0:
            title_name = named_identity
            title_has_academic_prefix = True
        else:
            named_title_segments.append(named_identity)
            named_title_segment_indexes.add(index)

    if title_name is None and title_segments:
        tokens = _title_name_tokens(title_segments[0])
        if tokens:
            title_name = " ".join(tokens)

    if title_name is None:
        for named_identity in named_title_segments:
            if _singular_profile_url_supports_identity(str(result.url), named_identity):
                title_name = named_identity
                title_has_academic_prefix = True
                break

    context = _result_context(result)
    contextual_names = _contextual_academic_names(context)
    if title_name is not None:
        if title_has_academic_prefix:
            if _singular_profile_url_names_different_person(str(result.url), title_name):
                return None, SearchResultRejectionCategory.IDENTITY_CONFLICT, False
            return title_name, None, False
        normalized_title = _accent_folded_identity_text(title_name, remove_title=True)
        contextual_identities = {
            _accent_folded_identity_text(name, remove_title=True) for name in contextual_names
        }
        later_named_identities = {
            _accent_folded_identity_text(name, remove_title=True) for name in named_title_segments
        }
        later_untitled_identities: dict[int, str] = {}
        for index, segment in enumerate(title_segments[1:], start=1):
            tokens = _title_name_tokens(segment)
            if tokens:
                later_untitled_identities[index] = _accent_folded_identity_text(
                    " ".join(tokens),
                    remove_title=True,
                )
        unnamed_role_segment_exists = any(
            index not in named_title_segment_indexes
            and index - 1 not in later_untitled_identities
            and _ACADEMIC_ROLE_PATTERN.search(segment)
            for index, segment in enumerate(title_segments[1:], start=1)
        )
        title_is_independently_supported = (
            normalized_title in contextual_identities
            or normalized_title in later_named_identities
            or unnamed_role_segment_exists
        )
        identity_matches_topic = _identity_matches_search_topic(title_name, search_plan)
        if (
            not identity_matches_topic
            and _singular_profile_url_supports_identity(str(result.url), title_name)
            and _context_explicitly_supports_scholarly_identity(context, title_name)
        ):
            return title_name, None, True
        if title_is_independently_supported and not identity_matches_topic:
            return title_name, None, True
        if identity_matches_topic:
            return (
                None,
                SearchResultRejectionCategory.ACADEMIC_CONTEXT_NOT_ESTABLISHED,
                False,
            )
        if (
            contextual_identities
            or later_named_identities
            or set(later_untitled_identities.values())
        ):
            return None, SearchResultRejectionCategory.IDENTITY_CONFLICT, False
        if _SINGULAR_PERSON_PROFILE_URL_PATTERN.search(
            str(result.url)
        ) and _UNNAMED_ACADEMIC_ROLE_PATTERN.search(context):
            return title_name, None, True
        return (
            None,
            SearchResultRejectionCategory.ACADEMIC_CONTEXT_NOT_ESTABLISHED,
            False,
        )

    if contextual_names:
        return contextual_names[0], None, False

    return None, SearchResultRejectionCategory.PERSON_NOT_ESTABLISHED, False


def _has_incomplete_institution_fragment(
    result: SearchResult,
    title_segments: tuple[str, ...],
) -> bool:
    """Detect a truncated affiliation without retaining or exposing its text."""
    possible_fragments = (*title_segments, *re.split(r"[.;,|]", _result_context(result)))
    for fragment in possible_fragments:
        normalized = _clean_institution_segment(fragment).strip()
        if not normalized:
            continue
        has_institution_signal = bool(
            _STRONG_INSTITUTION_PATTERN.search(normalized) or _SCHOOL_PATTERN.search(normalized)
        )
        if has_institution_signal and normalized.rsplit(maxsplit=1)[-1].casefold() in (
            _DANGLING_INSTITUTION_SUFFIXES
        ):
            return True
    return False


def _extract_owner_linked_context_institution(
    context: str,
    full_name: str,
) -> str | None:
    """Capture only the institution licensed by a closed owner-affiliation relation."""
    normalized_name = _accent_folded_identity_text(full_name, remove_title=True)
    name = r"[\W_]{1,4}".join(re.escape(token) for token in normalized_name.split())
    academic_role = (
        r"(?:(?:associate|assistant|adjunct|full|senior)\s+)?"
        r"(?:professor|lecturer|researcher|research fellow|research scientist|reader|"
        r"principal investigator)"
    )
    owner_affiliation = re.compile(
        rf"\b{name}\b\s+(?:"
        rf"is\s+(?:(?:an?|the)\s+)?{academic_role}(?:\s+(?:in|of)\s+[^,.;]{{1,80}}?)?|"
        r"is\s+(?:currently\s+)?(?:based|employed|affiliated)|"
        rf"works(?:\s+as\s+(?:(?:an?|the)\s+)?{academic_role})?|"
        rf"serves\s+as\s+(?:(?:an?|the)\s+)?{academic_role}|"
        r"holds\s+(?:(?:an?|the)\s+)?(?:academic\s+)?(?:position|post|chair|role)"
        r")\s+at\s+(?:the\s+)?",
        re.IGNORECASE,
    )
    activity_boundary = re.compile(
        r",|\bwhere\b|\bwhose\b|\b(?:(?:and\s+(?:(?:she|he|they)\s+)?)?"
        r"(?:researches|researching|studies|publishes|leads|focuses|specialises|"
        r"specializes|teaches|examines|examining|investigates|develops|conducts|"
        r"collaborates|works|serves))\b|\b(?:from|with)\b|\s+-\s+",
        re.IGNORECASE,
    )

    for clause in _bounded_context_clauses(context):
        named_academics = {
            _accent_folded_identity_text(name, remove_title=True)
            for name in _contextual_academic_names(clause)
        }
        if named_academics - {normalized_name}:
            continue
        comparison_clause = _accent_folded_length_preserving_text(clause)
        relation = owner_affiliation.search(comparison_clause)
        if relation is None:
            continue
        if re.search(
            r"\b(?:with|collaborat\w*|partner\w*|projects?|alongside|together|led\s+by)\b",
            relation.group(0),
            re.IGNORECASE,
        ):
            continue
        institution = activity_boundary.split(clause[relation.end() :], maxsplit=1)[0]
        institution = institution.strip(" .,:;-")
        if (
            not _is_non_institution_activity_or_host_label(institution)
            and (
                _STRONG_INSTITUTION_PATTERN.search(institution)
                or _SCHOOL_PATTERN.search(institution)
                or _is_plausible_acronym_institution(institution)
            )
            and _has_plausible_institution_suffix(institution)
        ):
            return institution
    return None


def _extract_institution(
    result: SearchResult,
    title_segments: tuple[str, ...],
    full_name: str,
    *,
    require_owner_linked_context: bool = False,
) -> str | None:
    context = _result_context(result)
    normalized_name = _normalized_identity_text(full_name, remove_title=True)
    for segment in reversed(title_segments):
        if _title_segment_names_different_person(segment, full_name):
            continue
        institution = _clean_institution_segment(segment)
        if (
            not _is_non_institution_activity_or_host_label(institution)
            and _STRONG_INSTITUTION_PATTERN.search(institution)
            and _has_plausible_institution_suffix(institution)
            and _normalized_identity_text(institution, remove_title=True) != normalized_name
        ):
            return institution

    for segment in reversed(title_segments):
        if _title_segment_names_different_person(segment, full_name):
            continue
        stripped = _clean_institution_segment(segment)
        if (
            not _is_non_institution_activity_or_host_label(stripped)
            and _SCHOOL_PATTERN.search(stripped)
            and _has_plausible_institution_suffix(stripped)
            and not stripped.casefold().startswith("school of ")
            and _normalized_identity_text(stripped, remove_title=True) != normalized_name
        ):
            return stripped

    for segment in reversed(title_segments):
        if _title_segment_names_different_person(segment, full_name):
            continue
        stripped = _clean_institution_segment(segment)
        if (
            not _is_non_institution_activity_or_host_label(stripped)
            and (
                _is_plausible_acronym_institution(stripped)
                or _is_context_supported_two_letter_institution(stripped, context)
            )
        ) and _normalized_identity_text(stripped, remove_title=True) != normalized_name:
            return stripped

    if require_owner_linked_context:
        return _extract_owner_linked_context_institution(context, full_name)

    for clause in _bounded_context_clauses(context):
        at_parts = re.split(
            r"\b(?:at|from|with)\s+(?:the\s+)?",
            clause,
            flags=re.IGNORECASE,
        )
        if len(at_parts) < 2:
            continue
        institution = at_parts[-1].strip(" .,:;-")
        institution = re.split(
            r",|\bwhere\b|\bwhose\b|\b(?:and\s+(?:(?:she|he|they)\s+)?)?"
            r"(?:researches|researching|studies|publishes|leads|focuses|specialises|"
            r"specializes|teaches|examines|examining|investigates|develops|conducts)\b",
            institution,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        if (
            not _is_non_institution_activity_or_host_label(institution)
            and (
                _STRONG_INSTITUTION_PATTERN.search(institution)
                or _SCHOOL_PATTERN.search(institution)
                or _INSTITUTION_ABBREVIATION_PATTERN.fullmatch(institution)
                or _is_context_supported_two_letter_institution(institution, clause)
            )
            and _has_plausible_institution_suffix(institution)
        ):
            return institution

    for fragment in re.split(r"[.;,|]", context):
        fragment = fragment.strip(" .,:;-")
        if _is_non_institution_activity_or_host_label(fragment):
            continue
        prefix_match = re.search(
            r"\b(?:The\s+)?University\s+of\s+(?:the\s+)?"
            r"[A-ZÀ-ÖØ-Þ][^,.;|]{1,80}$",
            fragment,
        )
        if prefix_match is not None:
            institution = prefix_match.group(0).strip(" .,:;-")
            if _has_plausible_institution_suffix(institution):
                return institution

        suffix_match = re.search(
            r"\b[A-ZÀ-ÖØ-Þ][^,.;|]{1,80}\s+"
            r"(?:University|Institute|College|Polytechnic|Academy)$",
            fragment,
        )
        if suffix_match is not None:
            institution = suffix_match.group(0).strip(" .,:;-")
            if _has_plausible_institution_suffix(institution):
                return institution
    return None


def _extract_department(
    title_segments: tuple[str, ...],
    institution: str,
    full_name: str,
) -> str:
    normalized_institution = _normalized_identity_text(institution)
    for segment in title_segments:
        if _title_segment_names_different_person(segment, full_name):
            continue
        if not _DEPARTMENT_PATTERN.search(segment):
            continue
        if _normalized_identity_text(segment) != normalized_institution:
            return segment.strip(" .,:;-")
    return "Not stated"


def _has_academic_context(
    result: SearchResult,
    title_segments: tuple[str, ...],
) -> bool:
    context = " ".join((*title_segments, _result_context(result)))
    return bool(
        _ACADEMIC_ROLE_PATTERN.search(context)
        or (
            _SINGULAR_PERSON_PROFILE_URL_PATTERN.search(str(result.url))
            and (_RESEARCH_CONTEXT_PATTERN.search(context) or _DEPARTMENT_PATTERN.search(context))
        )
    )


class SupervisorDiscoveryAgent:
    """Conservatively identify Prospective Supervisors without evaluating Research Fit."""

    def discover(
        self,
        search_plan: SearchPlan,
        search_results: Iterable[SearchResult],
    ) -> SupervisorDiscoveryResult:
        """Extract typed people, reject weak identities, and merge exact provenance."""
        planned_queries = {item.query for item in search_plan.search_queries}
        result_items = tuple(search_results)
        prospective: list[ProspectiveSupervisor] = []
        rejection_counts = SearchResultRejectionCounts()
        for result in result_items:
            if result.originating_query not in planned_queries:
                raise ValueError("SearchResult originating query is not present in SearchPlan")
            title_segments = tuple(
                segment.strip()
                for segment in _TITLE_SPLIT_PATTERN.split(result.title)
                if segment.strip()
            )
            full_name, rejection_category, require_owner_linked_context = _extract_name(
                result,
                title_segments,
                search_plan,
            )
            if full_name is None:
                if rejection_category is None:
                    raise RuntimeError("A missing person identity requires a rejection category")
                rejection_counts = rejection_counts.increment(rejection_category)
                continue
            if full_name.casefold().startswith(("dr ", "dr. ")) and not _has_academic_context(
                result,
                title_segments,
            ):
                rejection_counts = rejection_counts.increment(
                    SearchResultRejectionCategory.ACADEMIC_CONTEXT_NOT_ESTABLISHED
                )
                continue
            institution = _extract_institution(
                result,
                title_segments,
                full_name,
                require_owner_linked_context=require_owner_linked_context,
            )
            if institution is None:
                institution_category = (
                    SearchResultRejectionCategory.INCOMPLETE_INSTITUTION
                    if _has_incomplete_institution_fragment(result, title_segments)
                    else SearchResultRejectionCategory.INSTITUTION_NOT_ESTABLISHED
                )
                rejection_counts = rejection_counts.increment(institution_category)
                continue
            department = _extract_department(title_segments, institution, full_name)
            source_url = str(result.url)
            provenance = SupervisorDiscoveryProvenance(
                source_url=result.url,
                originating_query=result.originating_query,
            )
            prospective.append(
                ProspectiveSupervisor(
                    supervisor_id=deterministic_supervisor_id(
                        full_name,
                        institution,
                        source_url,
                    ),
                    full_name=full_name,
                    institution=institution,
                    department=department,
                    profile_url=result.url,
                    discovery_source=source_url,
                    discovery_query=result.originating_query,
                    discovery_provenance=(provenance,),
                )
            )
        unique_supervisors = deduplicate_prospective_supervisors(prospective)
        return SupervisorDiscoveryResult(
            prospective_supervisors=unique_supervisors,
            result_count=len(result_items),
            plausible_supervisor_count=len(prospective),
            duplicate_result_count=len(prospective) - len(unique_supervisors),
            rejection_counts=rejection_counts,
        )
