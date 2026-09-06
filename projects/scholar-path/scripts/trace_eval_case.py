"""Check one fake fallback scenario offline; opt in to its inspectable LangSmith trace."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from scholarpath.config import load_evaluation_settings, load_langsmith_settings
from scholarpath.evaluation.runner import (
    format_failure_summary,
    run_local_baseline,
    run_uploaded_experiment,
    sync_evaluation_dataset,
)
from scholarpath.evaluation.synthetic_tracing import create_synthetic_trace_client
from scholarpath.evaluation.trace_case import SYNTHETIC_TRACE_DATASET, synthetic_trace_scenario


def main(argv: Sequence[str] | None = None) -> int:
    """Default to zero network; upload only one curated fake case after both opt-ins."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--upload", action="store_true", help="Send the one fake case to LangSmith."
    )
    args = parser.parse_args(argv)
    scenario = synthetic_trace_scenario()
    offline = run_local_baseline(scenarios=(scenario,))
    print(f"Offline preflight: {offline.passed_scenario_count}/{offline.scenario_count} passed.")
    if not offline.passed:
        print(format_failure_summary(offline))
        return 1
    if not args.upload:
        print("No upload. All providers were fake; no network calls were made.")
        return 0
    settings = load_evaluation_settings()
    if not settings.run_langsmith_evals:
        print("Upload requires SCHOLARPATH_RUN_LANGSMITH_EVALS=true.", file=sys.stderr)
        return 2
    client = None
    exit_status = 2
    try:
        client = create_synthetic_trace_client(load_langsmith_settings())
        sync_evaluation_dataset(client, dataset_name=SYNTHETIC_TRACE_DATASET, scenarios=(scenario,))
        report = run_uploaded_experiment(
            client,
            evaluation_settings=settings,
            dataset_name=SYNTHETIC_TRACE_DATASET,
            synthetic_trace=True,
        )
        client.flush(timeout=5)
        print(f"Experiment: {report.experiment_name}")
        print(
            f"Passed: {report.example_count - report.failed_example_count}/{report.example_count}"
        )
        for reference in report.run_references:
            print(f"Trace reference: {reference.model_dump_json()}")
        print(format_failure_summary(report))
        print("Only LangSmith was live. Models, search, extraction, and memory were fake.")
        exit_status = 0 if report.passed else 1
    except Exception:
        # SDK exceptions can contain credentials, HTTP bodies, or source content.
        print(
            "Trace upload failed. Check LangSmith endpoint, credentials and permissions.",
            file=sys.stderr,
        )
    finally:
        if client is not None:
            try:
                client.close(timeout=5)
            except Exception:
                print("Trace client cleanup failed; details withheld.", file=sys.stderr)
                exit_status = 2
    return exit_status


if __name__ == "__main__":
    raise SystemExit(main())
