"""Offline review/export/check entry point; deliberately no upload or live mode."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from collections.abc import Sequence

from langsmith import tracing_context

from .draft_models import EvaluationDraft
from .draft_scenarios import build_evaluation_draft
from .measurements import RuntimeSummary, format_runtime_summary
from .models import EvaluationModel
from .runner import EvaluationFailure, LocalMetricSummary, run_local_baseline


class DraftCheckReport(EvaluationModel):
    """Offline observations identified as a draft, never as the preserved v1 baseline."""

    dataset_name: str
    draft_version: str
    content_digest: str
    human_review_status: str
    scenario_count: int
    passed_scenario_count: int
    metrics: tuple[LocalMetricSummary, ...]
    failures: tuple[EvaluationFailure, ...]
    runtime_summaries: tuple[RuntimeSummary, ...]

    @property
    def passed(self) -> bool:
        """Correctness only; provisional runtime budgets are reported separately."""
        return self.scenario_count > 0 and self.passed_scenario_count == self.scenario_count


def run_draft_checks(draft: EvaluationDraft) -> DraftCheckReport:
    """Exercise real policies with synthetic ports, even when trace opt-ins are set."""
    draft = EvaluationDraft.model_validate(draft.model_dump())
    with tracing_context(enabled=False):
        observations = run_local_baseline(scenarios=tuple(case.scenario for case in draft.cases))
    # Reuse only the observations. The existing runner identifies its default v1
    # baseline; that dataset/experiment identity must never label this new cohort.
    return DraftCheckReport(
        dataset_name=draft.dataset_name,
        draft_version=draft.draft_version,
        content_digest=draft.content_digest,
        human_review_status=draft.status,
        scenario_count=observations.scenario_count,
        passed_scenario_count=observations.passed_scenario_count,
        metrics=observations.metric_summaries,
        failures=observations.failures,
        runtime_summaries=observations.runtime_summaries,
    )


def render_review_table(draft: EvaluationDraft) -> str:
    """Readable, stable label-review inventory; no target execution needed."""
    lines = [
        f"# {draft.dataset_name}",
        "",
        f"Version: {draft.draft_version}. Status: {draft.status}.",
        f"Content SHA-256: {draft.content_digest}",
        "",
        "All detailed labels await human review. Five retained starting-outcome concepts were",
        "previously acknowledged; that is not approval of this dataset. All inputs are synthetic.",
        "",
        "| # | Scenario ID | Type | Origin | Proposed expected outcome |",
        "| --- | --- | --- | --- | --- |",
    ]
    for index, case in enumerate(draft.cases, start=1):
        lines.append(
            f"| {index} | {case.scenario.scenario_id} | {case.scenario_type.value} | "
            f"{case.origin} | {case.label_rationale.replace('|', '/')} |"
        )
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Inspect all labels or run a fake-only check; never write files or approve labels."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", choices=("table", "json"), default="table")
    parser.add_argument("--case", help="Inspect one scenario ID and its full proposed label.")
    parser.add_argument("--check", action="store_true", help="Check all 30 cases offline.")
    args = parser.parse_args(argv)
    if args.check and (args.case or args.format != "table"):
        parser.error("--check runs the full draft; do not combine it with preview options")
    draft = build_evaluation_draft()
    if args.case:
        selected = next(
            (case for case in draft.cases if case.scenario.scenario_id == args.case), None
        )
        if selected is None:
            parser.error("Unknown draft scenario ID")
        print(selected.model_dump_json(indent=2))
    elif args.check:
        report = run_draft_checks(draft)
        print(f"Draft: {report.dataset_name} ({report.draft_version})")
        print(f"Labels: {report.human_review_status}; SHA-256: {report.content_digest}")
        print(f"Offline checks: {report.passed_scenario_count}/{report.scenario_count} passed")
        for metric in report.metrics:
            print(
                f"{metric.key}: {metric.passed_count}/{metric.applicable_count} applicable passed"
            )
        for failure in report.failures:
            print(f"FAIL {failure.scenario_id}: {failure.key} ({failure.category})")
        # The shared formatter's final hint belongs to run_evals.py. This draft
        # intentionally has no runtime-enforcement/upload/live switches.
        runtime_text = format_runtime_summary(report.runtime_summaries).replace(
            "\nFake-cohort budgets are diagnostic unless --enforce-runtime-budgets is set.", ""
        )
        print(runtime_text)
        print("Runtime budgets are reported separately, not enforced by this correctness check.")
        print("Fake-provider checks are not human label approval or live quality measurements.")
        return 0 if report.passed else 1
    elif args.format == "json":
        print(
            json.dumps(
                {**draft.model_dump(mode="json"), "content_digest": draft.content_digest}, indent=2
            )
        )
    else:
        print(render_review_table(draft))
        print()
        print("Mix:", dict(Counter(case.scenario_type.value for case in draft.cases)))
    return 0
