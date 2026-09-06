"""Preserve the observed, same-cohort LangSmith comparison without live calls."""

import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from scholarpath.evaluation.evaluators import DETERMINISTIC_EVALUATORS
from scholarpath.evaluation.reviewed_manifest import build_reviewed_manifest
from scholarpath.evaluation.reviewed_upload import ReviewedUploadedReport
from scholarpath.evaluation.runner import stable_example_id

ARTIFACTS = Path(__file__).resolve().parents[2] / "docs" / "evaluation"
BEFORE = ARTIFACTS / "week4-reviewed-langsmith-baseline-2026-09-06.json"
AFTER = ARTIFACTS / "week4-reviewed-langsmith-after-2026-09-06.json"
REPAIRED_CASE = "draft-evidence-heading-bound-research"


def _read(path: Path) -> ReviewedUploadedReport:
    return ReviewedUploadedReport.model_validate_json(path.read_text())


@pytest.mark.parametrize("artifact", (BEFORE, AFTER))
def test_recorded_reports_validate_and_round_trip(artifact: Path) -> None:
    report = _read(artifact)

    assert ReviewedUploadedReport.model_validate_json(report.model_dump_json()) == report
    assert report.example_count == 30
    assert report.execution_mode == "fake_only"
    assert report.approval_scope == "expected_behaviors"
    assert report.readback_complete


def test_after_reuses_the_frozen_dataset_snapshot_and_example_ids() -> None:
    before, after = _read(BEFORE), _read(AFTER)
    manifest = build_reviewed_manifest()

    assert before.dataset_name == after.dataset_name == manifest.dataset_name
    assert before.content_digest == after.content_digest == manifest.content_digest
    assert before.source_draft_digest == after.source_draft_digest == manifest.source_draft_digest
    assert before.reviewed_version == after.reviewed_version == manifest.reviewed_version
    assert before.dataset_id == after.dataset_id
    assert before.dataset_url == after.dataset_url
    assert before.snapshot_as_of == after.snapshot_as_of
    assert before.graph_version == after.graph_version == "m13"
    assert after.dataset_created is False
    expected_ids = {
        case.scenario.scenario_id: stable_example_id(
            manifest.dataset_name, case.scenario.scenario_id
        )
        for case in manifest.source_draft.cases
    }
    assert {case.scenario_id: case.example_id for case in before.cases} == expected_ids
    assert {case.scenario_id: case.example_id for case in after.cases} == expected_ids


def test_after_is_a_distinct_complete_thirty_root_experiment() -> None:
    before, after = _read(BEFORE), _read(AFTER)

    assert after.experiment_name == "scholarpath-week4-reviewed-upload-m13-b804f2f2"
    assert before.experiment_id != after.experiment_id
    assert before.experiment_name != after.experiment_name
    assert after.observation_source == "upload"
    assert len(after.cases) == len(after.run_references) == 30
    run_ids = {case.run_id for case in after.cases}
    assert len(run_ids) == 30
    assert run_ids == {reference.run_id for reference in after.run_references}
    assert run_ids.isdisjoint(case.run_id for case in before.cases)
    assert {(case.run_id, case.trace_id) for case in after.cases} == {
        (reference.run_id, reference.trace_id) for reference in after.run_references
    }
    assert all(case.persisted and case.feedback_persisted for case in after.cases)
    graph_cases = {case.scenario_id for case in after.runtime_cases if case.target == "graph_fake"}
    assert len(graph_cases) == 12
    assert all(
        case.graph_child_visible is (True if case.scenario_id in graph_cases else None)
        for case in after.cases
    )
    metric_keys = {evaluator.__name__ for evaluator in DETERMINISTIC_EVALUATORS}
    assert len(metric_keys) == 11
    assert sum(len(case.metrics) for case in after.cases) == 330
    assert all({metric.key for metric in case.metrics} == metric_keys for case in after.cases)
    assert all(case.duplicate_rate_semantics_source != "unavailable" for case in after.cases)


def test_only_heading_bound_expected_behavior_changes_from_fail_to_pass() -> None:
    before, after = _read(BEFORE), _read(AFTER)
    before_metrics = {
        (case.scenario_id, metric.key): metric for case in before.cases for metric in case.metrics
    }
    after_metrics = {
        (case.scenario_id, metric.key): metric for case in after.cases for metric in case.metrics
    }
    assert before_metrics.keys() == after_metrics.keys()
    changed = []
    for key, original in before_metrics.items():
        current = after_metrics[key]
        assert original.applicable is current.applicable
        # Saved feedback uses numeric 1/0; fresh evaluation can use bool True/False.
        if (original.passed, original.score) != (current.passed, current.score):
            changed.append(key)
    assert changed == [(REPAIRED_CASE, "expected_behavior")]
    original = before_metrics[changed[0]]
    current = after_metrics[changed[0]]
    assert not original.passed and original.score == 0
    assert current.passed and current.score == 1
    assert before.failed_example_count == 1
    assert len(before.failures) == 1
    assert before.failures[0].scenario_id == REPAIRED_CASE
    assert after.failed_example_count == 0 and after.failures == ()
    assert after.passed


def test_call_counts_and_legacy_budget_failure_are_not_rewritten_as_an_optimization() -> None:
    before, after = _read(BEFORE), _read(AFTER)
    original_counts = {
        case.scenario_id: (case.target, case.measurement.port_invocations)
        for case in before.runtime_cases
    }
    current_counts = {
        case.scenario_id: (case.target, case.measurement.port_invocations)
        for case in after.runtime_cases
    }

    assert len(original_counts) == len(current_counts) == 30
    assert original_counts == current_counts
    assert current_counts["draft-graph-request-more"] == ("graph_fake", 76)
    assert before.runtime_budget == after.runtime_budget
    for report in (before, after):
        graph = next(item for item in report.runtime_summaries if item.target == "graph_fake")
        assert (graph.maximum_port_invocations, graph.invocation_budget) == (76, 40)
        assert graph.invocation_budget_passed is False
        assert report.provisional_runtime_budgets_passed is False


def test_after_links_preserve_observed_authenticated_run_coordinates() -> None:
    after = _read(AFTER)
    assert after.experiment_url is not None and after.dataset_url is not None
    urls = [after.experiment_url, after.dataset_url]
    urls.extend(case.run_url for case in after.cases if case.run_url is not None)
    assert len(urls) == 32
    for url in urls:
        parsed = urlsplit(url)
        assert parsed.scheme == "https" and parsed.hostname == "smith.langchain.com"
        assert parsed.username is None and parsed.password is None
        assert not parsed.fragment
        assert "/public/" not in parsed.path
        assert not {"api_key", "token", "access_token"}.intersection(parse_qs(parsed.query))
    assert f"/datasets/{after.dataset_id}" in urlsplit(after.dataset_url).path
    assert parse_qs(urlsplit(after.experiment_url).query)["selectedSessions"] == [
        str(after.experiment_id)
    ]
    for case in after.cases:
        assert case.run_url is not None
        parsed = urlsplit(case.run_url)
        assert parsed.path.endswith(f"/projects/p/{after.experiment_id}/r/{case.run_id}")
        assert parse_qs(parsed.query)["trace_id"] == [str(case.trace_id)]


def test_recorded_after_contains_only_the_existing_report_schema_not_private_payloads() -> None:
    raw = json.loads(AFTER.read_text())
    assert set(raw) == set(ReviewedUploadedReport.model_fields)
    serialized = json.dumps(raw)
    for forbidden_field in (
        "api_key",
        "candidate_id",
        "candidate_profile",
        "proposed_research_statement",
        "full_name",
        "email",
        "institution",
        "source_url",
        "supporting_excerpt",
        "page_content",
        "raw_content",
        "search_queries",
    ):
        assert f'"{forbidden_field}"' not in serialized
