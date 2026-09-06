"""Inspect a locally frozen manifest and measure it with fake providers only."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Literal
from uuid import uuid4

from langsmith import tracing_context

from .measurements import format_runtime_summary, runtime_budgets_passed
from .reviewed_manifest import ReviewedEvaluationManifest, build_reviewed_manifest
from .runner import LocalEvaluationReport, run_local_baseline


class ReviewedBaselineReport(LocalEvaluationReport):
    """Measurements tied to approved expectations, not a claim of live quality."""

    reviewed_version: str
    content_digest: str
    source_draft_digest: str
    approval_scope: Literal["expected_behaviors"] = "expected_behaviors"
    execution_mode: Literal["fake_only"] = "fake_only"

    @property
    def runtime_budgets_passed(self) -> bool | None:
        """Keep provisional runtime results separate from correctness approval."""
        return runtime_budgets_passed(self.runtime_summaries)


def run_reviewed_baseline(manifest: ReviewedEvaluationManifest) -> ReviewedBaselineReport:
    """Revalidate the frozen inputs, then run offline regardless of live opt-ins."""
    manifest = ReviewedEvaluationManifest.model_validate(manifest.model_dump())
    with tracing_context(enabled=False):
        observations = run_local_baseline(
            scenarios=tuple(case.scenario for case in manifest.source_draft.cases)
        )
    # The shared runner's default dataset name belongs to the original eleven
    # cases. Copy observations, never reuse that cohort's experiment identity.
    return ReviewedBaselineReport.model_validate(
        {
            **observations.model_dump(),
            "baseline_name": (
                f"scholarpath-week4-reviewed-local-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
                f"-{uuid4().hex[:8]}"
            ),
            "dataset_name": manifest.dataset_name,
            "reviewed_version": manifest.reviewed_version,
            "content_digest": manifest.content_digest,
            "source_draft_digest": manifest.source_draft.content_digest,
        }
    )


def main(argv: Sequence[str] | None = None) -> int:
    """Preview or measure locally; deliberately no upload, live, judge, or write mode."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument("--check", action="store_true", help="Measure all 30 cases offline.")
    args = parser.parse_args(argv)
    manifest = build_reviewed_manifest()
    if not args.check:
        if args.format == "json":
            print(
                json.dumps(
                    {**manifest.model_dump(mode="json"), "content_digest": manifest.content_digest},
                    indent=2,
                )
            )
        else:
            print(f"Dataset: {manifest.dataset_name} ({manifest.reviewed_version})")
            print(f"Status: {manifest.status}; approval scope: {manifest.approval_scope}")
            print(f"Content SHA-256: {manifest.content_digest}")
            print("30 expected behaviors approved: 5 individually, 25 by explicit batch approval.")
            print("Original pending draft preserved. No targets executed or data uploaded.")
        return 0

    report = run_reviewed_baseline(manifest)
    if args.format == "json":
        print(report.model_dump_json(indent=2))
    else:
        print(f"Local baseline: {report.baseline_name}")
        print(f"Dataset: {report.dataset_name} ({report.reviewed_version})")
        print(f"Content SHA-256: {report.content_digest}")
        print(f"Offline checks: {report.passed_scenario_count}/{report.scenario_count} passed")
        for metric in report.metric_summaries:
            print(
                f"{metric.key}: {metric.passed_count}/{metric.applicable_count} applicable passed"
            )
        for failure in report.failures:
            print(f"FAIL {failure.scenario_id}: {failure.key} ({failure.category})")
        print(
            format_runtime_summary(report.runtime_summaries).replace(
                "\nFake-cohort budgets are diagnostic unless --enforce-runtime-budgets is set.", ""
            )
        )
        print(f"Provisional runtime budgets passed: {report.runtime_budgets_passed}")
        print("Exit status checks correctness; runtime is reported separately, not waived.")
        print("Expected-behavior approval is not a passing result or a live quality measurement.")
    return 0 if report.passed else 1
