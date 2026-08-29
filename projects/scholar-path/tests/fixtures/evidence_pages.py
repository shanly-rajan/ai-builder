"""Fixed, invented page-content fixtures for offline evidence-verification tests."""

from datetime import UTC, datetime
from pathlib import Path

from pydantic import HttpUrl

from scholarpath.tools.content_extraction import ExtractedContent

EVIDENCE_PAGE_ROOT = Path(__file__).with_name("evidence")
FIXED_EVIDENCE_RETRIEVED_AT = datetime(2026, 8, 29, 10, 15, tzinfo=UTC)

COMPLETE_PROFILE_URL = "https://profiles.scholarpath.example/supervisor-001"
MISSING_AFFILIATION_URL = "https://research.scholarpath.example/amara-ndlovu"
MISSING_RESEARCH_URL = "https://directory.scholarpath.example/supervisor-001"
ACCEPTING_PROFILE_URL = "https://profiles.scholarpath.example/supervisor-001/availability"
NOT_ACCEPTING_PROFILE_URL = "https://profiles.scholarpath.example/supervisor-001/not-accepting"
CONFLICTING_AFFILIATION_URL = "https://directory.northbridge.ac.example/amara-ndlovu"
ALTERNATE_OFFICIAL_PROFILE_URL = "https://faculty.southerncape.example/amara-ndlovu"


def read_evidence_page(filename: str) -> str:
    """Read one named fixture without permitting traversal outside its directory."""
    if Path(filename).name != filename:
        raise ValueError("Evidence fixture filename must not contain a directory component")
    return (EVIDENCE_PAGE_ROOT / filename).read_text(encoding="utf-8")


def make_extracted_content(
    filename: str,
    source_url: str,
    *,
    retrieved_at: datetime = FIXED_EVIDENCE_RETRIEVED_AT,
) -> ExtractedContent:
    """Bind a fixed page fixture to authoritative extraction provenance."""
    return ExtractedContent(
        source_url=HttpUrl(source_url),
        content=read_evidence_page(filename),
        retrieved_at=retrieved_at,
    )
