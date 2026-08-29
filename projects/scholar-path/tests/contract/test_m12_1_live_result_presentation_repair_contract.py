"""Repository contract for the bounded M12.1 live-result presentation repair."""

from pathlib import Path

from scholarpath.evaluation import LOCAL_BASELINE_NAME
from scholarpath.graph import DiscoveryPolicy, ToolErrorRecord
from scholarpath.observability import GRAPH_VERSION
from scholarpath.ui import RecoverableUiError

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m12_1_prompt_diagram_readme_architecture_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs/prompts/m12-1-live-result-presentation-repair.md"
    diagram = PROJECT_ROOT / "docs/m12-1-live-result-presentation-repair.mmd"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert diagram.is_file()
    assert "M12.1 Live-result presentation repair" in prompt.read_text(encoding="utf-8")
    assert "flowchart" in diagram.read_text(encoding="utf-8")
    assert "M12.1 live-result presentation repair" in readme
    assert "M12.1 live-result presentation boundary" in architecture
    assert "## M12.1 Repair: Live-result presentation" in journal


def test_m12_1_keeps_discovery_policy_and_graph_audit_records_unchanged() -> None:
    policy = DiscoveryPolicy()

    assert GRAPH_VERSION == "m12.1"
    assert LOCAL_BASELINE_NAME == "scholarpath-m12-1-fake-baseline-2026-08-29"
    assert policy.minimum_unique_supervisors == 5
    assert policy.maximum_you_retry_count == 1
    assert policy.maximum_tavily_fallback_count == 4
    assert "occurrence_count" not in ToolErrorRecord.model_fields


def test_m12_1_groups_only_at_the_typed_ui_projection_boundary() -> None:
    discovery_source = (PROJECT_ROOT / "src/agents/supervisor_discovery.py").read_text(
        encoding="utf-8"
    )
    controller_source = (PROJECT_ROOT / "src/ui/controller.py").read_text(encoding="utf-8")

    assert RecoverableUiError.model_fields["occurrence_count"].default == 1
    assert '"dr"' in discovery_source
    assert '"prof"' in discovery_source
    assert "strong_breadcrumb_fragments[-1]" in discovery_source
    assert "key = (error.code, error.message, error.recoverable)" in controller_source
    for forbidden_dependency in ("ChatOpenAI", "langchain", "httpx", "requests"):
        assert forbidden_dependency not in controller_source
