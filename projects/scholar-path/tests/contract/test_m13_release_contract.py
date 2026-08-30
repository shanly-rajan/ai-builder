"""Repository-level contract for the M13 submission-ready release boundary."""

import tomllib
from pathlib import Path

import pytest
from pydantic import ValidationError

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.evaluation import LOCAL_BASELINE_NAME
from scholarpath.graph import DiscoveryPolicy
from scholarpath.observability import GRAPH_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPOSITORY_ROOT = PROJECT_ROOT.parents[1]


def test_m13_release_artifacts_and_architecture_record_are_present() -> None:
    required_paths = (
        "docs/prompts/m13-reliability-hardening-and-release.md",
        "docs/reliability-review.md",
        "docs/release-checklist.md",
        "docs/m13-release-architecture.mmd",
        "docs/m13-langgraph-node-edge.mmd",
        "requirements.lock",
        "tests/integration/test_m13_release_end_to_end.py",
        "tests/integration/test_m13_live_canary.py",
    )

    for relative_path in required_paths:
        assert (PROJECT_ROOT / relative_path).is_file(), f"Missing M13 artifact: {relative_path}"

    prompt = (PROJECT_ROOT / required_paths[0]).read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")

    assert "Milestone M13: reliability hardening and submission-ready" in prompt
    assert "## Milestone M13: Reliability hardening and submission-ready release" in journal
    assert "## M13 submission-ready reliability boundary" in architecture


def test_m13_versions_the_graph_and_offline_release_baseline() -> None:
    baseline = (PROJECT_ROOT / "docs/evaluation-baseline.md").read_text(encoding="utf-8")

    assert GRAPH_VERSION == "m13"
    assert LOCAL_BASELINE_NAME == "scholarpath-m13-fake-baseline-2026-08-30"
    assert LOCAL_BASELINE_NAME in baseline
    assert "Graph version | `m13`" in baseline


def test_m13_has_finite_langsmith_and_discovery_release_controls() -> None:
    tracing = LangSmithSettings()
    discovery = DiscoveryPolicy()

    assert tracing.request_timeout_seconds == 10.0
    assert tracing.maximum_retry_count == 2
    assert discovery.maximum_prospective_supervisors == 20
    assert discovery.maximum_prospective_supervisors >= discovery.minimum_unique_supervisors

    with pytest.raises(ValidationError, match="failure injection must be off"):
        ApplicationSettings(
            environment=Environment.PRODUCTION,
            discovery_failure_mode=DiscoveryFailureMode.YOU_RETRYABLE_ERROR,
        )


def test_m13_reproducible_constraints_and_ci_commands_are_locked() -> None:
    constraint_lines = tuple(
        line.strip()
        for line in (PROJECT_ROOT / "requirements.lock").read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    workflow = (REPOSITORY_ROOT / ".github/workflows/scholarpath-ci.yml").read_text(
        encoding="utf-8"
    )
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert len(constraint_lines) >= 80
    assert all("==" in line for line in constraint_lines)
    assert "setuptools==84.0.0" in project["build-system"]["requires"]
    assert "pip==26.1.2" in workflow
    assert "setuptools==84.0.0" in workflow
    assert "--constraint requirements.lock" in workflow
    assert "mypy src tests scripts" in workflow
    assert 'pytest -m "not live"' in workflow


def test_m13_release_scope_excludes_unrequested_platforms_and_outreach() -> None:
    project = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    dependencies = " ".join(project["project"]["dependencies"]).casefold()
    production_source = "\n".join(
        path.read_text(encoding="utf-8") for path in sorted((PROJECT_ROOT / "src").rglob("*.py"))
    ).casefold()

    for excluded in ("pinecone", "fireworks", "llamaindex", "llama-index"):
        assert excluded not in dependencies
    assert "generate_outreach" not in production_source
    assert "draft_outreach" not in production_source


def test_m13_readme_contains_the_complete_release_handoff() -> None:
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")

    required_sections = (
        "**Canonical one-liner:**",
        "## M13 project overview and release scope",
        "## Agents",
        "## Technology decisions",
        "## Dataset and source description",
        "## Test strategy and LangSmith evaluation",
        "## Sample output",
        "## Known limitations",
        "## Future roadmap",
        "## Release checklist",
    )
    for section in required_sections:
        assert section in readme
    assert "v0.1.0" in readme
    assert "requirements.lock" in readme
    assert "SCHOLARPATH_RUN_LIVE_CANARY=true" in readme


def test_m13_live_canary_is_separately_opted_in_and_call_budgeted() -> None:
    source = (PROJECT_ROOT / "tests/integration/test_m13_live_canary.py").read_text(
        encoding="utf-8"
    )

    assert "@pytest.mark.live" in source
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in source
    assert "SCHOLARPATH_RUN_LIVE_CANARY" in source
    assert "sum(budget.calls.values()) <= 9" in source
