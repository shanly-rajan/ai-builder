"""Parser to convert raw MCC Laws text into structured LangChain Documents."""

from __future__ import annotations

import re
from pathlib import Path

from langchain_core.documents import Document


def parse_mcc_laws(file_path: Path | str) -> list[Document]:
    """Parse text file and split along Law/clause boundaries."""
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Law file not found at: {path}")

    raw_text = path.read_text(encoding="utf-8")

    # Split on Law headers (e.g., "LAW 38 RUN OUT") or section numbers (e.g., "38.1 Out")
    law_blocks = re.split(r"\n(?=LAW \d+|Law \d+|\d+\.\d+ )", raw_text)
    documents: list[Document] = []

    current_law_num = "General"
    current_law_title = "Preamble / General"

    for block in law_blocks:
        cleaned = block.strip()
        if not cleaned:
            continue

        law_match = re.match(r"(?:LAW|Law)\s+(\d+)\s+([^\n]+)", cleaned, re.IGNORECASE)
        section_match = re.match(r"(\d+)\.(\d+)\s+([^\n]+)", cleaned)

        if law_match:
            current_law_num = law_match.group(1)
            current_law_title = law_match.group(2).strip()

        section_title = (
            section_match.group(0).strip() if section_match else f"Law {current_law_num}"
        )

        metadata = {
            "law_number": str(current_law_num),
            "law_title": current_law_title,
            "section": section_title,
            "source": "MCC Laws of Cricket",
        }

        documents.append(Document(page_content=cleaned, metadata=metadata))

    return documents
