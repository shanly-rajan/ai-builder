"""Deterministic extraction and deduplication for Prospective Supervisors."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

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
_PERSON_URL_PATTERN = re.compile(
    r"/(people|person|profiles?|staff(?:-directory)?|faculty|researchers?|academics?|"
    r"academic-staff|experts?|team|directory)(?:/|$)",
    re.IGNORECASE,
)
_SINGULAR_PERSON_PROFILE_URL_PATTERN = re.compile(
    r"/(?:people|person|profiles?|staff(?:-directory)?|faculty|researchers?|academics?|"
    r"academic-staff)/[^/?#]+(?:[/?#]|$)",
    re.IGNORECASE,
)
_UNNAMED_ACADEMIC_ROLE_PATTERN = re.compile(
    r"\b(?:(?:associate|assistant|adjunct|full|senior)\s+)?"
    r"(?:professor|lecturer|researcher|research fellow|research scientist|reader|"
    r"principal investigator)\s+(?:of|in|at)\b",
    re.IGNORECASE,
)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_NAME_PARTICLES = {"al", "bin", "da", "de", "del", "di", "la", "le", "van", "von"}
_NAME_PARTICLE_ALTERNATION = "|".join(sorted(_NAME_PARTICLES))
_NAME_WORD = r"[A-ZÀ-ÖØ-Þ][^\W\d_.'’\-]*"
_NAME_SEQUENCE = rf"{_NAME_WORD}(?:\s+(?:(?:{_NAME_PARTICLE_ALTERNATION})\s+)?{_NAME_WORD}){{1,3}}"
_UNTITLED_ACADEMIC_PATTERN = re.compile(
    rf"\b(?P<name>{_NAME_SEQUENCE})\s+"
    r"(?i:(?:is|serves\s+as|works\s+as|,\s*)\s+(?:an?\s+)?"
    r"(?:(?:associate|assistant|adjunct|full|senior|academic)\s+)?"
    r"(?:professor|lecturer|researcher|research fellow|research scientist|reader|"
    r"principal investigator))\b",
    re.UNICODE,
)
_LAST_FIRST_NAME_PATTERN = re.compile(
    rf"^(?P<last>(?:(?:{_NAME_PARTICLE_ALTERNATION})\s+)?{_NAME_WORD}"
    rf"(?:\s+(?:{_NAME_PARTICLE_ALTERNATION})\s+{_NAME_WORD})?)"
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
        if not re.fullmatch(r"[^\W\d_][^\W\d_.'’\-]*", token, re.UNICODE):
            break
        if not (token[0].isupper() or normalized in _NAME_PARTICLES):
            break
        tokens.append(token)
        if len(tokens) == 5:
            break
    substantive = [token for token in tokens if token.casefold() not in _NAME_PARTICLES]
    return tuple(tokens) if len(substantive) >= 2 else ()


def _result_context(result: SearchResult) -> str:
    """Combine only provider summaries and bounded snippets, never retrieved pages."""
    return ". ".join(part for part in (result.description, *result.snippets) if part)


def _title_name_tokens(value: str) -> tuple[str, ...]:
    last_first_match = _LAST_FIRST_NAME_PATTERN.fullmatch(value.strip(" .:-"))
    if last_first_match is not None:
        return _clean_name_tokens(
            f"{last_first_match.group('first')} {last_first_match.group('last')}"
        )
    return _clean_name_tokens(value)


def _clean_institution_segment(value: str) -> str:
    """Remove an academic-role prefix from a combined role-and-institution title segment."""
    stripped = value.strip(" .,:;-")
    return _ACADEMIC_ROLE_AT_INSTITUTION_PATTERN.sub("", stripped).strip(" .,:;-")


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


def _extract_name(
    result: SearchResult,
    title_segments: tuple[str, ...],
) -> tuple[str | None, SearchResultRejectionCategory | None]:
    """Return a supported person identity or one privacy-safe rejection category."""
    title_name: str | None = None
    title_has_academic_prefix = False
    for segment in title_segments:
        match = _ACADEMIC_PREFIX_PATTERN.match(segment)
        if match is None:
            continue
        tokens = _clean_name_tokens(match.group(2))
        if tokens:
            title_name = f"{match.group(1)} {' '.join(tokens)}"
            title_has_academic_prefix = True
            break

    if title_name is None and title_segments:
        tokens = _title_name_tokens(title_segments[0])
        if tokens:
            title_name = " ".join(tokens)

    context = _result_context(result)
    contextual_names = _contextual_academic_names(context)
    if title_name is not None:
        if title_has_academic_prefix:
            return title_name, None
        normalized_title = _normalized_identity_text(title_name, remove_title=True)
        if any(
            _normalized_identity_text(name, remove_title=True) != normalized_title
            for name in contextual_names
        ):
            return None, SearchResultRejectionCategory.IDENTITY_CONFLICT
        if contextual_names or any(
            _ACADEMIC_ROLE_PATTERN.search(segment) for segment in title_segments[1:]
        ):
            return title_name, None
        if _SINGULAR_PERSON_PROFILE_URL_PATTERN.search(
            str(result.url)
        ) and _UNNAMED_ACADEMIC_ROLE_PATTERN.search(context):
            return title_name, None
        return None, SearchResultRejectionCategory.ACADEMIC_CONTEXT_NOT_ESTABLISHED

    if contextual_names:
        return contextual_names[0], None

    return None, SearchResultRejectionCategory.PERSON_NOT_ESTABLISHED


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


def _extract_institution(
    result: SearchResult,
    title_segments: tuple[str, ...],
    full_name: str,
) -> str | None:
    context = _result_context(result)
    normalized_name = _normalized_identity_text(full_name, remove_title=True)
    for segment in reversed(title_segments):
        institution = _clean_institution_segment(segment)
        if (
            _STRONG_INSTITUTION_PATTERN.search(institution)
            and _has_plausible_institution_suffix(institution)
            and _normalized_identity_text(institution, remove_title=True) != normalized_name
        ):
            return institution

    for segment in reversed(title_segments):
        stripped = _clean_institution_segment(segment)
        if (
            _SCHOOL_PATTERN.search(stripped)
            and _has_plausible_institution_suffix(stripped)
            and not stripped.casefold().startswith("school of ")
            and _normalized_identity_text(stripped, remove_title=True) != normalized_name
        ):
            return stripped

    for segment in reversed(title_segments):
        stripped = _clean_institution_segment(segment)
        if (
            _is_plausible_acronym_institution(stripped)
            or _is_context_supported_two_letter_institution(stripped, context)
        ) and _normalized_identity_text(stripped, remove_title=True) != normalized_name:
            return stripped

    for clause in re.split(r"[.;]", context):
        at_parts = re.split(
            r"\b(?:at|from|with)\s+(?:the\s+)?",
            clause,
            flags=re.IGNORECASE,
        )
        if len(at_parts) < 2:
            continue
        institution = at_parts[-1].strip(" .,:;-")
        institution = re.split(
            r",|\bwhere\b|\bwhose\b|\band\s+(?:researches|studies|publishes|leads|"
            r"focuses|specialises|specializes|teaches)\b",
            institution,
            maxsplit=1,
            flags=re.IGNORECASE,
        )[0].strip()
        if (
            _STRONG_INSTITUTION_PATTERN.search(institution)
            or _SCHOOL_PATTERN.search(institution)
            or _INSTITUTION_ABBREVIATION_PATTERN.fullmatch(institution)
            or _is_context_supported_two_letter_institution(institution, clause)
        ) and _has_plausible_institution_suffix(institution):
            return institution

    for fragment in re.split(r"[.;,|]", context):
        fragment = fragment.strip(" .,:;-")
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


def _extract_department(title_segments: tuple[str, ...], institution: str) -> str:
    normalized_institution = _normalized_identity_text(institution)
    for segment in title_segments:
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
        or _DEPARTMENT_PATTERN.search(context)
        or (
            _PERSON_URL_PATTERN.search(str(result.url))
            and _RESEARCH_CONTEXT_PATTERN.search(context)
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
            full_name, rejection_category = _extract_name(result, title_segments)
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
            institution = _extract_institution(result, title_segments, full_name)
            if institution is None:
                institution_category = (
                    SearchResultRejectionCategory.INCOMPLETE_INSTITUTION
                    if _has_incomplete_institution_fragment(result, title_segments)
                    else SearchResultRejectionCategory.INSTITUTION_NOT_ESTABLISHED
                )
                rejection_counts = rejection_counts.increment(institution_category)
                continue
            department = _extract_department(title_segments, institution)
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
