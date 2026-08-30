"""Repository contract for retiring outdated M14 submission documents safely."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_BUILDER_ROOT = PROJECT_ROOT.parents[1]
RETIRED_DOCUMENTS = (
    PROJECT_ROOT / "docs/project-submission.md",
    PROJECT_ROOT / "docs/five-minute-demo.md",
)
_MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _assert_relative_links_resolve(document: Path) -> None:
    content = document.read_text(encoding="utf-8")
    for raw_target in _MARKDOWN_LINK_PATTERN.findall(content):
        target = raw_target.split("#", 1)[0]
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        assert (document.parent / target).resolve().exists(), (
            f"Broken relative Markdown link in {document}: {raw_target}"
        )


def test_outdated_submission_documents_remain_retired() -> None:
    for document in RETIRED_DOCUMENTS:
        assert not document.exists(), f"Retired documentation was unexpectedly restored: {document}"


def test_active_readmes_do_not_link_to_retired_documents() -> None:
    root_readme = (AI_BUILDER_ROOT / "README.md").read_text(encoding="utf-8")
    project_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    for retired_name in ("project-submission.md", "five-minute-demo.md"):
        assert retired_name not in root_readme
        assert retired_name not in project_readme


def test_current_reviewer_handoff_documents_and_history_remain_available() -> None:
    required_paths = (
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs/architecture.md",
        PROJECT_ROOT / "docs/reliability-review.md",
        PROJECT_ROOT / "docs/release-checklist.md",
        PROJECT_ROOT / "docs/evaluation-baseline.md",
        PROJECT_ROOT / "docs/prompts/m14-submission-documentation.md",
        PROJECT_ROOT / "docs/build-journal.md",
    )

    for document in required_paths:
        assert document.is_file(), f"Missing current reviewer handoff artifact: {document}"

    root_readme = (AI_BUILDER_ROOT / "README.md").read_text(encoding="utf-8")
    project_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert "Featured project: ScholarPath" in root_readme
    assert "## Reviewer quick path" in project_readme
    assert "## M14: Submission documentation and five-minute recording script" in journal
    assert "(prompts/m14-submission-documentation.md)" in journal


def test_active_reviewer_entry_point_relative_links_resolve() -> None:
    _assert_relative_links_resolve(AI_BUILDER_ROOT / "README.md")
    _assert_relative_links_resolve(PROJECT_ROOT / "README.md")
    _assert_relative_links_resolve(PROJECT_ROOT / "docs/evaluation-baseline.md")
