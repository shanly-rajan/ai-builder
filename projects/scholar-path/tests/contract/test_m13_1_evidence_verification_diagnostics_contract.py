"""Repository contract for the bounded M13.1 evidence-verification diagnostics repair."""

import inspect
from pathlib import Path
from typing import get_args, get_type_hints

from pydantic import BaseModel

from scholarpath.domain import EvidenceClaimType
from scholarpath.graph import (
    EvidenceVerificationRoute,
    ScholarPathState,
    VerificationPolicy,
    route_after_evidence_sufficiency,
)
from scholarpath.tools import ContentExtractionErrorCategory
from scholarpath.ui.controller import _evidence_verification_diagnostics
from scholarpath.ui.models import (
    EvidenceClaimTypeCountsView,
    EvidenceExtractionFailureCountsView,
    EvidenceVerificationDiagnosticsView,
    MissingRequiredEvidenceCountsView,
    UiRunSnapshot,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _schema_property_names(value: object) -> set[str]:
    """Collect nested JSON-schema property names without depending on definition layout."""
    if isinstance(value, dict):
        property_names = set(value.get("properties", {}))
        for nested_value in value.values():
            property_names.update(_schema_property_names(nested_value))
        return property_names
    if isinstance(value, list):
        nested_names: set[str] = set()
        for nested_value in value:
            nested_names.update(_schema_property_names(nested_value))
        return nested_names
    return set()


def test_m13_1_prompt_and_diagram_record_the_observational_boundary() -> None:
    prompt_path = PROJECT_ROOT / "docs/prompts/m13-1-evidence-verification-diagnostics.md"
    diagram_path = PROJECT_ROOT / "docs/m13-1-evidence-verification-diagnostics.mmd"

    assert prompt_path.is_file()
    assert diagram_path.is_file()

    prompt = " ".join(prompt_path.read_text(encoding="utf-8").casefold().split())
    for boundary in (
        "existing `evidence_extraction_attempts`",
        "current `verification_records`",
        "contentextractionerrorcategory",
        "every existing `evidenceclaimtype`",
        "research_interest_or_publication",
        "model-accepted draft counts",
        "first-failed grounding reasons",
        "verification minimum",
        "one alternate-source retry",
        "candidate approval gate",
    ):
        assert boundary in prompt

    diagram = diagram_path.read_text(encoding="utf-8").casefold()
    stages = (
        "page retrieval attempts",
        "retrieved pages",
        "claims retained",
        "directly supported and grounded",
        "completed verification",
        "partial verification",
    )
    assert "flowchart" in diagram
    assert "selected alternate official sources" in diagram
    assert all(stage in diagram for stage in stages)
    assert [diagram.index(stage) for stage in stages] == sorted(
        diagram.index(stage) for stage in stages
    )


def test_m13_1_exposes_only_typed_aggregate_diagnostic_fields() -> None:
    required_fields = {
        "primary_retrieval_attempt_count",
        "primary_retrieval_success_count",
        "primary_retrieval_failure_count",
        "alternate_retrieval_attempt_count",
        "alternate_retrieval_success_count",
        "alternate_retrieval_failure_count",
        "extraction_failure_counts",
        "verification_record_count",
        "completed_verification_record_count",
        "partial_verification_record_count",
        "retained_claim_counts",
        "directly_grounded_claim_counts",
        "missing_required_evidence_counts",
    }

    assert issubclass(EvidenceVerificationDiagnosticsView, BaseModel)
    assert required_fields <= EvidenceVerificationDiagnosticsView.model_fields.keys()
    assert EvidenceVerificationDiagnosticsView.model_config.get("extra") == "forbid"
    assert EvidenceVerificationDiagnosticsView.model_config.get("frozen") is True

    schema_fields = _schema_property_names(EvidenceVerificationDiagnosticsView.model_json_schema())
    # `identity` is intentionally a safe aggregate missing-gate key; identity-bearing
    # source fields remain forbidden.
    forbidden_fields = {
        "supervisor_id",
        "supervisor_name",
        "full_name",
        "prospective_supervisor",
        "candidate_id",
        "candidate_profile",
        "query",
        "source_url",
        "url",
        "source_reference",
        "snippet",
        "claim",
        "claim_text",
        "supporting_excerpt",
        "page_content",
        "checkpoint_token",
        "thread_id",
        "provider_payload",
        "exception_text",
    }
    assert forbidden_fields.isdisjoint(schema_fields)
    assert not any(
        "draft" in field_name or "grounding_reason" in field_name for field_name in schema_fields
    )

    app_source = (PROJECT_ROOT / "src/ui/app.py").read_text(encoding="utf-8").casefold()
    assert "evidence-verification diagnostics" in app_source


def test_m13_1_count_breakdowns_mirror_only_existing_safe_taxonomies() -> None:
    assert set(EvidenceExtractionFailureCountsView.model_fields) == {
        category.value for category in ContentExtractionErrorCategory
    }
    assert set(EvidenceClaimTypeCountsView.model_fields) == {
        claim_type.value for claim_type in EvidenceClaimType
    }
    assert set(MissingRequiredEvidenceCountsView.model_fields) == {
        "identity",
        "current_affiliation",
        "research_interest_or_publication",
    }


def test_m13_1_is_a_read_only_ui_projection_of_existing_graph_records() -> None:
    assert {
        "evidence_extraction_attempts",
        "verification_records",
    } <= ScholarPathState.__required_keys__
    assert "evidence_verification_diagnostics" not in ScholarPathState.__required_keys__

    snapshot_annotation = UiRunSnapshot.model_fields["evidence_verification_diagnostics"].annotation
    assert EvidenceVerificationDiagnosticsView in get_args(snapshot_annotation)
    assert "alternate_source_diagnostics" in UiRunSnapshot.model_fields

    parameters = inspect.signature(_evidence_verification_diagnostics).parameters
    type_hints = get_type_hints(_evidence_verification_diagnostics)
    assert tuple(parameters) == ("state",)
    assert type_hints["state"] is ScholarPathState


def test_m13_1_keeps_verification_thresholds_and_routes_unchanged() -> None:
    policy = VerificationPolicy()
    route_parameters = inspect.signature(route_after_evidence_sufficiency).parameters

    assert policy.minimum_verified_supervisors == 5
    assert policy.maximum_alternate_source_retries == 1
    assert {route.value for route in EvidenceVerificationRoute} == {
        "retry_alternate_evidence_source",
        "evaluate_research_fit",
        "__end__",
    }
    assert {
        "policy",
        "verification_records",
        "alternate_retry_count",
    } <= route_parameters.keys()
    assert "diagnostics" not in route_parameters
