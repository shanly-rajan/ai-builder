"""Deterministic checks for canonical Candidate and Supervisor terminology."""

import re
from collections.abc import Iterable
from pathlib import Path

import pytest

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
DOCS_ROOT = PROJECT_ROOT / "docs"
PROMPT_ARCHIVE = DOCS_ROOT / "prompts"

BANNED_PATTERNS = (
    re.compile(r"\bsupervisor[\s_-]+candidates?\b", re.IGNORECASE),
    re.compile(r"\bapproved[\s_-]+candidates?\b", re.IGNORECASE),
)


def authored_product_files() -> tuple[Path, ...]:
    """Return source and authored documentation, excluding verbatim prompt records."""
    source_files = tuple(SOURCE_ROOT.rglob("*.py")) + tuple(SOURCE_ROOT.rglob("*.pyi"))
    documentation_files = tuple(
        path for path in DOCS_ROOT.rglob("*.md") if PROMPT_ARCHIVE not in path.parents
    )
    return tuple(sorted((*source_files, *documentation_files, PROJECT_ROOT / "README.md")))


def find_banned_terminology(paths: Iterable[Path]) -> list[str]:
    """Report ambiguous terminology with its exact path and line number."""
    violations: list[str] = []
    for path in paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for pattern in BANNED_PATTERNS:
                if match := pattern.search(line):
                    violations.append(f"{path}:{line_number}: {match.group(0)}")
    return violations


def test_authored_source_and_documentation_use_canonical_terminology() -> None:
    files = authored_product_files()

    assert SOURCE_ROOT.is_dir()
    assert DOCS_ROOT.is_dir()
    assert files, "Terminology scan must inspect at least one authored file"
    assert find_banned_terminology(files) == []


@pytest.mark.parametrize("relative_path", ["src/example.py", "docs/example.md"])
@pytest.mark.parametrize(
    "bad_text",
    ["supervisor candidate", "Supervisor-Candidates", "approved_candidate"],
)
def test_scanner_detects_banned_terminology_variants(
    tmp_path: Path, relative_path: str, bad_text: str
) -> None:
    target = tmp_path / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(bad_text, encoding="utf-8")

    violations = find_banned_terminology([target])

    assert len(violations) == 1
    assert bad_text in violations[0]


def test_scanner_allows_canonical_role_language(tmp_path: Path) -> None:
    target = tmp_path / "docs" / "terminology.md"
    target.parent.mkdir(parents=True)
    target.write_text(
        "The Candidate approved the Verified Supervisor for the shortlist.",
        encoding="utf-8",
    )

    assert find_banned_terminology([target]) == []
