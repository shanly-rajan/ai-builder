"""Unit tests for the cricket-law document parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingestion.parser import parse_mcc_laws

SYNTHETIC_LAWS = """LAW 1 FICTIONAL EQUIPMENT
1.1 Training marker
The blue marker is used only in this synthetic fixture.
1.2 Spare marker
The green marker remains beside the practice field.

LAW 2 FICTIONAL INTERVALS
2.1 Practice break
The fictional practice break lasts three minutes.
"""


def test_parser_creates_provenance_bearing_documents(tmp_path: Path) -> None:
    fixture = tmp_path / "synthetic-laws.txt"
    fixture.write_text(SYNTHETIC_LAWS, encoding="utf-8")

    documents = parse_mcc_laws(fixture)

    assert len(documents) == 5
    assert documents[0].metadata["law_number"] == "1"
    assert documents[1].metadata["section"].startswith("1.1")
    assert documents[-1].metadata == {
        "law_number": "2",
        "law_title": "FICTIONAL INTERVALS",
        "section": "2.1 Practice break",
        "source": "MCC Laws of Cricket",
    }


def test_parser_rejects_a_missing_source(tmp_path: Path) -> None:
    missing = tmp_path / "missing.txt"

    with pytest.raises(FileNotFoundError, match="Law file not found"):
        parse_mcc_laws(missing)
