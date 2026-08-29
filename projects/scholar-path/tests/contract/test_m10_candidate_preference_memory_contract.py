"""Repository contract for M10 persistent Candidate preference memory."""

from pathlib import Path

from scholarpath.graph import CANONICAL_NODE_NAMES, render_scholarpath_mermaid
from scholarpath.memory import CandidateMemoryRecord, CandidatePreferenceMemoryPort
from scholarpath.observability import GRAPH_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m10_dependency_and_typed_memory_boundary_are_present() -> None:
    pyproject = (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    memory_source = (PROJECT_ROOT / "src" / "memory" / "mem0_adapter.py").read_text(
        encoding="utf-8"
    )

    assert '"mem0ai==2.0.19"' in pyproject
    assert CandidatePreferenceMemoryPort is not None
    assert CandidateMemoryRecord is not None
    assert "infer=False" in memory_source
    assert 'filters={"user_id": scoped_candidate_id}' in memory_source


def test_m10_prompt_diagram_tests_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs" / "prompts" / "m10-persistent-candidate-preference-memory.md"
    diagram = PROJECT_ROOT / "docs" / "m10-candidate-preference-memory-graph.mmd"
    journal = (PROJECT_ROOT / "docs" / "build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert diagram.is_file()
    assert "Milestone M10" in prompt.read_text(encoding="utf-8")
    assert "## Milestone M10" in journal
    assert (PROJECT_ROOT / "tests" / "graph" / "test_m10_candidate_preference_memory.py").is_file()
    assert (PROJECT_ROOT / "tests" / "integration" / "test_mem0_memory_live.py").is_file()


def test_m10_mermaid_is_the_current_generated_graph_snapshot() -> None:
    saved = (PROJECT_ROOT / "docs" / "m10-candidate-preference-memory-graph.mmd").read_text(
        encoding="utf-8"
    )

    assert saved == render_scholarpath_mermaid()
    assert "learn_candidate_preferences" in CANONICAL_NODE_NAMES


def test_m10_updates_trace_version_without_adding_outreach() -> None:
    source_files = tuple((PROJECT_ROOT / "src").rglob("*.py"))
    source = "\n".join(path.read_text(encoding="utf-8") for path in source_files)

    major_version = int(GRAPH_VERSION.removeprefix("m").split(".", maxsplit=1)[0])
    assert major_version >= 10
    assert "outreach draft" not in source.casefold()


def test_m10_live_cleanup_uses_the_hosted_delete_all_request_shape() -> None:
    live_test_source = (
        PROJECT_ROOT / "tests" / "integration" / "test_mem0_memory_live.py"
    ).read_text(encoding="utf-8")

    assert "client.delete_all(user_id=candidate_id)" in live_test_source
    assert "client.delete_all(filters=" not in live_test_source
