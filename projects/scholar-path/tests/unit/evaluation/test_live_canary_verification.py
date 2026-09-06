"""Offline verification diagnostics reveal missing gates, never evidence payloads."""

import json

import pytest

from scholarpath.agents.evidence_verification import (
    EvidenceModelInvocationError,
    EvidenceModelOutputError,
    EvidenceVerificationAgent,
    StructuredEvidenceExtractionResult,
)
from scholarpath.agents.research_fit import (
    ResearchFitEvaluationError,
    ResearchFitModelInvocationError,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    ResearchFitAssessment,
    SourceKind,
    SupervisorVerificationRecord,
    VerificationEvidenceStandard,
    VerifiedSupervisor,
    evidence_claim_is_grounded_for_supervisor,
)
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeResearchFitModel,
    make_complete_evidence_response,
)
from tests.fixtures import (
    COMPLETE_PROFILE_URL,
    make_candidate_profile,
    make_evidence_claims,
    make_prospective_supervisor,
)
from tests.integration import test_m13_live_canary as canary

PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"
GATES = ("identity", "current_affiliation", "research_interest_or_publication")


def _record(evidence: tuple[EvidenceClaim, ...] | None = None) -> SupervisorVerificationRecord:
    return EvidenceVerificationAgent(FakeEvidenceVerificationModel()).build_verification_record(
        make_prospective_supervisor(1),
        make_evidence_claims(1) if evidence is None else evidence,
    )


def _exercise_pipeline(
    budget: canary._CallBudget,
    evidence_model: FakeEvidenceVerificationModel,
    fit_model: FakeResearchFitModel,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[VerifiedSupervisor, ResearchFitAssessment]:
    # Reserved fixture URLs do not have real academic suffixes. Source classification
    # has independent tests; this suite exercises verification and its safe projection.
    monkeypatch.setattr(
        canary,
        "classify_evidence_source_kind",
        lambda *args, **kwargs: SourceKind.UNIVERSITY_PROFILE,
    )
    return canary._verify_and_evaluate(
        profile=make_candidate_profile(),
        prospective=make_prospective_supervisor(1),
        extracted_content=FakeContentExtraction().extract(COMPLETE_PROFILE_URL),
        evidence_model=canary._BudgetedEvidenceModel(evidence_model, budget),
        research_fit_model=canary._BudgetedResearchFitModel(fit_model, budget),
        budget=budget,
    )


def test_complete_record_reports_fixed_categories_without_private_content() -> None:
    record = _record()

    summary = canary._verification_diagnostics(record)

    assert summary["verification_standard"] == VerificationEvidenceStandard.STRICT.value
    assert summary["missing_required_evidence"] == []
    assert summary["unrecognized_missing_category_count"] == 0
    for field in ("retained_claim_counts", "grounded_claim_counts"):
        assert set(summary[field]) == {claim_type.value for claim_type in EvidenceClaimType}
    assert summary["retained_claim_counts"] == summary["grounded_claim_counts"]
    assert sum(summary["retained_claim_counts"].values()) == len(record.evidence)
    assert record.availability_status is AvailabilityStatus.NOT_STATED
    serialized = json.dumps(summary)
    assert record.prospective_supervisor.full_name not in serialized
    assert record.prospective_supervisor.supervisor_id not in serialized
    for claim in record.evidence:
        assert claim.claim not in serialized
        assert claim.evidence_id not in serialized
        assert str(claim.source_url) not in serialized


@pytest.mark.parametrize(
    ("excluded", "expected"),
    [
        ({EvidenceClaimType.IDENTITY}, [GATES[0]]),
        ({EvidenceClaimType.CURRENT_AFFILIATION}, [GATES[1]]),
        ({EvidenceClaimType.RESEARCH_INTEREST, EvidenceClaimType.PUBLICATION}, [GATES[2]]),
        (
            {
                EvidenceClaimType.CURRENT_AFFILIATION,
                EvidenceClaimType.RESEARCH_INTEREST,
                EvidenceClaimType.PUBLICATION,
            },
            list(GATES[1:]),
        ),
        (set(EvidenceClaimType), list(GATES)),
    ],
)
def test_missing_gate_names_match_existing_verifier(
    excluded: set[EvidenceClaimType], expected: list[str]
) -> None:
    record = _record(tuple(c for c in make_evidence_claims(1) if c.claim_type not in excluded))

    summary = canary._verification_diagnostics(record)

    assert record.verified_supervisor is None
    assert list(record.missing_required_evidence) == expected
    assert summary["missing_required_evidence"] == expected
    assert summary["unrecognized_missing_category_count"] == 0
    for claim_type in excluded:
        assert summary["retained_claim_counts"][claim_type.value] == 0
        assert summary["grounded_claim_counts"][claim_type.value] == 0


def test_unknown_categories_and_standard_never_leak_raw_values() -> None:
    original = _record()
    # Deliberately bypass domain validation to test the diagnostic allowlist itself.
    malformed = SupervisorVerificationRecord.model_construct(
        **{
            **original.model_dump(mode="python"),
            "prospective_supervisor": original.prospective_supervisor,
            "evidence": original.evidence,
            "missing_required_evidence": (PRIVATE, "identity", PRIVATE),
            "verification_evidence_standard": PRIVATE,
            "verification_concerns": (PRIVATE,),
        }
    )

    summary = canary._verification_diagnostics(malformed)

    assert summary["verification_standard"] is None
    assert summary["missing_required_evidence"] == ["identity"]
    assert summary["unrecognized_missing_category_count"] == 2
    assert PRIVATE not in json.dumps(summary)


def test_gate_order_is_canonical_and_duplicate_names_are_removed() -> None:
    original = _record(())
    # Unordered duplicate gates cannot enter a valid domain record; check defensively.
    unordered = SupervisorVerificationRecord.model_construct(
        **{
            **original.model_dump(mode="python"),
            "prospective_supervisor": original.prospective_supervisor,
            "evidence": original.evidence,
            "missing_required_evidence": (*reversed(GATES), "identity", "current_affiliation"),
        }
    )

    summary = canary._verification_diagnostics(unordered)

    assert summary["missing_required_evidence"] == list(GATES)
    assert summary["unrecognized_missing_category_count"] == 0


def test_grounded_counts_use_domain_checks_not_only_direct_support_flag() -> None:
    original = _record()
    identity = original.evidence[0]
    # A corrupt claim still marked direct must not inflate the grounded diagnostic.
    ungrounded = EvidenceClaim.model_construct(
        **{**identity.model_dump(mode="python"), "supporting_excerpt": PRIVATE}
    )
    malformed = SupervisorVerificationRecord.model_construct(
        **{
            **original.model_dump(mode="python"),
            "prospective_supervisor": original.prospective_supervisor,
            "evidence": (ungrounded,),
        }
    )

    summary = canary._verification_diagnostics(malformed)

    assert ungrounded.directly_supported
    assert summary["retained_claim_counts"]["identity"] == 1
    assert summary["grounded_claim_counts"]["identity"] == 0
    assert PRIVATE not in json.dumps(summary)


def test_contextual_claim_grounding_receives_complete_evidence_collection() -> None:
    identity, _, research = make_evidence_claims(1)[:3]
    profile_url = "https://profiles.example.edu/amara-ndlovu"
    identity = identity.model_copy(
        update={"source_url": profile_url, "source_kind": SourceKind.UNIVERSITY_PROFILE}
    )
    research = research.model_copy(
        update={
            "source_url": profile_url,
            "source_kind": SourceKind.UNIVERSITY_PROFILE,
            "retrieved_at": identity.retrieved_at,
            "subject_identity_evidence_id": identity.evidence_id,
            "supporting_excerpt": "Research interests: enterprise architecture and AI governance.",
        }
    )
    record = _record((identity, research))
    assert not evidence_claim_is_grounded_for_supervisor(research, record.prospective_supervisor)
    assert evidence_claim_is_grounded_for_supervisor(
        research, record.prospective_supervisor, record.evidence
    )

    summary = canary._verification_diagnostics(record)

    assert summary["retained_claim_counts"]["research_interest"] == 1
    assert summary["grounded_claim_counts"]["research_interest"] == 1
    assert summary["missing_required_evidence"] == ["current_affiliation"]


@pytest.mark.parametrize("error_type", [EvidenceModelInvocationError, EvidenceModelOutputError])
def test_extraction_failure_keeps_verification_diagnostics_unavailable(
    error_type: type[Exception],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    evidence_model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: error_type(PRIVATE)})
    fit_model = FakeResearchFitModel()

    with pytest.raises(error_type), canary._summarized_call_budget() as budget:
        _exercise_pipeline(budget, evidence_model, fit_model, monkeypatch)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["verification_diagnostics"] is None
    assert summary["provider_calls"]["openai_evidence"] == 1
    assert summary["provider_calls"]["openai_research_fit"] == 0
    assert PRIVATE not in captured.out + captured.err


@pytest.mark.parametrize("gate", GATES)
def test_pipeline_preserves_missing_gates_before_stopping_without_fit_call(
    gate: str,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    excluded = (
        {
            EvidenceClaimType.RESEARCH_INTEREST,
            EvidenceClaimType.PUBLICATION,
            EvidenceClaimType.PROJECT,
        }
        if gate == GATES[2]
        else {EvidenceClaimType(gate)}
    )
    response = StructuredEvidenceExtractionResult(
        claims=[c for c in make_complete_evidence_response().claims if c.claim_type not in excluded]
    )
    evidence_model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    fit_model = FakeResearchFitModel()

    with (
        pytest.raises(canary._MissingRequiredEvidenceError),
        canary._summarized_call_budget() as budget,
    ):
        _exercise_pipeline(budget, evidence_model, fit_model, monkeypatch)

    summary = json.loads(capsys.readouterr().out)
    diagnostics = summary["verification_diagnostics"]
    assert diagnostics is not None
    # Without an extracted identity, the existing agent also demotes dependent claims.
    assert gate in diagnostics["missing_required_evidence"]
    assert summary["stage_outcomes"]["evidence_verification"]["failure_category"] == (
        "missing_required_evidence"
    )
    assert fit_model.call_count == 0
    assert summary["provider_calls"]["openai_research_fit"] == 0
    assert summary["total_provider_calls"] == 1


def test_successful_pipeline_reports_completed_empty_gates_without_extra_calls(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_model = FakeEvidenceVerificationModel()
    fit_model = FakeResearchFitModel()

    with canary._summarized_call_budget() as budget:
        verified, _ = _exercise_pipeline(budget, evidence_model, fit_model, monkeypatch)

    summary = json.loads(capsys.readouterr().out)
    assert summary["verification_diagnostics"]["missing_required_evidence"] == []
    assert summary["verification_diagnostics"]["verification_standard"] == "strict"
    assert verified.availability_status is AvailabilityStatus.NOT_STATED
    assert evidence_model.call_count == fit_model.call_count == 1
    assert summary["total_provider_calls"] == 2
    assert sum(canary._LIVE_CALL_LIMITS.values()) == 9


def test_later_fit_failure_does_not_erase_completed_verification_diagnostics(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    evidence_model = FakeEvidenceVerificationModel()
    fit_model = FakeResearchFitModel({"supervisor-001": [ResearchFitModelInvocationError(PRIVATE)]})

    with pytest.raises(ResearchFitEvaluationError), canary._summarized_call_budget() as budget:
        _exercise_pipeline(budget, evidence_model, fit_model, monkeypatch)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["verification_diagnostics"]["missing_required_evidence"] == []
    assert summary["stage_outcomes"]["research_fit_evaluation"]["failure_category"] == (
        "model_invocation"
    )
    assert summary["total_provider_calls"] == 2
    assert PRIVATE not in captured.out + captured.err
