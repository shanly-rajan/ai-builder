"""Offline stage diagnostics distinguish local evidence gates from model failures."""

import json
from typing import cast

import pytest
from pydantic import ValidationError

from scholarpath.agents.evidence_verification import (
    EvidenceModelInvocationError,
    EvidenceModelOutputError,
    StructuredEvidenceExtractionResult,
)
from scholarpath.agents.research_fit import (
    ResearchFitEvaluationError,
    ResearchFitFailureKind,
    ResearchFitModelInvocationError,
    ResearchFitModelOutputError,
)
from scholarpath.domain import (
    AvailabilityStatus,
    CandidateProfile,
    EvidenceClaimType,
    ResearchFitAssessment,
    SourceKind,
    VerifiedSupervisor,
)
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeResearchFitModel,
    make_complete_evidence_response,
)
from tests.fixtures import COMPLETE_PROFILE_URL, make_candidate_profile, make_prospective_supervisor
from tests.integration import test_m13_live_canary as canary

PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"


@pytest.fixture(autouse=True)
def _official_fixture_source(monkeypatch: pytest.MonkeyPatch) -> None:
    # Reserved .example fixtures have no real academic suffix. Classification has
    # separate tests; these cases exercise the evidence and diagnostic boundaries.
    monkeypatch.setattr(
        canary,
        "classify_evidence_source_kind",
        lambda *args, **kwargs: SourceKind.UNIVERSITY_PROFILE,
    )


def _exercise_pipeline(
    budget: canary._CallBudget,
    evidence_model: FakeEvidenceVerificationModel,
    fit_model: FakeResearchFitModel,
    *,
    profile: CandidateProfile | None = None,
) -> tuple[VerifiedSupervisor, ResearchFitAssessment]:
    return canary._verify_and_evaluate(
        profile=profile or make_candidate_profile(),
        prospective=make_prospective_supervisor(1),
        extracted_content=FakeContentExtraction().extract(COMPLETE_PROFILE_URL),
        evidence_model=canary._BudgetedEvidenceModel(evidence_model, budget),
        research_fit_model=canary._BudgetedResearchFitModel(fit_model, budget),
        budget=budget,
    )


def _assert_stage(
    summary: dict[str, object],
    stage: canary._CanaryStage,
    status: canary._StageStatus,
    category: canary._FailureCategory | None = None,
) -> None:
    stages = summary["stage_outcomes"]
    assert isinstance(stages, dict)
    assert stages[stage.value] == {
        "status": status.value,
        "failure_category": category.value if category is not None else None,
    }


def test_fixed_evidence_completes_all_four_stages_without_live_services(
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence_model = FakeEvidenceVerificationModel()
    fit_model = FakeResearchFitModel()

    with canary._summarized_call_budget() as budget:
        verified, assessment = _exercise_pipeline(budget, evidence_model, fit_model)

    summary = json.loads(capsys.readouterr().out)
    assert evidence_model.call_count == 1
    assert fit_model.call_count == 1
    assert verified.availability_status is AvailabilityStatus.NOT_STATED
    assert assessment.supervisor_id == verified.supervisor_id
    for stage in list(canary._CanaryStage)[:4]:
        _assert_stage(summary, stage, canary._StageStatus.COMPLETED)
    for stage in list(canary._CanaryStage)[4:]:
        _assert_stage(summary, stage, canary._StageStatus.NOT_REACHED)
    assert summary["total_provider_calls"] == 2


@pytest.mark.parametrize(
    "missing",
    [
        EvidenceClaimType.IDENTITY,
        EvidenceClaimType.CURRENT_AFFILIATION,
        EvidenceClaimType.RESEARCH_INTEREST,
    ],
)
def test_missing_required_evidence_stops_before_research_fit(
    missing: EvidenceClaimType,
    capsys: pytest.CaptureFixture[str],
) -> None:
    excluded = {missing}
    if missing is EvidenceClaimType.RESEARCH_INTEREST:
        excluded.update({EvidenceClaimType.PUBLICATION, EvidenceClaimType.PROJECT})
    response = StructuredEvidenceExtractionResult(
        claims=[
            claim
            for claim in make_complete_evidence_response().claims
            if claim.claim_type not in excluded
        ]
    )
    evidence_model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    fit_model = FakeResearchFitModel()

    with (
        pytest.raises(canary._MissingRequiredEvidenceError),
        canary._summarized_call_budget() as budget,
    ):
        _exercise_pipeline(budget, evidence_model, fit_model)

    summary = json.loads(capsys.readouterr().out)
    _assert_stage(summary, canary._CanaryStage.EVIDENCE_EXTRACTION, canary._StageStatus.COMPLETED)
    _assert_stage(
        summary,
        canary._CanaryStage.EVIDENCE_VERIFICATION,
        canary._StageStatus.FAILED,
        canary._FailureCategory.MISSING_REQUIRED_EVIDENCE,
    )
    for stage in (
        canary._CanaryStage.RESEARCH_FIT_INPUT,
        canary._CanaryStage.RESEARCH_FIT_EVALUATION,
    ):
        _assert_stage(summary, stage, canary._StageStatus.NOT_REACHED)
    assert evidence_model.call_count == 1
    assert fit_model.call_count == 0
    assert summary["provider_calls"]["openai_research_fit"] == 0


@pytest.mark.parametrize(
    ("error_type", "category"),
    [
        (EvidenceModelInvocationError, canary._FailureCategory.MODEL_INVOCATION),
        (EvidenceModelOutputError, canary._FailureCategory.INVALID_OUTPUT),
    ],
)
def test_evidence_model_failures_remain_distinct_and_private(
    error_type: type[Exception],
    category: canary._FailureCategory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence_model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: error_type(PRIVATE)})
    fit_model = FakeResearchFitModel()

    with pytest.raises(error_type), canary._summarized_call_budget() as budget:
        _exercise_pipeline(budget, evidence_model, fit_model)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    _assert_stage(
        summary, canary._CanaryStage.EVIDENCE_EXTRACTION, canary._StageStatus.FAILED, category
    )
    for stage in list(canary._CanaryStage)[1:]:
        _assert_stage(summary, stage, canary._StageStatus.NOT_REACHED)
    assert evidence_model.call_count == 1
    assert fit_model.call_count == 0
    assert PRIVATE not in captured.out + captured.err


def test_research_fit_input_validation_failure_makes_no_model_call(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Deliberately bypass domain validation to exercise a corrupted local boundary.
    profile = CandidateProfile.model_construct(
        **{**make_candidate_profile().model_dump(mode="python"), "research_topics": ()}
    )
    evidence_model = FakeEvidenceVerificationModel()
    fit_model = FakeResearchFitModel()

    with pytest.raises(ValidationError), canary._summarized_call_budget() as budget:
        _exercise_pipeline(budget, evidence_model, fit_model, profile=profile)

    summary = json.loads(capsys.readouterr().out)
    for stage in (
        canary._CanaryStage.EVIDENCE_EXTRACTION,
        canary._CanaryStage.EVIDENCE_VERIFICATION,
    ):
        _assert_stage(summary, stage, canary._StageStatus.COMPLETED)
    _assert_stage(
        summary,
        canary._CanaryStage.RESEARCH_FIT_INPUT,
        canary._StageStatus.FAILED,
        canary._FailureCategory.INPUT_VALIDATION,
    )
    _assert_stage(
        summary, canary._CanaryStage.RESEARCH_FIT_EVALUATION, canary._StageStatus.NOT_REACHED
    )
    assert fit_model.call_count == 0
    assert summary["provider_calls"]["openai_research_fit"] == 0


@pytest.mark.parametrize(
    ("error_type", "failure", "category", "attempts"),
    [
        (
            ResearchFitModelInvocationError,
            ResearchFitFailureKind.MODEL_INVOCATION,
            canary._FailureCategory.MODEL_INVOCATION,
            1,
        ),
        (
            ResearchFitModelOutputError,
            ResearchFitFailureKind.INVALID_OUTPUT,
            canary._FailureCategory.INVALID_OUTPUT,
            2,
        ),
    ],
)
def test_research_fit_failure_categories_preserve_existing_retry_limits(
    error_type: type[Exception],
    failure: ResearchFitFailureKind,
    category: canary._FailureCategory,
    attempts: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    evidence_model = FakeEvidenceVerificationModel()
    fit_model = FakeResearchFitModel(
        {"supervisor-001": [error_type(PRIVATE) for _ in range(attempts)]}
    )

    with (
        pytest.raises(ResearchFitEvaluationError) as captured_error,
        canary._summarized_call_budget() as budget,
    ):
        _exercise_pipeline(budget, evidence_model, fit_model)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert captured_error.value.kind is failure
    assert captured_error.value.attempts == attempts
    assert fit_model.call_count == attempts
    assert summary["provider_calls"]["openai_research_fit"] == attempts
    for stage in list(canary._CanaryStage)[:3]:
        _assert_stage(summary, stage, canary._StageStatus.COMPLETED)
    _assert_stage(
        summary, canary._CanaryStage.RESEARCH_FIT_EVALUATION, canary._StageStatus.FAILED, category
    )
    for stage in list(canary._CanaryStage)[4:]:
        _assert_stage(summary, stage, canary._StageStatus.NOT_REACHED)
    assert PRIVATE not in captured.out + captured.err


@pytest.mark.parametrize(
    ("stage", "error_type", "category"),
    [
        (
            canary._CanaryStage.EVIDENCE_VERIFICATION,
            ValueError,
            canary._FailureCategory.VERIFICATION_CONTRACT,
        ),
        (
            canary._CanaryStage.EVIDENCE_VERIFICATION,
            EvidenceModelOutputError,
            canary._FailureCategory.VERIFICATION_CONTRACT,
        ),
        (
            canary._CanaryStage.RESEARCH_FIT_INPUT,
            ValueError,
            canary._FailureCategory.INPUT_VALIDATION,
        ),
        (
            canary._CanaryStage.EVIDENCE_EXTRACTION,
            ValueError,
            canary._FailureCategory.LOCAL_VALIDATION,
        ),
        (
            canary._CanaryStage.EVIDENCE_EXTRACTION,
            RuntimeError,
            canary._FailureCategory.UNEXPECTED_FAILURE,
        ),
    ],
)
def test_stage_observation_rethrows_original_error_without_disclosing_payload(
    stage: canary._CanaryStage,
    error_type: type[Exception],
    category: canary._FailureCategory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = error_type(PRIVATE)
    failure.__cause__ = RuntimeError(PRIVATE)

    with (
        pytest.raises(error_type) as captured_error,
        canary._summarized_call_budget() as budget,
        budget.observe(stage),
    ):
        raise failure

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert captured_error.value is failure
    _assert_stage(summary, stage, canary._StageStatus.FAILED, category)
    assert summary["total_provider_calls"] == 0
    assert PRIVATE not in captured.out + captured.err


def test_unreached_stages_are_not_reported_as_success(capsys: pytest.CaptureFixture[str]) -> None:
    with canary._summarized_call_budget():
        pass

    summary = json.loads(capsys.readouterr().out)
    for stage in canary._CanaryStage:
        _assert_stage(summary, stage, canary._StageStatus.NOT_REACHED)
    assert summary["total_provider_calls"] == 0


def test_malformed_evidence_payload_is_rejected_by_real_agent_validation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Simulate malformed provider data, not a trusted, already validated instance.
    malformed = StructuredEvidenceExtractionResult.model_construct(claims=PRIVATE)
    wire_payload = malformed.model_dump(mode="python", warnings=False)
    evidence_model = FakeEvidenceVerificationModel(
        {COMPLETE_PROFILE_URL: cast(StructuredEvidenceExtractionResult, wire_payload)}
    )
    fit_model = FakeResearchFitModel()

    with pytest.raises(EvidenceModelOutputError), canary._summarized_call_budget() as budget:
        _exercise_pipeline(budget, evidence_model, fit_model)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    _assert_stage(
        summary,
        canary._CanaryStage.EVIDENCE_EXTRACTION,
        canary._StageStatus.FAILED,
        canary._FailureCategory.INVALID_OUTPUT,
    )
    assert evidence_model.call_count == 1
    assert fit_model.call_count == 0
    assert PRIVATE not in captured.out + captured.err


def test_interruption_preserves_started_state_and_is_not_swallowed(
    capsys: pytest.CaptureFixture[str],
) -> None:
    interruption = KeyboardInterrupt(PRIVATE)
    stage = canary._CanaryStage.EVIDENCE_EXTRACTION

    with (
        pytest.raises(KeyboardInterrupt) as captured_error,
        canary._summarized_call_budget() as budget,
        budget.observe(stage),
    ):
        assert budget.stage_outcomes[stage].status is canary._StageStatus.STARTED
        raise interruption

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert captured_error.value is interruption
    _assert_stage(summary, stage, canary._StageStatus.STARTED)
    assert PRIVATE not in captured.out + captured.err


def test_unknown_stage_is_rejected_with_a_fixed_message(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        pytest.raises(ValueError) as captured_error,
        canary._summarized_call_budget() as budget,
        budget.observe(cast(canary._CanaryStage, PRIVATE)),
    ):
        pytest.fail("An unknown stage must be rejected before its body executes")

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert str(captured_error.value) == "Unknown live canary diagnostic stage"
    for stage in canary._CanaryStage:
        _assert_stage(summary, stage, canary._StageStatus.NOT_REACHED)
    assert PRIVATE not in captured.out + captured.err


def test_unknown_research_fit_failure_kind_uses_safe_fallback(
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = ResearchFitEvaluationError(cast(ResearchFitFailureKind, PRIVATE), attempts=1)

    with (
        pytest.raises(ResearchFitEvaluationError) as captured_error,
        canary._summarized_call_budget() as budget,
        budget.observe(canary._CanaryStage.RESEARCH_FIT_EVALUATION),
    ):
        raise failure

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert captured_error.value is failure
    _assert_stage(
        summary,
        canary._CanaryStage.RESEARCH_FIT_EVALUATION,
        canary._StageStatus.FAILED,
        canary._FailureCategory.UNEXPECTED_FAILURE,
    )
    assert PRIVATE not in captured.out + captured.err
