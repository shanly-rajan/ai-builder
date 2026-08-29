"""Deterministic extraction and deduplication for Prospective Supervisors."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from pydantic import BaseModel, ConfigDict, ValidationError

from ..domain import (
    ProspectiveSupervisor,
    SearchPlan,
    SearchResult,
    SupervisorDiscoveryProvenance,
)

_TITLE_SPLIT_PATTERN = re.compile(r"\s*(?:\||—|–|\s-\s)\s*")
_ACADEMIC_PREFIX_PATTERN = re.compile(
    r"^(Associate Professor|Assistant Professor|Professor|Prof\.?|Dr\.?)\s+(.+)$",
    re.IGNORECASE,
)
_ACADEMIC_PREFIX_SEARCH_PATTERN = re.compile(
    r"\b(Associate Professor|Assistant Professor|Professor|Prof\.?|Dr\.?)\s+"
    r"([^,;|—–]+)",
    re.IGNORECASE,
)
_ACADEMIC_ROLE_PATTERN = re.compile(
    r"\b(professor|lecturer|researcher|research fellow|faculty member|academic|reader)\b",
    re.IGNORECASE,
)
_STRONG_INSTITUTION_PATTERN = re.compile(
    r"\b(university|institute|college|polytechnic|academy)\b", re.IGNORECASE
)
_SCHOOL_PATTERN = re.compile(r"\bschool\b", re.IGNORECASE)
_INSTITUTION_ABBREVIATION_PATTERN = re.compile(r"^[A-Z][A-Z.&-]{1,11}$")
_DEPARTMENT_PATTERN = re.compile(
    r"\b(department of|faculty of|school of|centre for|center for)\b", re.IGNORECASE
)
_PERSON_URL_PATTERN = re.compile(
    r"/(people|person|profiles?|staff|faculty|researchers?)(?:/|$)", re.IGNORECASE
)
_TRACKING_QUERY_KEYS = {"fbclid", "gclid", "mc_cid", "mc_eid"}
_NAME_PARTICLES = {"al", "da", "de", "del", "di", "la", "le", "van", "von"}
_NAME_STOP_WORDS = {
    "academic",
    "academy",
    "and",
    "at",
    "center",
    "centre",
    "college",
    "department",
    "faculty",
    "from",
    "group",
    "institute",
    "is",
    "lab",
    "laboratory",
    "lecturer",
    "polytechnic",
    "professor",
    "research",
    "researcher",
    "school",
    "university",
}


class SupervisorDiscoveryResult(BaseModel):
    """Structured discovery output containing only Prospective Supervisors."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        str_strip_whitespace=True,
        validate_default=True,
    )

    prospective_supervisors: tuple[ProspectiveSupervisor, ...] = ()


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


def _extract_name(result: SearchResult, title_segments: tuple[str, ...]) -> str | None:
    for segment in title_segments:
        match = _ACADEMIC_PREFIX_PATTERN.match(segment)
        if match is None:
            continue
        tokens = _clean_name_tokens(match.group(2))
        if tokens:
            return f"{match.group(1)} {' '.join(tokens)}"

    description_match = _ACADEMIC_PREFIX_SEARCH_PATTERN.search(result.description)
    if description_match is not None:
        tokens = _clean_name_tokens(description_match.group(2))
        if tokens:
            return f"{description_match.group(1)} {' '.join(tokens)}"

    if (
        title_segments
        and _ACADEMIC_ROLE_PATTERN.search(result.description)
        and _PERSON_URL_PATTERN.search(str(result.url))
    ):
        tokens = _clean_name_tokens(title_segments[0])
        if tokens:
            return " ".join(tokens)
    return None


def _extract_institution(
    result: SearchResult,
    title_segments: tuple[str, ...],
    full_name: str,
) -> str | None:
    normalized_name = _normalized_identity_text(full_name, remove_title=True)
    for segment in reversed(title_segments):
        if _STRONG_INSTITUTION_PATTERN.search(segment) and (
            _normalized_identity_text(segment, remove_title=True) != normalized_name
        ):
            return segment.strip(" .,:;-")

    for segment in reversed(title_segments):
        stripped = segment.strip(" .,:;-")
        if (
            _SCHOOL_PATTERN.search(stripped)
            and not stripped.casefold().startswith("school of ")
            and _normalized_identity_text(stripped, remove_title=True) != normalized_name
        ):
            return stripped

    for clause in re.split(r"[.;]", result.description):
        at_parts = re.split(
            r"\b(?:at|from|with)\s+(?:the\s+)?",
            clause,
            flags=re.IGNORECASE,
        )
        if len(at_parts) < 2:
            continue
        institution = at_parts[-1].strip(" .,:;-")
        institution = re.split(r",|\bwhere\b|\bwhose\b", institution, maxsplit=1)[0].strip()
        if (
            _STRONG_INSTITUTION_PATTERN.search(institution)
            or _SCHOOL_PATTERN.search(institution)
            or _INSTITUTION_ABBREVIATION_PATTERN.fullmatch(institution)
        ):
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
    context = " ".join((*title_segments, result.description))
    return bool(
        _ACADEMIC_ROLE_PATTERN.search(context)
        or _DEPARTMENT_PATTERN.search(context)
        or _PERSON_URL_PATTERN.search(str(result.url))
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
        prospective: list[ProspectiveSupervisor] = []
        for result in search_results:
            if result.originating_query not in planned_queries:
                raise ValueError("SearchResult originating query is not present in SearchPlan")
            title_segments = tuple(
                segment.strip()
                for segment in _TITLE_SPLIT_PATTERN.split(result.title)
                if segment.strip()
            )
            full_name = _extract_name(result, title_segments)
            if full_name is None:
                continue
            if full_name.casefold().startswith(("dr ", "dr. ")) and not _has_academic_context(
                result,
                title_segments,
            ):
                continue
            institution = _extract_institution(result, title_segments, full_name)
            if institution is None:
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
        return SupervisorDiscoveryResult(
            prospective_supervisors=deduplicate_prospective_supervisors(prospective)
        )
