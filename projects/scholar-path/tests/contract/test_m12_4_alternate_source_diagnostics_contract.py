"""Repository contract for the bounded M12.4 alternate-source diagnostic repair."""

from pathlib import Path
from typing import Annotated, get_origin, get_type_hints

from scholarpath.evaluation import LOCAL_BASELINE_NAME
from scholarpath.graph import (
    AlternateSourceAttempt,
    AlternateSourceRejectionCategory,
    AlternateSourceRejectionCounts,
    ScholarPathState,
    VerificationPolicy,
    merge_alternate_source_attempts,
)
from scholarpath.observability import GRAPH_VERSION
from scholarpath.ui import AlternateSourceDiagnosticsView

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m12_4_prompt_diagram_readme_architecture_and_journal_are_recorded() -> None:
    prompt_path = PROJECT_ROOT / "docs/prompts/m12-4-alternate-source-diagnostics.md"
    diagram_path = PROJECT_ROOT / "docs/m12-4-alternate-source-diagnostics.mmd"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt_path.is_file()
    assert diagram_path.is_file()
    assert "M12.4 Privacy-safe alternate-source diagnostics repair" in prompt_path.read_text(
        encoding="utf-8"
    )
    assert "first failure" in diagram_path.read_text(encoding="utf-8")
    assert "M12.4 privacy-safe alternate-source diagnostics repair" in readme
    assert "M12.4 privacy-safe alternate-source diagnostics boundary" in architecture
    assert "## M12.4 Repair: Privacy-safe alternate-source diagnostics" in journal


def test_m12_4_versions_graph_and_offline_evaluation_baseline() -> None:
    assert GRAPH_VERSION == "m13"
    assert LOCAL_BASELINE_NAME == "scholarpath-m13-fake-baseline-2026-08-30"


def test_m12_4_uses_exact_first_failed_gate_taxonomy() -> None:
    assert {category.value for category in AlternateSourceRejectionCategory} == {
        "query_mismatch",
        "same_url",
        "https_or_host_invalid",
        "exact_person_text_missing",
        "exact_institution_text_missing",
        "singular_route_mismatch",
        "academic_host_mismatch",
        "source_kind_unsupported",
    }
    assert set(AlternateSourceRejectionCounts.model_fields) == {
        category.value for category in AlternateSourceRejectionCategory
    }


def test_m12_4_persisted_attempt_schema_contains_only_bounded_audit_fields() -> None:
    assert set(AlternateSourceAttempt.model_fields) == {
        "supervisor_id",
        "attempt_number",
        "discovery_round",
        "outcome",
        "result_count",
        "eligible_result_count",
        "rejection_counts",
        "error_category",
    }
    forbidden_fields = {
        "query",
        "url",
        "title",
        "description",
        "snippet",
        "page_content",
        "candidate_profile",
        "provider_payload",
        "exception_text",
    }
    assert forbidden_fields.isdisjoint(AlternateSourceAttempt.model_fields)


def test_m12_4_state_uses_replay_safe_attempt_reducer() -> None:
    annotation = get_type_hints(ScholarPathState, include_extras=True)["alternate_source_attempts"]

    assert get_origin(annotation) is Annotated
    assert annotation.__metadata__ == (merge_alternate_source_attempts,)


def test_m12_4_ui_projection_omits_internal_identity_and_source_fields() -> None:
    assert set(AlternateSourceDiagnosticsView.model_fields) == {
        "attempted_supervisor_count",
        "result_count",
        "eligible_result_count",
        "selected_source_count",
        "no_results_count",
        "rejected_all_count",
        "provider_error_count",
        "not_configured_count",
        "rejection_counts",
    }
    assert {
        "supervisor_id",
        "query",
        "url",
        "result_content",
        "candidate_profile",
    }.isdisjoint(AlternateSourceDiagnosticsView.model_fields)


def test_m12_4_keeps_verification_and_retry_thresholds_unchanged() -> None:
    policy = VerificationPolicy()

    assert policy.minimum_verified_supervisors == 5
    assert policy.maximum_alternate_source_retries == 1
