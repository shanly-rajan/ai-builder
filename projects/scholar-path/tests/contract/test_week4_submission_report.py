"""Tie submission figures to saved evidence without live services or uploads."""

import re
from pathlib import Path

import pytest

from scholarpath.evaluation.reviewed_upload import ReviewedUploadedReport

DOCS = Path(__file__).resolve().parents[2] / "docs"
REPORT = DOCS / "week4-submission-report.md"
SCRIPT = DOCS / "week4-recording-script.md"


def _observations(role: str) -> ReviewedUploadedReport:
    return ReviewedUploadedReport.model_validate_json(
        (DOCS / f"evaluation/week4-reviewed-langsmith-{role}-2026-09-06.json").read_text()
    )


@pytest.mark.parametrize("role", ("baseline", "after"))
def test_report_identity_and_quality_counts_match_saved_experiments(role: str) -> None:
    recorded = _observations(role)
    report = REPORT.read_text()
    for identity in (
        recorded.dataset_name,
        recorded.reviewed_version,
        recorded.content_digest,
        recorded.experiment_name,
    ):
        assert identity in report
    assert recorded.readback_complete
    integrity = [
        metric
        for case in recorded.cases
        for metric in case.metrics
        if metric.applicable
        and metric.key
        in {"evidence_id_validity", "source_url_presence", "no_unsupported_availability_claim"}
    ]
    assert len(integrity) == sum(metric.passed for metric in integrity) == 72
    assert "72/72" in report
    outcomes = [
        metric
        for case in recorded.cases
        for metric in case.metrics
        if metric.key == "expected_behavior"
    ]
    assert f"{sum(metric.passed for metric in outcomes)}/{len(outcomes)}" in report


@pytest.mark.parametrize(
    "target", ("evidence_verification", "graph_fake", "research_fit", "search_planning")
)
def test_report_timing_rows_preserve_hosted_family_observations(target: str) -> None:
    before = next(
        item for item in _observations("baseline").runtime_summaries if item.target == target
    )
    after = next(item for item in _observations("after").runtime_summaries if item.target == target)
    assert before.p95_target_seconds is not None and after.p95_target_seconds is not None
    row = next(line for line in REPORT.read_text().splitlines() if line.startswith(f"| {target} |"))
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells[1:] == [
        str(after.case_count),
        f"{before.p95_target_seconds:.6f}",
        f"{after.p95_target_seconds:.6f}",
        f"{after.p95_target_seconds - before.p95_target_seconds:+.6f}",
        f"{before.maximum_port_invocations} → {after.maximum_port_invocations}",
    ]


def test_report_uses_only_recorded_authenticated_langsmith_links() -> None:
    reports = [_observations("baseline"), _observations("after")]
    observed_urls = {report.experiment_url for report in reports}
    observed_urls.update(case.run_url for report in reports for case in report.cases)
    linked_urls = set(
        re.findall(r"\]\((https://smith\.langchain\.com/[^)]+)\)", REPORT.read_text())
    )
    assert len(linked_urls) == 4
    assert linked_urls <= observed_urls
    assert all("/public/" not in url for url in linked_urls)


def test_report_and_script_keep_unfinished_work_and_simulated_evidence_explicit() -> None:
    report = re.sub(r"\s+", " ", REPORT.read_text())
    script = re.sub(r"\s+", " ", SCRIPT.read_text())
    for phrase in (
        "recording not yet provided; submission not yet completed",
        "no third observed frozen-baseline cluster",
        "Do not sum cohorts or call these four frozen-benchmark improvements",
        "Live quality and monetary cost remain unmeasured",
        "9 paused within budget so far",
        "Zero calls saved",
        "no Windows runner evidence",
        "not deployed",
    ):
        assert phrase in report
    assert "Ready to record, not yet recorded" in script
    assert "not a real Candidate endorsing actual Supervisors" in script
    assert "Zero calls were saved" in script


def test_script_has_a_contiguous_five_minute_plan_and_bounded_narration() -> None:
    text = SCRIPT.read_text()
    sections = re.findall(r"^## (\d+):(\d+)–(\d+):(\d+)", text, re.MULTILINE)
    intervals = [(int(a) * 60 + int(b), int(c) * 60 + int(d)) for a, b, c, d in sections]
    assert len(intervals) == 7
    assert intervals[0][0] == 0 and intervals[-1][1] == 300
    assert all(start < end for start, end in intervals)
    assert all(
        left[1] == right[0] for left, right in zip(intervals[:-1], intervals[1:], strict=True)
    )
    narration = " ".join(line[1:] for line in text.splitlines() if line.startswith(">"))
    assert 500 <= len(narration.split()) <= 750
