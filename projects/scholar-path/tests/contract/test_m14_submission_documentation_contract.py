"""Repository contract for the M14 submission documentation."""

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
AI_BUILDER_ROOT = PROJECT_ROOT.parents[1]
_WORD_PATTERN = re.compile(r"\b[\w'-]+\b")
_TIMING_PATTERN = re.compile(r"^### (?P<start>\d:\d{2})–(?P<end>\d:\d{2})", re.MULTILINE)
_MARKDOWN_LINK_PATTERN = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def _seconds(timestamp: str) -> int:
    minutes, seconds = (int(part) for part in timestamp.split(":"))
    return minutes * 60 + seconds


def _spoken_text(section: str) -> str:
    return " ".join(
        line.removeprefix("> ") for line in section.splitlines() if line.startswith("> ")
    )


def _assert_relative_links_resolve(document: Path) -> None:
    content = document.read_text(encoding="utf-8")
    for raw_target in _MARKDOWN_LINK_PATTERN.findall(content):
        target = raw_target.split("#", 1)[0]
        if not target or target.startswith(("#", "http://", "https://", "mailto:")):
            continue
        assert (document.parent / target).resolve().exists(), (
            f"Broken relative Markdown link in {document}: {raw_target}"
        )


def test_submission_readmes_writeup_script_prompt_and_journal_are_complete() -> None:
    root_readme = (AI_BUILDER_ROOT / "README.md").read_text(encoding="utf-8")
    project_readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    submission = (PROJECT_ROOT / "docs/project-submission.md").read_text(encoding="utf-8")
    demo = (PROJECT_ROOT / "docs/five-minute-demo.md").read_text(encoding="utf-8")
    baseline = (PROJECT_ROOT / "docs/evaluation-baseline.md").read_text(encoding="utf-8")
    prompt_name = "m14-submission-documentation.md"
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert "Featured project: ScholarPath" in root_readme
    assert "multi-agent doctoral supervisor" not in root_readme.lower()
    assert "projects/scholar-path/docs/project-submission.md" in root_readme
    assert "projects/scholar-path/docs/five-minute-demo.md" in root_readme

    assert "## Reviewer quick path" in project_readme
    assert "1,579 non-live tests passed" in project_readme
    assert "product latency and Candidate-relevance target" in project_readme
    assert "it is not presented as achieved" in project_readme
    assert "Gate -->|valid explicit action| Memory" in project_readme
    assert "Memory -->|approve exact IDs| Shortlist" in project_readme

    framework_fields = (
        "Agent goal",
        "Where do people use it?",
        "What steps does it take, in order?",
        "What can it actually do?",
        "What does it need to remember?",
        "What should it never do?",
        "Human-in-the-loop",
        "What happens when something breaks?",
        "How do you know it worked?",
    )
    for field in framework_fields:
        assert f"**{field}**" in submission
    for required_section in (
        "## Datasets and sources used",
        "## AI-assisted engineering approach",
        "## Prompts used during AI-assisted coding",
        "## Major iterations and tuning",
        "## Testing, evaluation, and observed results",
        "## Lessons learned and workflow observations",
    ):
        assert required_section in submission
    for integration in ("OpenAI", "You.com", "Tavily", "Nebius", "Mem0", "LangSmith"):
        assert integration in submission
    assert "product target" in submission.lower()
    assert "not yet claimed as achieved" in submission
    assert "Gate -->|valid explicit action| Learn" in submission
    assert "Learn -->|approve exact IDs| Save" in submission

    expected_timings = (
        "0:00–0:30",
        "0:30–1:10",
        "1:10–1:50",
        "1:50–2:25",
        "2:25–3:05",
        "3:05–3:55",
        "3:55–4:25",
        "4:25–5:00",
    )
    for timing in expected_timings:
        assert timing in demo
    spoken_section = demo.split("## Read-aloud recording script", 1)[1].split(
        "## Operator appendix",
        1,
    )[0]
    spoken_text = _spoken_text(spoken_section)
    spoken_word_count = len(_WORD_PATTERN.findall(spoken_text))
    assert 430 <= spoken_word_count <= 520
    assert "1,579 passing non-live tests" in spoken_text
    assert "requiring calibrated live-user evaluation" in spoken_text
    timing_matches = list(_TIMING_PATTERN.finditer(spoken_section))
    assert len(timing_matches) == len(expected_timings)
    for index, match in enumerate(timing_matches):
        section_end = (
            timing_matches[index + 1].start()
            if index + 1 < len(timing_matches)
            else len(spoken_section)
        )
        section_words = len(
            _WORD_PATTERN.findall(_spoken_text(spoken_section[match.end() : section_end]))
        )
        duration_seconds = _seconds(match.group("end")) - _seconds(match.group("start"))
        words_per_minute = section_words / duration_seconds * 60
        assert words_per_minute <= 120

    for document_text in (project_readme, submission, demo, baseline, journal):
        assert "1579" in document_text.replace(",", "")
    assert "212 Python files formatted" in baseline
    assert "205 source files" in baseline
    assert "205 source files" in submission
    assert "`212 files already formatted`" in journal
    assert "`205 source files`" in journal

    for document in (
        AI_BUILDER_ROOT / "README.md",
        PROJECT_ROOT / "README.md",
        PROJECT_ROOT / "docs/project-submission.md",
        PROJECT_ROOT / "docs/five-minute-demo.md",
        PROJECT_ROOT / "docs/evaluation-baseline.md",
    ):
        _assert_relative_links_resolve(document)

    assert (PROJECT_ROOT / f"docs/prompts/{prompt_name}").is_file()
    assert f"(prompts/{prompt_name})" in journal
