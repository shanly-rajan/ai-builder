"""Repository contract for the guarded M13.2 deterministic demonstration runtime."""

from pathlib import Path

from scholarpath.config import ApplicationSettings, RuntimeProfile
from scholarpath.graph import GraphFixtureConfig

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m13_2_prompt_documentation_and_journal_are_present() -> None:
    required_paths = (
        "docs/prompts/m13-2-deterministic-demo-runtime.md",
        "docs/architecture.md",
        "tests/integration/test_m13_2_deterministic_demo_streamlit.py",
    )
    for relative_path in required_paths:
        assert (PROJECT_ROOT / relative_path).is_file(), f"Missing M13.2 artifact: {relative_path}"

    prompt = (PROJECT_ROOT / required_paths[0]).read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / required_paths[1]).read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert "Milestone M13.2 Prompt" in prompt
    assert "## M13.2 explicit runtime-composition boundary" in architecture
    assert "## M13.2 Repair: Deterministic Streamlit demonstration runtime" in journal


def test_m13_2_live_is_default_and_strict_graph_policy_is_unchanged() -> None:
    settings = ApplicationSettings()
    graph_config = GraphFixtureConfig()

    assert settings.runtime_profile is RuntimeProfile.LIVE
    assert graph_config.verification_policy.minimum_verified_supervisors == 5
    assert graph_config.verification_policy.maximum_alternate_source_retries == 1
    assert graph_config.shortlist_size == 5


def test_m13_2_demo_runtime_has_no_test_package_dependency_or_form_toggle() -> None:
    service_source = (PROJECT_ROOT / "src/ui/service.py").read_text(encoding="utf-8")
    app_source = (PROJECT_ROOT / "src/ui/app.py").read_text(encoding="utf-8")

    assert "from tests" not in service_source
    assert "import tests" not in service_source
    assert "LangSmithSettings(tracing=False)" in service_source
    assert "create_test_checkpointer()" in service_source
    assert "Runtime profile" not in app_source
    assert 'key="runtime_profile"' not in app_source


def test_m13_2_readme_documents_exact_opt_in_and_synthetic_warning() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    normalized_readme = " ".join(readme.split())

    assert "SCHOLARPATH_RUNTIME_PROFILE=deterministic_demo" in readme
    assert "SCHOLARPATH_RUNTIME_PROFILE=live" in readme
    assert "Synthetic offline demonstration mode is active" in normalized_readme
    assert "fully stopping and restarting Streamlit" in readme
