"""Opt-in private excerpt capture and deterministic, excerpt-only local replay.

These artifacts are deliberately separate from traces and aggregate canary reports.
Replay checks the profile excerpt helper only; it cannot establish full grounding.
"""

from __future__ import annotations

import os
import re
import stat
from pathlib import Path
from typing import Literal, Self, cast
from urllib.parse import unquote, urlsplit
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from scholarpath.domain import models as domain_models
from scholarpath.domain.enums import EvidenceClaimType, GroundingFailureReason, SourceKind
from scholarpath.domain.models import EvidenceClaim

CaptureOrigin = Literal["live_canary", "synthetic_fixture"]
CapturedClaimType = Literal[
    EvidenceClaimType.CURRENT_AFFILIATION, EvidenceClaimType.RESEARCH_INTEREST
]
CapturedReason = Literal[
    GroundingFailureReason.CONTEXT_CONFLICTING_PERSON,
    GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
]
CapturedSourceKind = Literal[SourceKind.UNIVERSITY_PROFILE, SourceKind.INSTITUTIONAL_DIRECTORY]
_CLAIM_TYPES = frozenset(
    {EvidenceClaimType.CURRENT_AFFILIATION, EvidenceClaimType.RESEARCH_INTEREST}
)
_REASONS = frozenset(
    {
        GroundingFailureReason.CONTEXT_CONFLICTING_PERSON,
        GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
    }
)
_MAX_FILE_BYTES = 16 * 1024
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)
_NONBLOCK = getattr(os, "O_NONBLOCK", 0)
_DIRECTORY_FLAGS = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | _NOFOLLOW
_SENSITIVE_TEXT = re.compile(
    r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|"
    r"\b(?:sk-|sk_|tvly-|tvly_|tavily-|lsv2_|ls__|gh[pousr]_|github_pat_|xox[baprs]-|hf_|gsk_)"
    r"[A-Za-z0-9_-]+|\bAKIA[A-Z0-9]{16}\b|"
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]+|"
    r"\bBearer\s+\S+|"
    r"-----BEGIN[ \t]+(?:[A-Z0-9]+[ \t]+)*PRIVATE[ \t]+KEY-----|"
    r"\b(?:[A-Za-z][A-Za-z0-9_-]*[_-])?"
    r"(?:api[_ -]?key|access[_ -]?token|token|secret|password|authorization|private[_ -]?key)"
    r"[\"'`]?\s*[:=]\s*\S+",
    re.IGNORECASE,
)


class PrivateReplayError(ValueError):
    """A fixed-message failure that never includes private input or filesystem paths."""


class _ReplayModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, hide_input_in_errors=True)


class RejectedExcerptSample(_ReplayModel):
    """The exact minimal excerpt inputs, with private fields hidden in repr."""

    claim_type: CapturedClaimType
    expected_name: str = Field(min_length=1, max_length=200, repr=False)
    asserted_name: str = Field(min_length=1, max_length=200, repr=False)
    supporting_excerpt: str = Field(min_length=1, max_length=1200, repr=False)
    source_url: str = Field(min_length=1, max_length=2048, repr=False)
    source_kind: CapturedSourceKind
    observed_reason: CapturedReason

    @field_validator("expected_name", "asserted_name", "supporting_excerpt", "source_url")
    @classmethod
    def private_text_must_be_eligible(cls, value: str) -> str:
        if not value.strip() or _SENSITIVE_TEXT.search(unquote(value)):
            raise ValueError("Private replay text is not eligible")
        return value

    @field_validator("source_url")
    @classmethod
    def source_url_must_be_clean_https(cls, value: str) -> str:
        try:
            parsed = urlsplit(value)
            eligible = (
                parsed.scheme == "https"
                and bool(parsed.hostname)
                and parsed.username is None
                and parsed.password is None
                and not parsed.query
                and not parsed.fragment
                and "?" not in value
                and "#" not in value
                and not any(character.isspace() for character in value)
            )
            _ = parsed.port
        except ValueError:
            eligible = False
        if not eligible:
            raise ValueError("Private replay source URL is not eligible")
        return value


class GroundingReplaySnapshot(_ReplayModel):
    schema_version: Literal[1] = 1
    origin: CaptureOrigin = "synthetic_fixture"
    samples: tuple[RejectedExcerptSample, ...] = Field(default=(), max_length=2, repr=False)
    excluded_count: int = Field(default=0, strict=True, ge=0)

    @model_validator(mode="after")
    def sample_types_must_be_unique(self) -> Self:
        if len({sample.claim_type for sample in self.samples}) != len(self.samples):
            raise ValueError("Private replay sample types must be unique")
        return self


class RejectedExcerptCapture:
    """Bounded in-memory observer; construction and observation perform no IO."""

    def __init__(self, *, origin: CaptureOrigin = "synthetic_fixture") -> None:
        self._snapshot = GroundingReplaySnapshot(origin=origin)

    def snapshot(self) -> GroundingReplaySnapshot:
        return self._snapshot

    def observe(
        self, *, expected_name: str, claim: EvidenceClaim, failure: GroundingFailureReason
    ) -> None:
        if claim.claim_type not in _CLAIM_TYPES or failure not in _REASONS:
            return
        if any(sample.claim_type == claim.claim_type for sample in self._snapshot.samples):
            return
        try:
            sample = RejectedExcerptSample(
                claim_type=cast(CapturedClaimType, claim.claim_type),
                expected_name=expected_name,
                asserted_name=claim.asserted_name or "",
                supporting_excerpt=claim.supporting_excerpt or "",
                source_url=str(claim.source_url),
                source_kind=cast(CapturedSourceKind, claim.source_kind),
                observed_reason=cast(CapturedReason, failure),
            )
            updated = self._snapshot.model_copy(
                update={"samples": (*self._snapshot.samples, sample)}
            )
            if len(updated.model_dump_json(indent=2).encode("utf-8")) > _MAX_FILE_BYTES:
                raise ValueError("Private replay size limit exceeded")
        except (ValidationError, ValueError):
            self._snapshot = self._snapshot.model_copy(
                update={"excluded_count": self._snapshot.excluded_count + 1}
            )
            return
        self._snapshot = updated


class GroundingReplaySummary(_ReplayModel):
    sample_count: int
    matched_count: int
    changed_count: int
    excluded_count: int


def replay_snapshot(snapshot: GroundingReplaySnapshot) -> GroundingReplaySummary:
    """Return counts only; equality concerns the excerpt helper, not full verification."""
    matched = sum(
        domain_models.profile_context_excerpt_failure(
            sample.claim_type, sample.asserted_name, sample.supporting_excerpt
        )
        == sample.observed_reason
        for sample in snapshot.samples
    )
    return GroundingReplaySummary(
        sample_count=len(snapshot.samples),
        matched_count=matched,
        changed_count=len(snapshot.samples) - matched,
        excluded_count=snapshot.excluded_count,
    )


class GroundingReplayDetail(_ReplayModel):
    """Private, derived diagnostics; never add these fields to aggregate reports."""

    claim_type: CapturedClaimType
    observed_reason: CapturedReason
    current_reason: GroundingFailureReason | None
    matcher_family: str | None
    matched_text: str | None = Field(repr=False)
    normalized_prefix: str = Field(max_length=160, repr=False)
    wrapper_removed: bool
    prefix_recognized: bool


def replay_details(snapshot: GroundingReplaySnapshot) -> tuple[GroundingReplayDetail, ...]:
    """Inspect the current domain matchers locally, without copying or changing rules."""
    details: list[GroundingReplayDetail] = []
    for sample in snapshot.samples:
        excerpt = sample.supporting_excerpt
        if sample.claim_type is EvidenceClaimType.RESEARCH_INTEREST:
            excerpt = domain_models._RESEARCH_OVERVIEW_WRAPPER_PATTERN.sub("", excerpt, count=1)
        family = None
        matched_text = None
        for match in domain_models._titled_person_matches(excerpt):
            if not domain_models.supervisor_names_are_title_equivalent(
                match.group(0), sample.asserted_name
            ):
                family, matched_text = "titled_person", match.group(0)
                break
        if family is None:
            for index, pattern in enumerate(domain_models._UNTITLED_CONTEXT_PERSON_PATTERNS):
                untitled_match = pattern.search(excerpt)
                if (
                    untitled_match is not None
                    and not domain_models.supervisor_names_are_title_equivalent(
                        untitled_match.group(1), sample.asserted_name
                    )
                ):
                    family, matched_text = f"untitled_context_{index}", untitled_match.group(1)
                    break
        normalized = domain_models._normalized_profile_excerpt(excerpt)
        details.append(
            GroundingReplayDetail(
                claim_type=sample.claim_type,
                observed_reason=sample.observed_reason,
                current_reason=domain_models.profile_context_excerpt_failure(
                    sample.claim_type, sample.asserted_name, sample.supporting_excerpt
                ),
                matcher_family=family,
                matched_text=matched_text,
                normalized_prefix=normalized[:160],
                wrapper_removed=excerpt != sample.supporting_excerpt,
                prefix_recognized=(
                    domain_models._PROFILE_CONTEXT_SUBJECT_PATTERN.match(normalized) is not None
                    or normalized.startswith(
                        domain_models._PROFILE_SECTION_PREFIXES.get(sample.claim_type, ())
                    )
                    or (
                        sample.claim_type is EvidenceClaimType.RESEARCH_INTEREST
                        and domain_models._named_academic_specialisation_prefix(
                            normalized, sample.asserted_name
                        )
                    )
                ),
            )
        )
    return tuple(details)


def _open_directory_path(path: Path) -> int:
    """Walk each component with no-follow semantics, including ancestor directories."""
    if not _NOFOLLOW or not getattr(os, "O_DIRECTORY", 0) or not _NONBLOCK:
        raise PrivateReplayError("Secure private replay IO is unavailable")
    path = path.absolute()
    descriptor = os.open(path.anchor, _DIRECTORY_FLAGS)
    try:
        for component in path.parts[1:]:
            if component == "..":
                raise ValueError("Private replay path is not eligible")
            child = os.open(component, _DIRECTORY_FLAGS, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        return descriptor
    except (OSError, ValueError):
        os.close(descriptor)
        raise


def _private_child_directory(parent: int, name: str) -> int:
    try:
        os.mkdir(name, mode=0o700, dir_fd=parent)
        created = True
    except FileExistsError:
        created = False
    descriptor = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent)
    try:
        if created or name == "grounding-replays":
            os.fchmod(descriptor, 0o700)
    except OSError:
        os.close(descriptor)
        raise
    return descriptor


def write_private_replay(capture: RejectedExcerptCapture, project_root: Path) -> Path | None:
    """Write one new private artifact only at the fixed, ignored project location."""
    snapshot = capture.snapshot()
    if not snapshot.samples:
        return None
    descriptors: list[int] = []
    try:
        snapshot = GroundingReplaySnapshot.model_validate(snapshot.model_dump(warnings=False))
        payload = snapshot.model_dump_json(indent=2).encode("utf-8")
        if len(payload) > _MAX_FILE_BYTES:
            raise ValueError("Private replay size limit exceeded")
        descriptors.append(_open_directory_path(project_root))
        for name in ("artifacts", "grounding-replays"):
            descriptors.append(_private_child_directory(descriptors[-1], name))
        filename = f"{uuid4()}.json"
        descriptor = os.open(
            filename,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | _NOFOLLOW,
            0o600,
            dir_fd=descriptors[-1],
        )
        with os.fdopen(descriptor, "wb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(payload)
        return project_root / "artifacts" / "grounding-replays" / filename
    except (OSError, ValueError):
        raise PrivateReplayError("Private replay could not be written") from None
    finally:
        for descriptor in reversed(descriptors):
            os.close(descriptor)


def read_private_replay(path: Path) -> GroundingReplaySnapshot:
    """Load at most 16 KiB from a regular, non-symlink file; failures hide all input."""
    parent_descriptor: int | None = None
    try:
        parent_descriptor = _open_directory_path(path.parent)
        descriptor = os.open(
            path.name, os.O_RDONLY | _NOFOLLOW | _NONBLOCK, dir_fd=parent_descriptor
        )
        with os.fdopen(descriptor, "rb") as stream:
            metadata = os.fstat(stream.fileno())
            if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > _MAX_FILE_BYTES:
                raise ValueError("Private replay file is not eligible")
            payload = stream.read(_MAX_FILE_BYTES + 1)
            if len(payload) > _MAX_FILE_BYTES:
                raise ValueError("Private replay size limit exceeded")
        return GroundingReplaySnapshot.model_validate_json(payload)
    except (OSError, ValueError):
        raise PrivateReplayError("Private replay could not be read") from None
    finally:
        if parent_descriptor is not None:
            os.close(parent_descriptor)
