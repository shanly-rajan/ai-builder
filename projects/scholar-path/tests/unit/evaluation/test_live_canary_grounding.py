"""Call-local grounding summaries survive stopped canaries without source payloads."""

import json

import pytest

from scholarpath.agents.evidence_verification import (
    EvidenceModelInvocationError,
    EvidenceModelOutputError,
    StructuredEvidenceExtractionResult,
)
from scholarpath.agents.research_fit import (
    ResearchFitEvaluationError,
    ResearchFitModelInvocationError,
)
from scholarpath.domain import EvidenceClaimType
from tests.fakes import (
    FakeEvidenceVerificationModel,
    FakeResearchFitModel,
    make_complete_evidence_response,
)
from tests.fixtures import COMPLETE_PROFILE_URL
from tests.integration import test_m13_live_canary as canary
from tests.unit.evaluation.test_live_canary_verification import PRIVATE, _exercise_pipeline


@pytest.mark.parametrize("error_type", [EvidenceModelInvocationError, EvidenceModelOutputError])
def test_unavailable_extraction_keeps_grounding_summary_null_and_errors_private(
    error_type: type[Exception],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: error_type(PRIVATE)})
    fit_model = FakeResearchFitModel()

    with pytest.raises(error_type), canary._summarized_call_budget() as budget:
        _exercise_pipeline(budget, model, fit_model, monkeypatch)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["grounding_diagnostics"] is None
    assert summary["verification_diagnostics"] is None
    assert summary["total_provider_calls"] == model.call_count == 1
    assert fit_model.call_count == 0
    assert PRIVATE not in captured.out + captured.err


def test_strict_failure_reports_original_support_rejection_without_extra_calls(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    response = make_complete_evidence_response()
    response = StructuredEvidenceExtractionResult(
        claims=[
            draft.model_copy(update={"directly_supported": False})
            if draft.claim_type is EvidenceClaimType.CURRENT_AFFILIATION
            else draft
            for draft in response.claims
        ]
    )
    model = FakeEvidenceVerificationModel({COMPLETE_PROFILE_URL: response})
    fit_model = FakeResearchFitModel()

    with (
        pytest.raises(canary._MissingRequiredEvidenceError),
        canary._summarized_call_budget() as budget,
    ):
        _exercise_pipeline(budget, model, fit_model, monkeypatch)

    summary = json.loads(capsys.readouterr().out)
    grounding = summary["grounding_diagnostics"]
    assert grounding["rejection_counts"]["current_affiliation"] == {
        "model_not_directly_supported": 1
    }
    assert grounding["retained_claim_counts"]["current_affiliation"] == 1
    assert grounding["grounded_claim_counts"]["current_affiliation"] == 0
    assert summary["verification_diagnostics"]["missing_required_evidence"] == [
        "current_affiliation"
    ]
    assert summary["total_provider_calls"] == model.call_count == 1
    assert fit_model.call_count == 0


def test_successful_pipeline_reports_grounding_without_extra_provider_calls(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeEvidenceVerificationModel()
    fit_model = FakeResearchFitModel()

    with canary._summarized_call_budget() as budget:
        verified, _ = _exercise_pipeline(budget, model, fit_model, monkeypatch)

    summary = json.loads(capsys.readouterr().out)
    grounding = summary["grounding_diagnostics"]
    assert grounding["grounded_claim_counts"] == grounding["retained_claim_counts"]
    assert all(not reasons for reasons in grounding["rejection_counts"].values())
    assert (
        grounding["retained_claim_counts"]
        == summary["verification_diagnostics"]["retained_claim_counts"]
    )
    assert sum(grounding["retained_claim_counts"].values()) == len(verified.evidence)
    assert model.call_count == fit_model.call_count == 1
    assert summary["total_provider_calls"] == 2


def test_completed_empty_extraction_reports_zeros_not_unavailable(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeEvidenceVerificationModel(
        {COMPLETE_PROFILE_URL: StructuredEvidenceExtractionResult(claims=[])}
    )
    fit_model = FakeResearchFitModel()

    with (
        pytest.raises(canary._MissingRequiredEvidenceError),
        canary._summarized_call_budget() as budget,
    ):
        _exercise_pipeline(budget, model, fit_model, monkeypatch)

    summary = json.loads(capsys.readouterr().out)
    grounding = summary["grounding_diagnostics"]
    assert grounding is not None
    assert sum(grounding["retained_claim_counts"].values()) == 0
    assert sum(grounding["grounded_claim_counts"].values()) == 0
    assert all(not reasons for reasons in grounding["rejection_counts"].values())
    assert summary["total_provider_calls"] == model.call_count == 1
    assert fit_model.call_count == 0


def test_later_fit_failure_preserves_completed_grounding_summary(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    model = FakeEvidenceVerificationModel()
    fit_model = FakeResearchFitModel({"supervisor-001": [ResearchFitModelInvocationError(PRIVATE)]})

    with pytest.raises(ResearchFitEvaluationError), canary._summarized_call_budget() as budget:
        _exercise_pipeline(budget, model, fit_model, monkeypatch)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["grounding_diagnostics"] is not None
    assert summary["grounding_diagnostics"]["grounded_claim_counts"]["identity"] == 1
    assert summary["stage_outcomes"]["research_fit_evaluation"]["failure_category"] == (
        "model_invocation"
    )
    assert model.call_count == fit_model.call_count == 1
    assert summary["total_provider_calls"] == 2
    assert PRIVATE not in captured.out + captured.err
