"""Repository-level contract for the M12 LangSmith evaluation suite."""

import ast
import tomllib
from pathlib import Path
from typing import cast

from scholarpath.evaluation import (
    DETERMINISTIC_EVALUATORS,
    evidence_grounded_rationale_judge,
    evidence_verification_target,
    explanation_usefulness_judge,
    fake_end_to_end_target,
    live_end_to_end_target,
    make_judge_evaluators,
    research_fit_relevance_judge,
    research_fit_target,
    search_planning_target,
    shortlist_usefulness_judge,
)
from scholarpath.observability import GRAPH_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _read(relative_path: str) -> str:
    return (PROJECT_ROOT / relative_path).read_text(encoding="utf-8")


def _defined_functions(source: str) -> set[str]:
    return {
        node.name
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }


def test_m12_packages_the_public_evaluation_boundary_and_current_langsmith_sdk() -> None:
    with (PROJECT_ROOT / "pyproject.toml").open("rb") as pyproject_file:
        pyproject = tomllib.load(pyproject_file)
    dependencies = cast(list[str], pyproject["project"]["dependencies"])
    packages = cast(list[str], pyproject["tool"]["setuptools"]["packages"])
    mypy_files = cast(list[str], pyproject["tool"]["mypy"]["files"])
    pytest_markers = cast(list[str], pyproject["tool"]["pytest"]["ini_options"]["markers"])

    assert [item for item in dependencies if item.casefold().startswith("langsmith")] == [
        "langsmith>=0.11.2,<1"
    ]
    assert "scholarpath.evaluation" in packages
    assert "scripts" in mypy_files
    assert any(marker.startswith("live:") for marker in pytest_markers)
    assert (PROJECT_ROOT / "src" / "py.typed").is_file()


def test_m12_exports_exact_target_and_evaluator_families() -> None:
    for target in (
        search_planning_target,
        evidence_verification_target,
        research_fit_target,
        fake_end_to_end_target,
        live_end_to_end_target,
    ):
        assert callable(target)

    assert tuple(item.__name__ for item in DETERMINISTIC_EVALUATORS) == (
        "schema_validity",
        "canonical_terminology",
        "evidence_id_validity",
        "source_url_presence",
        "score_range_and_component_totals",
        "no_unsupported_availability_claim",
        "no_admission_probability",
        "correct_fallback_route",
        "duplicate_supervisor_rate",
        "human_approval_enforcement",
    )
    assert tuple(
        item.__name__
        for item in (
            research_fit_relevance_judge,
            explanation_usefulness_judge,
            evidence_grounded_rationale_judge,
            shortlist_usefulness_judge,
            make_judge_evaluators,
        )
    ) == (
        "research_fit_relevance_judge",
        "explanation_usefulness_judge",
        "evidence_grounded_rationale_judge",
        "shortlist_usefulness_judge",
        "make_judge_evaluators",
    )


def test_deterministic_evaluators_have_no_model_or_network_dependency() -> None:
    source = _read("src/evaluation/evaluators.py")

    for forbidden in (
        "ChatOpenAI",
        "langchain_openai",
        "httpx",
        "requests",
        "Client(",
        ".invoke(",
    ):
        assert forbidden not in source


def test_qualitative_judge_uses_strict_structured_output_and_no_manual_json_parsing() -> None:
    source = _read("src/evaluation/judges.py")

    assert ".with_structured_output(" in source
    assert 'method="json_schema"' in source
    assert "strict=True" in source
    assert "StructuredJudgeResult" in source
    assert "EvaluationJudgePort" in source
    assert "json.loads(" not in source
    assert "Do not browse" in source
    assert "estimate admission probability" in source


def test_dataset_creation_and_evaluation_scripts_are_cli_safe_and_explicitly_gated() -> None:
    create_script_path = PROJECT_ROOT / "scripts" / "create_eval_dataset.py"
    run_script_path = PROJECT_ROOT / "scripts" / "run_evals.py"
    assert create_script_path.is_file()
    assert run_script_path.is_file()

    create_source = create_script_path.read_text(encoding="utf-8")
    run_source = run_script_path.read_text(encoding="utf-8")
    runner_source = _read("src/evaluation/runner.py")
    assert "main" in _defined_functions(create_source)
    assert "main" in _defined_functions(run_source)
    assert '__name__ == "__main__"' in create_source
    assert '__name__ == "__main__"' in run_source
    assert "create_langsmith_evaluation_client" in create_source
    assert "Client" in runner_source
    assert ".evaluate(" in runner_source
    for target_name in (
        "search_planning_target",
        "evidence_verification_target",
        "research_fit_target",
        "fake_end_to_end_target",
        "live_end_to_end_target",
    ):
        assert target_name in run_source
    assert "SCHOLARPATH_RUN_LANGSMITH_EVALS" in run_source
    assert "SCHOLARPATH_RUN_LIVE_E2E_EVALS" in run_source


def test_live_experiments_have_marker_credentials_and_multiple_opt_ins() -> None:
    live_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((PROJECT_ROOT / "tests" / "integration").glob("*m12*live*.py"))
    )

    assert "@pytest.mark.live" in live_sources
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in live_sources
    assert "SCHOLARPATH_RUN_LANGSMITH_EVALS" in live_sources
    assert "LANGSMITH_API_KEY" in live_sources


def test_m12_environment_example_keeps_uploads_and_live_execution_off_by_default() -> None:
    environment_example = _read(".env.example")

    assert "SCHOLARPATH_RUN_LANGSMITH_EVALS=false" in environment_example
    assert "SCHOLARPATH_RUN_LIVE_E2E_EVALS=false" in environment_example
    assert "SCHOLARPATH_EVALUATION_DATASET_NAME=scholarpath-m12-regression-v1" in (
        environment_example
    )
    assert "SCHOLARPATH_EVALUATION_EXPERIMENT_PREFIX=scholarpath-m12" in (environment_example)
    assert "SCHOLARPATH_EVALUATION_JUDGE_MODEL=" in environment_example
    assert "LANGSMITH_API_KEY=" in environment_example


def test_m12_prompt_plan_diagram_baseline_readme_and_build_journal_are_recorded() -> None:
    required_files = (
        "docs/prompts/m12-langsmith-evaluation-and-regression-suite.md",
        "docs/evaluation-plan.md",
        "docs/evaluation-baseline.md",
        "docs/m12-langsmith-evaluation-suite.mmd",
    )
    for relative_path in required_files:
        assert (PROJECT_ROOT / relative_path).is_file(), f"Missing M12 artifact: {relative_path}"

    prompt = _read(required_files[0])
    plan = _read(required_files[1])
    baseline = _read(required_files[2])
    diagram = _read(required_files[3])
    readme = _read("README.md")
    journal = _read("docs/build-journal.md")

    assert "Milestone M12" in prompt
    assert "https://docs.langchain.com/langsmith/evaluation" in plan
    assert "https://docs.langchain.com/langsmith/evaluation-quickstart" in plan
    assert "Deterministic" in plan and "LLM-as-judge" in plan
    assert "scholarpath-m12-fake-baseline-2026-08-29" in baseline
    assert "2026-08-29" in baseline
    assert "Pending" in baseline
    assert "Not run" in baseline
    assert "flowchart" in diagram
    assert "scripts/create_eval_dataset.py" in readme
    assert "scripts/run_evals.py" in readme
    assert "Milestone M12" in journal
    assert GRAPH_VERSION == "m12"
