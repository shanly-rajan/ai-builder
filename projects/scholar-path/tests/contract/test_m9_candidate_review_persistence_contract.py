"""Repository contracts for M9 Candidate review and durable persistence."""

from pathlib import Path

from scholarpath.graph import render_scholarpath_mermaid
from scholarpath.observability import GRAPH_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m9_uses_current_interrupt_resume_and_patched_sqlite_checkpoint_package() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    workflow = (PROJECT_ROOT / "src" / "graph" / "workflow.py").read_text(encoding="utf-8")
    persistence = (PROJECT_ROOT / "src" / "graph" / "persistence.py").read_text(encoding="utf-8")

    assert '"langgraph-checkpoint-sqlite==3.1.1"' in pyproject
    assert "from langgraph.types import Command, interrupt" in workflow
    assert "raw_response = interrupt(" in workflow
    assert "Command(resume=resume_value)" in workflow
    assert "candidate_review_gate_stub" not in workflow
    assert "InMemorySaver" in persistence
    assert "SqliteSaver" in persistence
    assert "allowed_msgpack_modules=" in persistence
    assert "pickle_fallback=True" not in persistence


def test_m9_local_checkpoint_path_is_configured_and_ignored() -> None:
    environment_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    gitignore = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    config_source = (PROJECT_ROOT / "src" / "config.py").read_text(encoding="utf-8")

    assert (
        "SCHOLARPATH_CHECKPOINT_DATABASE_PATH=.scholarpath/checkpoints.sqlite3"
        in environment_example
    )
    assert ".scholarpath/" in gitignore
    assert 'Path(".scholarpath/checkpoints.sqlite3")' in config_source


def test_m9_prompt_diagram_tests_and_journal_are_recorded() -> None:
    prompt_name = "m9-candidate-review-interrupt-and-persistence.md"
    prompt = PROJECT_ROOT / "docs" / "prompts" / prompt_name
    diagram = PROJECT_ROOT / "docs" / "m9-candidate-review-persistence-graph.mmd"
    journal = (PROJECT_ROOT / "docs" / "build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert diagram.is_file()
    assert prompt_name in journal
    assert "CandidateReviewInterruptPayload" in journal
    assert (PROJECT_ROOT / "tests" / "graph" / "test_m9_candidate_review_interrupt.py").is_file()
    assert (PROJECT_ROOT / "tests" / "integration" / "test_m9_sqlite_persistence.py").is_file()


def test_m9_mermaid_is_the_current_generated_graph_snapshot() -> None:
    saved = (PROJECT_ROOT / "docs" / "m9-candidate-review-persistence-graph.mmd").read_text(
        encoding="utf-8"
    )

    assert saved.strip() == render_scholarpath_mermaid().strip()
    assert "candidate_review_gate" in saved
    assert "candidate_review_gate_stub" not in saved


def test_m9_updates_trace_version_without_adding_mem0_or_outreach() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8").casefold()
    graph_source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "src" / "graph").glob("*.py"))
    ).casefold()

    assert GRAPH_VERSION == "m9"
    assert '"mem0' not in pyproject
    assert "outreach" not in graph_source
