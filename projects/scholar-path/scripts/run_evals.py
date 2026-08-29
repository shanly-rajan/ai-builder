"""Run ScholarPath's offline baseline or an explicitly uploaded LangSmith experiment."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from langsmith.utils import LangSmithError

from scholarpath.config import (
    ProviderConfigurationError,
    load_evaluation_settings,
    load_langsmith_settings,
    load_openai_planning_settings,
)
from scholarpath.evaluation import (
    EvaluationTargetKind,
    build_openai_judge_evaluators,
    create_langsmith_evaluation_client,
    run_local_baseline,
    run_uploaded_experiment,
    sync_evaluation_dataset,
)
from scholarpath.evaluation.targets import (
    evidence_verification_target,
    fake_end_to_end_target,
    live_end_to_end_target,
    research_fit_target,
    search_planning_target,
)

# Keep every supported public target visible to CLI introspection and contract tests.
_PUBLIC_TARGETS = (
    search_planning_target,
    evidence_verification_target,
    research_fit_target,
    fake_end_to_end_target,
    live_end_to_end_target,
)


def _target(value: str) -> EvaluationTargetKind | None:
    if value == "all":
        return None
    return EvaluationTargetKind(value)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run ScholarPath M12 synthetic regression evaluations."
    )
    parser.add_argument(
        "--target",
        choices=(
            "all",
            EvaluationTargetKind.SEARCH_PLANNING.value,
            EvaluationTargetKind.EVIDENCE_VERIFICATION.value,
            EvaluationTargetKind.RESEARCH_FIT.value,
            EvaluationTargetKind.GRAPH_FAKE.value,
            EvaluationTargetKind.GRAPH_LIVE.value,
        ),
        default="all",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help=("Upload results to LangSmith after SCHOLARPATH_RUN_LANGSMITH_EVALS=true is enabled."),
    )
    parser.add_argument(
        "--include-llm-judges",
        action="store_true",
        help="Add the four scoped structured-output judges to an uploaded experiment.",
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help=(
            "Run only the separately gated live end-to-end example; requires "
            "SCHOLARPATH_RUN_LIVE_E2E_EVALS=true."
        ),
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Execute the offline default or the separately authorized uploaded path."""
    args = _parser().parse_args(argv)
    selected_target = _target(args.target)
    live = args.live or selected_target is EvaluationTargetKind.GRAPH_LIVE
    if args.live and selected_target not in {None, EvaluationTargetKind.GRAPH_LIVE}:
        print("--live may be combined only with --target all or graph_live.", file=sys.stderr)
        return 2
    if live and not args.upload:
        print("Live end-to-end evaluation requires the explicit --upload option.", file=sys.stderr)
        return 2
    if args.include_llm_judges and not args.upload:
        print(
            "LLM judges are available only for an explicitly uploaded experiment.",
            file=sys.stderr,
        )
        return 2

    if not args.upload:
        report = run_local_baseline(target=selected_target)
        print(f"Baseline: {report.baseline_name}")
        print(f"Dataset: {report.dataset_name}")
        print(f"Scenarios: {report.passed_scenario_count}/{report.scenario_count} passed")
        for metric in report.metric_summaries:
            observed = "n/a" if metric.observed_mean is None else f"{metric.observed_mean:.3f}"
            print(
                f"- {metric.key}: {metric.passed_count}/{metric.applicable_count} "
                f"passed; mean={observed}"
            )
        return 0 if report.passed else 1

    evaluation_settings = load_evaluation_settings()
    if not evaluation_settings.run_langsmith_evals:
        print(
            "LangSmith evaluation upload is disabled. Set "
            "SCHOLARPATH_RUN_LANGSMITH_EVALS=true to opt in.",
            file=sys.stderr,
        )
        return 2
    if live and not evaluation_settings.run_live_e2e_evals:
        print(
            "Live end-to-end evaluation is disabled. Set "
            "SCHOLARPATH_RUN_LIVE_E2E_EVALS=true to opt in.",
            file=sys.stderr,
        )
        return 2
    try:
        client = create_langsmith_evaluation_client(load_langsmith_settings())
        sync_evaluation_dataset(
            client,
            dataset_name=evaluation_settings.evaluation_dataset_name,
        )
        judges = (
            build_openai_judge_evaluators(
                load_openai_planning_settings(),
                evaluation_settings,
            )
            if args.include_llm_judges
            else ()
        )
        result = run_uploaded_experiment(
            client,
            evaluation_settings=evaluation_settings,
            dataset_name=evaluation_settings.evaluation_dataset_name,
            target=selected_target,
            judge_evaluators=judges,
            live=live,
        )
    except (ProviderConfigurationError, ValueError) as error:
        print(str(error), file=sys.stderr)
        return 2
    except LangSmithError:
        print(
            "The LangSmith experiment request failed. Verify endpoint, API key, workspace, "
            "and permissions.",
            file=sys.stderr,
        )
        return 2
    print(
        f"LangSmith experiment completed: {result.experiment_name}; "
        f"{result.example_count - result.failed_example_count}/{result.example_count} "
        "examples passed deterministic gates."
    )
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
