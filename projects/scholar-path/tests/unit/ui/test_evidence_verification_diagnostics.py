"""Focused tests for privacy-safe M13.1 evidence-verification diagnostics."""

import pytest
from pydantic import HttpUrl, ValidationError

from scholarpath.domain import (
    EvidenceClaimType,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationStatus,
)
from scholarpath.graph import EvidenceExtractionAttempt, create_initial_state
from scholarpath.tools import ContentExtractionErrorCategory
from scholarpath.ui.controller import project_graph_state_to_ui
from scholarpath.ui.models import (
    EvidenceClaimTypeCountsView,
    EvidenceExtractionFailureCountsView,
    EvidenceVerificationDiagnosticsView,
)
from tests.fixtures.factories import (
    make_candidate_profile,
    make_evidence_claims,
    make_prospective_supervisor,
    make_verified_supervisor,
)


def _completed_record(index: int) -> SupervisorVerificationRecord:
    prospective = make_prospective_supervisor(index)
    verified = make_verified_supervisor(index)
    return SupervisorVerificationRecord(
        prospective_supervisor=prospective,
        evidence=verified.evidence,
        verification_status=verified.verification_status,
        availability_status=verified.availability_status,
        verification_concerns=verified.verification_concerns,
        verified_supervisor=verified,
    )


def _partial_record(
    index: int,
    *,
    retain_identity: bool,
) -> SupervisorVerificationRecord:
    evidence = (make_evidence_claims(index)[0],) if retain_identity else ()
    missing = (
        (EvidenceClaimType.CURRENT_AFFILIATION.value, "research_interest_or_publication")
        if retain_identity
        else (
            EvidenceClaimType.IDENTITY.value,
            EvidenceClaimType.CURRENT_AFFILIATION.value,
            "research_interest_or_publication",
        )
    )
    return SupervisorVerificationRecord(
        prospective_supervisor=make_prospective_supervisor(index),
        evidence=evidence,
        verification_status=VerificationStatus.PARTIALLY_VERIFIED,
        missing_required_evidence=missing,
    )


def test_projection_aggregates_only_current_round_and_omits_sensitive_content() -> None:
    private_statement = "Secret Candidate research direction"
    state = create_initial_state(
        make_candidate_profile(proposed_research_statement=private_statement)
    )
    state["discovery_round"] = 2
    state["evidence_extraction_attempts"] = [
        EvidenceExtractionAttempt(
            supervisor_id="older-private-supervisor",
            source_url=HttpUrl("https://older-private.example/profile"),
            source_kind=SourceKind.UNIVERSITY_PROFILE,
            attempt_number=1,
            discovery_round=1,
            alternate_source=False,
            successful=False,
            error_category=ContentExtractionErrorCategory.AUTHENTICATION,
        ),
        EvidenceExtractionAttempt(
            supervisor_id="current-completed-supervisor",
            source_url=HttpUrl("https://private.example/primary-success"),
            source_kind=SourceKind.UNIVERSITY_PROFILE,
            attempt_number=1,
            discovery_round=2,
            alternate_source=False,
            successful=True,
        ),
        EvidenceExtractionAttempt(
            supervisor_id="current-partial-supervisor-one",
            source_url=HttpUrl("https://private.example/primary-failure"),
            source_kind=SourceKind.UNIVERSITY_PROFILE,
            attempt_number=1,
            discovery_round=2,
            alternate_source=False,
            successful=False,
            error_category=ContentExtractionErrorCategory.TIMEOUT,
        ),
        EvidenceExtractionAttempt(
            supervisor_id="current-partial-supervisor-one",
            source_url=HttpUrl("https://private.example/alternate-success"),
            source_kind=SourceKind.DEPARTMENT_PAGE,
            attempt_number=2,
            discovery_round=2,
            alternate_source=True,
            successful=True,
        ),
        EvidenceExtractionAttempt(
            supervisor_id="current-partial-supervisor-two",
            source_url=HttpUrl("https://private.example/alternate-failure"),
            source_kind=SourceKind.INSTITUTIONAL_DIRECTORY,
            attempt_number=2,
            discovery_round=2,
            alternate_source=True,
            successful=False,
            error_category=ContentExtractionErrorCategory.PROVIDER,
        ),
    ]
    completed_record = _completed_record(6)
    identity_partial_record = _partial_record(1, retain_identity=True)
    empty_partial_record = _partial_record(2, retain_identity=False)
    state["verification_records"] = [
        completed_record,
        identity_partial_record,
        empty_partial_record,
    ]

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-safe-evidence-diagnostics",
        review_payload=None,
    )
    replayed_snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-safe-evidence-diagnostics",
        review_payload=None,
    )

    diagnostics = snapshot.evidence_verification_diagnostics
    assert diagnostics is not None
    assert replayed_snapshot.evidence_verification_diagnostics == diagnostics
    assert (
        diagnostics.primary_retrieval_attempt_count,
        diagnostics.primary_retrieval_success_count,
        diagnostics.primary_retrieval_failure_count,
    ) == (2, 1, 1)
    assert (
        diagnostics.alternate_retrieval_attempt_count,
        diagnostics.alternate_retrieval_success_count,
        diagnostics.alternate_retrieval_failure_count,
    ) == (2, 1, 1)
    assert diagnostics.extraction_failure_counts.timeout == 1
    assert diagnostics.extraction_failure_counts.provider == 1
    assert diagnostics.extraction_failure_counts.authentication == 0
    assert diagnostics.extraction_failure_counts.total == 2
    assert diagnostics.verification_record_count == 3
    assert diagnostics.completed_verification_record_count == 1
    assert diagnostics.partial_verification_record_count == 2
    assert diagnostics.retained_claim_counts == EvidenceClaimTypeCountsView(
        identity=2,
        current_affiliation=1,
        research_interest=2,
        methodology=1,
        publication=1,
    )
    assert diagnostics.directly_grounded_claim_counts == EvidenceClaimTypeCountsView(
        identity=2,
        current_affiliation=1,
        research_interest=1,
        methodology=1,
        publication=1,
    )
    assert diagnostics.missing_required_evidence_counts.identity == 1
    assert diagnostics.missing_required_evidence_counts.current_affiliation == 2
    assert diagnostics.missing_required_evidence_counts.research_interest_or_publication == 2

    rendered = snapshot.model_dump_json()
    for forbidden in (
        private_statement,
        "older-private-supervisor",
        "current-completed-supervisor",
        "current-partial-supervisor-one",
        "current-partial-supervisor-two",
        "https://older-private.example/profile",
        "https://private.example/primary-success",
        completed_record.prospective_supervisor.supervisor_id,
        completed_record.prospective_supervisor.full_name,
        str(completed_record.evidence[0].source_url),
        completed_record.evidence[0].claim,
        completed_record.evidence[0].supporting_excerpt,
        identity_partial_record.prospective_supervisor.full_name,
        "supporting_excerpt",
        "originating_query",
    ):
        assert forbidden is not None
        assert forbidden not in rendered


def test_empty_pre_evidence_state_does_not_infer_diagnostic_zeros() -> None:
    state = create_initial_state(make_candidate_profile())

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-before-evidence",
        review_payload=None,
    )

    assert snapshot.evidence_verification_diagnostics is None


def test_verified_with_concerns_is_an_explicit_completed_outcome() -> None:
    state = create_initial_state(make_candidate_profile())
    state["discovery_round"] = 1
    state["verification_records"] = [_completed_record(3)]

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="checkpoint-completed-with-concerns",
        review_payload=None,
    )

    diagnostics = snapshot.evidence_verification_diagnostics
    assert diagnostics is not None
    assert diagnostics.completed_verification_record_count == 1
    assert diagnostics.partial_verification_record_count == 0


def test_fixed_count_models_cover_existing_typed_taxonomies_exactly() -> None:
    assert set(EvidenceExtractionFailureCountsView.model_fields) == {
        category.value for category in ContentExtractionErrorCategory
    }
    assert set(EvidenceClaimTypeCountsView.model_fields) == {
        claim_type.value for claim_type in EvidenceClaimType
    }


@pytest.mark.parametrize(
    "overrides",
    [
        {"primary_retrieval_attempt_count": 2},
        {"extraction_failure_counts": {"timeout": 1}},
        {"verification_record_count": 2},
        {"directly_grounded_claim_counts": {"identity": 1}},
        {
            "missing_required_evidence_counts": {
                "identity": 2,
                "current_affiliation": 1,
                "research_interest_or_publication": 1,
            }
        },
        {"missing_required_evidence_counts": {}},
        {
            "primary_retrieval_attempt_count": 0,
            "primary_retrieval_success_count": 0,
            "verification_record_count": 0,
            "partial_verification_record_count": 0,
            "missing_required_evidence_counts": {},
        },
        {
            "verification_record_count": 1,
            "completed_verification_record_count": 1,
            "partial_verification_record_count": 0,
            "retained_claim_counts": {},
            "directly_grounded_claim_counts": {},
            "missing_required_evidence_counts": {},
        },
    ],
)
def test_diagnostic_view_rejects_inconsistent_aggregate_counts(
    overrides: dict[str, object],
) -> None:
    valid: dict[str, object] = {
        "primary_retrieval_attempt_count": 1,
        "primary_retrieval_success_count": 1,
        "primary_retrieval_failure_count": 0,
        "alternate_retrieval_attempt_count": 0,
        "alternate_retrieval_success_count": 0,
        "alternate_retrieval_failure_count": 0,
        "extraction_failure_counts": {},
        "verification_record_count": 1,
        "completed_verification_record_count": 0,
        "partial_verification_record_count": 1,
        "retained_claim_counts": {},
        "directly_grounded_claim_counts": {},
        "missing_required_evidence_counts": {
            "identity": 1,
            "current_affiliation": 1,
            "research_interest_or_publication": 1,
        },
    }

    with pytest.raises(ValidationError):
        EvidenceVerificationDiagnosticsView.model_validate({**valid, **overrides})


def test_diagnostic_contract_rejects_unknown_or_content_bearing_fields() -> None:
    valid = {
        "primary_retrieval_attempt_count": 1,
        "primary_retrieval_success_count": 0,
        "primary_retrieval_failure_count": 1,
        "alternate_retrieval_attempt_count": 0,
        "alternate_retrieval_success_count": 0,
        "alternate_retrieval_failure_count": 0,
        "extraction_failure_counts": {"timeout": 1},
        "verification_record_count": 0,
        "completed_verification_record_count": 0,
        "partial_verification_record_count": 0,
        "retained_claim_counts": {},
        "directly_grounded_claim_counts": {},
        "missing_required_evidence_counts": {},
    }

    with pytest.raises(ValidationError):
        EvidenceVerificationDiagnosticsView.model_validate(
            {
                **valid,
                "source_url": "https://private.example/profile",
                "supervisor_id": "private-supervisor",
            }
        )
