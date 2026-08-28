"""Contract tests for the M0 repository structure and dependency boundary."""

import tomllib
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]
REPOSITORY_ROOT = TEST_FILE.parents[4]


def test_required_m0_directories_exist() -> None:
    required_directories = (
        "src/domain",
        "src/graph",
        "src/agents",
        "src/tools",
        "src/memory",
        "src/observability",
        "src/ui",
        "tests/unit",
        "tests/graph",
        "tests/contract",
        "tests/integration",
        "tests/fixtures",
        "docs/prompts",
    )

    for relative_path in required_directories:
        with_path = PROJECT_ROOT / relative_path
        assert with_path.is_dir(), f"Missing M0 directory: {relative_path}"


def test_required_m0_files_exist() -> None:
    required_files = (
        ".env.example",
        ".gitignore",
        "AGENTS.md",
        "README.md",
        "pyproject.toml",
        "src/__init__.py",
        "src/config.py",
        "src/py.typed",
        "docs/terminology.md",
        "docs/architecture.md",
        "docs/build-journal.md",
        "docs/prompts/m0-repository-foundation.md",
    )

    for relative_path in required_files:
        with_path = PROJECT_ROOT / relative_path
        assert with_path.is_file(), f"Missing M0 file: {relative_path}"


def test_m0_runtime_dependencies_are_minimal() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    assert pyproject["project"]["dependencies"] == [
        "pydantic>=2.10,<3",
        "pydantic-settings>=2.7,<3",
    ]
    assert pyproject["project"]["requires-python"] == ">=3.12"

    all_dependencies = " ".join(
        [
            *pyproject["project"]["dependencies"],
            *pyproject["project"]["optional-dependencies"]["dev"],
        ]
    ).lower()
    for deferred_dependency in ("langgraph", "streamlit", "mem0", "tavily", "openai"):
        assert deferred_dependency not in all_dependencies


def test_physical_src_root_maps_to_the_scholarpath_package() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)

    setuptools = pyproject["tool"]["setuptools"]
    assert setuptools["package-dir"] == {"scholarpath": "src"}
    assert setuptools["package-data"] == {"scholarpath": ["py.typed"]}
    assert set(setuptools["packages"]) == {
        "scholarpath",
        "scholarpath.agents",
        "scholarpath.domain",
        "scholarpath.graph",
        "scholarpath.memory",
        "scholarpath.observability",
        "scholarpath.tools",
        "scholarpath.ui",
    }
    assert not (PROJECT_ROOT / "src" / "scholarpath").exists()


def test_scholarpath_ci_workflow_exists_at_repository_root() -> None:
    workflow = REPOSITORY_ROOT / ".github" / "workflows" / "scholarpath-ci.yml"

    assert workflow.is_file()

    workflow_text = workflow.read_text(encoding="utf-8")
    for required_ci_step in (
        "actions/checkout@v7",
        "actions/setup-python@v7",
        'python-version: "3.12"',
        "ruff format --check .",
        "ruff check .",
        "mypy src tests",
        'pytest -m "not live"',
    ):
        assert required_ci_step in workflow_text


def test_readme_contains_exact_setup_and_quality_commands() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    required_commands = (
        "python3 -m venv venv",
        "source venv/bin/activate",
        "python -m pip install --upgrade pip",
        'python -m pip install -e ".[dev]" --config-settings editable_mode=strict',
        "ruff format --check .",
        "ruff check .",
        "mypy src tests",
        'pytest -m "not live"',
    )

    for command in required_commands:
        assert command in readme, f"README is missing command: {command}"
