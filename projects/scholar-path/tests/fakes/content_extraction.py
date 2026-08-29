"""Recording, scripted fake for the provider-neutral content-extraction port."""

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pydantic import HttpUrl

from scholarpath.graph.fixtures import build_walking_skeleton_fixtures
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fixtures.evidence_pages import (
    ACCEPTING_PROFILE_URL,
    ALTERNATE_OFFICIAL_PROFILE_URL,
    COMPLETE_PROFILE_URL,
    CONFLICTING_AFFILIATION_URL,
    MISSING_AFFILIATION_URL,
    MISSING_RESEARCH_URL,
    NOT_ACCEPTING_PROFILE_URL,
    make_extracted_content,
)

type ContentExtractionOutcome = ExtractedContent | Exception


def make_fixed_content_outcomes() -> dict[str, ExtractedContent]:
    """Return every fixed M6 page mapped to its invented reserved URL."""
    return {
        COMPLETE_PROFILE_URL: make_extracted_content(
            "complete_official_profile.md", COMPLETE_PROFILE_URL
        ),
        MISSING_AFFILIATION_URL: make_extracted_content(
            "missing_affiliation.md", MISSING_AFFILIATION_URL
        ),
        MISSING_RESEARCH_URL: make_extracted_content("missing_research.md", MISSING_RESEARCH_URL),
        ACCEPTING_PROFILE_URL: make_extracted_content(
            "accepting_doctoral_candidates.html", ACCEPTING_PROFILE_URL
        ),
        NOT_ACCEPTING_PROFILE_URL: make_extracted_content(
            "not_accepting_doctoral_candidates.md", NOT_ACCEPTING_PROFILE_URL
        ),
        CONFLICTING_AFFILIATION_URL: make_extracted_content(
            "conflicting_affiliation_directory.md", CONFLICTING_AFFILIATION_URL
        ),
        ALTERNATE_OFFICIAL_PROFILE_URL: make_extracted_content(
            "alternate_official_profile.md", ALTERNATE_OFFICIAL_PROFILE_URL
        ),
    }


def make_graph_content_outcomes() -> dict[str, ExtractedContent]:
    """Return complete invented profile pages for the walking-skeleton cohort."""
    retrieved_at = datetime(2026, 8, 29, 10, 30, tzinfo=UTC)
    outcomes: dict[str, ExtractedContent] = {}
    for raw in build_walking_skeleton_fixtures().raw_search_results:
        content = "\n".join(
            (
                raw.full_name,
                (f"{raw.full_name} is Professor in {raw.department} at {raw.institution}."),
                (
                    f"{raw.full_name}'s current research interests include enterprise "
                    "architecture, "
                    "responsible AI governance, and resilient digital transformation."
                ),
                (
                    f"{raw.full_name} authored a 2025 publication examining architecture "
                    "controls for responsible AI adoption."
                ),
            )
        )
        outcomes[str(raw.profile_url)] = ExtractedContent.model_validate(
            {
                "source_url": raw.profile_url,
                "content": content,
                "retrieved_at": retrieved_at,
            }
        )
    return outcomes


class FakeContentExtraction:
    """Return fixed or scripted content and record every exact requested URL."""

    def __init__(
        self,
        outcomes: Mapping[str, ContentExtractionOutcome] | None = None,
        *,
        scripts: Mapping[str, Sequence[ContentExtractionOutcome]] | None = None,
    ) -> None:
        default_outcomes = {**make_fixed_content_outcomes(), **make_graph_content_outcomes()}
        self._outcomes = dict(default_outcomes if outcomes is None else outcomes)
        self._scripts = {url: list(items) for url, items in (scripts or {}).items()}
        self.calls: list[str] = []

    def extract(self, source_url: str | HttpUrl) -> ExtractedContent:
        """Record the URL, then return or raise its deterministic outcome."""
        normalized_url = str(source_url)
        self.calls.append(normalized_url)
        scripted = self._scripts.get(normalized_url)
        outcome = scripted.pop(0) if scripted else self._outcomes.get(normalized_url)
        if outcome is None:
            raise AssertionError(f"No fake content-extraction outcome for {normalized_url}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
