"""Offline stage checks for the bounded, privacy-safe standalone Nebius smoke."""

import json
from typing import cast

import pytest
from langsmith import tracing_context
from langsmith.run_helpers import get_tracing_context
from pydantic import HttpUrl, SecretStr

from scholarpath.agents.independent_review import (
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewModelOutputError,
    IndependentReviewResult,
    reconcile_research_fit_assessment,
)
from scholarpath.config import NebiusReviewConfiguration, NebiusReviewSettings
from scholarpath.domain import (
    IndependentReviewFailureKind,
    IndependentReviewStatus,
    ReconciledResearchFitAssessment,
)
from tests.fakes import FakeIndependentReviewModel, make_accepted_review, make_revised_review
from tests.fixtures import (
    make_candidate_profile,
    make_research_fit_assessment,
    make_verified_supervisor,
)
from tests.integration import test_nebius_review_live as smoke

_PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"


def _settings(timeout: float = 60.0, *, with_key: bool = True) -> NebiusReviewSettings:
    # Bypass BaseSettings environment sources entirely; these fields are synthetic.
    return NebiusReviewSettings.model_construct(
        api_key=SecretStr("synthetic-not-a-live-key") if with_key else None,
        review_model="synthetic-review-model",
        endpoint=HttpUrl("https://review.example.test/v1/"),
        review_timeout_seconds=timeout,
    )


def _assert_stage(
    summary: dict[str, object], stage: str, status: str, category: str | None = None
) -> None:
    outcomes = summary["stage_outcomes"]
    assert isinstance(outcomes, dict)
    assert outcomes[stage] == {"status": status, "failure_category": category}


def _review_input() -> IndependentReviewInput:
    return IndependentReviewInput.from_domain(
        make_candidate_profile(), make_verified_supervisor(1), make_research_fit_assessment(1)
    )


@pytest.mark.parametrize("revised", [False, True])
def test_fake_review_reaches_all_core_smoke_stages(
    revised: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    expected_input = _review_input()
    outcome = (
        make_revised_review(expected_input, recommended_score=75)
        if revised
        else make_accepted_review(expected_input)
    )
    fake = FakeIndependentReviewModel({expected_input.initial_assessment.supervisor_id: [outcome]})
    original_input_json = expected_input.model_dump_json()
    original_fake = FakeIndependentReviewModel(
        {expected_input.initial_assessment.supervisor_id: [outcome]}
    )
    original_result = original_fake.review(expected_input)
    original_review = reconcile_research_fit_assessment(
        expected_input.verified_supervisor,
        expected_input.initial_assessment,
        original_result,
    )

    with smoke._summarized_smoke() as diagnostics:
        reviewed = smoke._run_review_smoke(fake, diagnostics)

    summary = json.loads(capsys.readouterr().out)
    assert summary["event"] == "nebius_smoke.summary"
    assert summary["review_calls"] == 1
    assert summary["review_status"] == ("revised" if revised else "accepted")
    assert summary["failure_kind"] is None
    assert fake.inputs == [expected_input]
    assert fake.call_count == original_fake.call_count == 1
    assert (
        fake.inputs[0].model_dump_json() == expected_input.model_dump_json() == original_input_json
    )
    assert reviewed == original_review
    assert reviewed.initial_assessment == expected_input.initial_assessment
    assert reviewed.review_status is (
        IndependentReviewStatus.REVISED if revised else IndependentReviewStatus.ACCEPTED
    )
    assert reviewed.effective_score == (
        75 if revised else expected_input.initial_assessment.overall_score
    )
    for stage in smoke._SmokeStage:
        assert summary["stage_outcomes"][stage.value] == {
            "status": "not_reached" if stage is smoke._SmokeStage.CONFIGURATION else "completed",
            "failure_category": None,
        }
    assert summary["token_usage"] is None
    assert summary["cost_usd"] is None
    assert summary["elapsed_seconds"] >= 0
    for private in (
        expected_input.candidate_profile.candidate_id,
        expected_input.candidate_profile.proposed_research_statement,
        expected_input.verified_supervisor.full_name,
        str(expected_input.verified_supervisor.profile_url),
        expected_input.initial_assessment.rationale,
        outcome.critique,
    ):
        assert private not in json.dumps(summary)


@pytest.mark.parametrize(
    ("error_type", "category"),
    [
        (IndependentReviewModelInvocationError, "model_invocation"),
        (IndependentReviewModelOutputError, "invalid_output"),
    ],
)
def test_model_failure_keeps_exception_identity_and_hides_payload(
    error_type: type[Exception], category: str, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = error_type(_PRIVATE)
    fake = FakeIndependentReviewModel({"supervisor-001": [failure]})

    with pytest.raises(error_type) as raised, smoke._summarized_smoke() as diagnostics:
        smoke._run_review_smoke(fake, diagnostics)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert raised.value is failure
    assert fake.call_count == summary["review_calls"] == 1
    _assert_stage(summary, "model_call", "failed", category)
    for stage in ("response_checks", "reconciliation", "final_checks"):
        _assert_stage(summary, stage, "not_reached")
    assert summary["review_status"] is None
    assert summary["failure_kind"] is None
    assert _PRIVATE not in captured.out + captured.err


def test_malformed_returned_mapping_fails_response_checks_not_invocation(
    capsys: pytest.CaptureFixture[str],
) -> None:
    class MalformedModel(FakeIndependentReviewModel):
        def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
            self.inputs.append(review_input)
            return cast(IndependentReviewResult, {"critique": _PRIVATE, "recommended_score": -1})

    fake = MalformedModel()
    with pytest.raises(ValueError), smoke._summarized_smoke() as diagnostics:
        smoke._run_review_smoke(fake, diagnostics)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    _assert_stage(summary, "model_call", "completed")
    _assert_stage(summary, "response_checks", "failed", "invalid_output")
    _assert_stage(summary, "reconciliation", "not_reached")
    assert summary["review_calls"] == fake.call_count == 1
    assert _PRIVATE not in captured.out + captured.err


@pytest.mark.parametrize("reference_field", ["unsupported_claim_ids", "overlooked_evidence_ids"])
def test_invalid_reference_is_reported_before_reconciliation(
    reference_field: str, capsys: pytest.CaptureFixture[str]
) -> None:
    review_input = _review_input()
    response = make_revised_review(review_input, recommended_score=75).model_copy(
        update={reference_field: [_PRIVATE]}
    )
    fake = FakeIndependentReviewModel({"supervisor-001": [response]})
    with pytest.raises(AssertionError), smoke._summarized_smoke() as diagnostics:
        smoke._run_review_smoke(fake, diagnostics)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    _assert_stage(summary, "model_call", "completed")
    _assert_stage(summary, "response_checks", "failed", "invalid_evidence_reference")
    _assert_stage(summary, "reconciliation", "not_reached")
    assert summary["review_calls"] == 1
    assert summary["review_status"] is None
    assert summary["failure_kind"] is None
    assert _PRIVATE not in captured.out + captured.err


def test_unavailable_reconciliation_does_not_pass_final_review_gate(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    review_input = _review_input()
    unavailable = reconcile_research_fit_assessment(
        review_input.verified_supervisor,
        review_input.initial_assessment,
        None,
        failure_kind=IndependentReviewFailureKind.INVALID_OUTPUT,
    )

    def degraded_review(*args: object, **kwargs: object) -> ReconciledResearchFitAssessment:
        return unavailable

    monkeypatch.setattr(smoke, "reconcile_research_fit_assessment", degraded_review)
    fake = FakeIndependentReviewModel()
    with pytest.raises(AssertionError), smoke._summarized_smoke() as diagnostics:
        smoke._run_review_smoke(fake, diagnostics)

    summary = json.loads(capsys.readouterr().out)
    _assert_stage(summary, "response_checks", "completed")
    _assert_stage(summary, "reconciliation", "completed")
    _assert_stage(summary, "final_checks", "failed", "review_not_completed")
    assert summary["review_status"] == "unavailable"
    assert summary["failure_kind"] == "invalid_output"
    assert summary["review_calls"] == fake.call_count == 1


def test_input_failure_prevents_a_review_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = ValueError(_PRIVATE)

    def broken_fixture() -> None:
        raise failure

    monkeypatch.setattr(smoke, "make_candidate_profile", broken_fixture)
    fake = FakeIndependentReviewModel()
    with pytest.raises(ValueError) as raised, smoke._summarized_smoke() as diagnostics:
        smoke._run_review_smoke(fake, diagnostics)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert raised.value is failure
    assert summary["review_calls"] == fake.call_count == 0
    _assert_stage(summary, "review_input", "failed", "input_validation")
    _assert_stage(summary, "model_call", "not_reached")
    assert _PRIVATE not in captured.out + captured.err


def test_reconciliation_failure_keeps_model_success_distinct(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = ValueError(_PRIVATE)

    def broken_reconciliation(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(smoke, "reconcile_research_fit_assessment", broken_reconciliation)
    with pytest.raises(ValueError) as raised, smoke._summarized_smoke() as diagnostics:
        smoke._run_review_smoke(FakeIndependentReviewModel(), diagnostics)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert raised.value is failure
    _assert_stage(summary, "model_call", "completed")
    _assert_stage(summary, "response_checks", "completed")
    _assert_stage(summary, "reconciliation", "failed", "local_validation")
    _assert_stage(summary, "final_checks", "not_reached")
    assert summary["review_status"] is None
    assert _PRIVATE not in captured.out + captured.err


def test_pytest_failure_is_recorded_and_restores_outer_tracing(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = pytest.fail.Exception(_PRIVATE)

    def failed_check(*args: object, **kwargs: object) -> None:
        assert get_tracing_context()["enabled"] is False
        raise failure

    monkeypatch.setattr(smoke, "reconcile_research_fit_assessment", failed_check)
    with tracing_context(enabled=True):
        with (
            pytest.raises(pytest.fail.Exception) as raised,
            smoke._summarized_smoke() as diagnostics,
        ):
            smoke._run_review_smoke(FakeIndependentReviewModel(), diagnostics)
        assert get_tracing_context()["enabled"] is True

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert raised.value is failure
    _assert_stage(summary, "reconciliation", "failed", "check_failed")
    _assert_stage(summary, "final_checks", "not_reached")
    assert _PRIVATE not in captured.out + captured.err


@pytest.mark.parametrize(
    ("error_type", "category"),
    [(AssertionError, "check_failed"), (RuntimeError, "unexpected_failure")],
)
def test_observation_rethrows_without_printing_errors(
    error_type: type[Exception], category: str, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = error_type(_PRIVATE)
    with (
        pytest.raises(error_type) as raised,
        smoke._summarized_smoke() as diagnostics,
        diagnostics.observe(smoke._SmokeStage.RECONCILIATION),
    ):
        raise failure

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert raised.value is failure
    _assert_stage(summary, "reconciliation", "failed", category)
    assert _PRIVATE not in captured.out + captured.err


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_control_flow_exceptions_remain_unclassified(
    error_type: type[BaseException], capsys: pytest.CaptureFixture[str]
) -> None:
    failure = error_type(_PRIVATE)
    with (
        pytest.raises(error_type) as raised,
        smoke._summarized_smoke() as diagnostics,
        diagnostics.observe(smoke._SmokeStage.MODEL_CALL),
    ):
        raise failure

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert raised.value is failure
    _assert_stage(summary, "model_call", "started")
    assert _PRIVATE not in captured.out + captured.err


def test_second_attempt_is_stopped_before_delegate_call(capsys: pytest.CaptureFixture[str]) -> None:
    fake = FakeIndependentReviewModel()
    with pytest.raises(AssertionError), smoke._summarized_smoke() as diagnostics:
        smoke._run_review_smoke(fake, diagnostics)
        smoke._run_review_smoke(fake, diagnostics)

    summary = json.loads(capsys.readouterr().out)
    assert summary["review_calls"] == fake.call_count == 1
    _assert_stage(summary, "model_call", "failed", "call_limit")


@pytest.mark.parametrize(("configured", "expected"), [(7.0, 7.0), (60.0, 60.0), (120.0, 60.0)])
def test_timeout_is_capped_without_changing_provider_settings(
    configured: float, expected: float
) -> None:
    settings = _settings(configured)
    original = settings.model_dump(mode="python")

    result = smoke._smoke_configuration(settings)

    assert result.timeout_seconds == expected
    assert result.model == settings.review_model
    assert result.endpoint == settings.endpoint
    assert result.api_key == settings.api_key
    assert settings.model_dump(mode="python") == original


@pytest.mark.parametrize("opted_in", [False, True])
def test_entry_skips_without_opt_in_or_key_before_adapter_construction(
    opted_in: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("SCHOLARPATH_RUN_LIVE_TESTS", "true" if opted_in else "false")
    settings_loads: list[bool] = []

    def settings_without_key() -> NebiusReviewSettings:
        settings_loads.append(True)
        return _settings(with_key=False)

    def unexpected_adapter(*args: object, **kwargs: object) -> None:
        pytest.fail("Skipped smoke must not instantiate a provider")

    monkeypatch.setattr(smoke, "load_nebius_review_settings", settings_without_key)
    monkeypatch.setattr(smoke, "NebiusReviewModelAdapter", unexpected_adapter)

    with pytest.raises(pytest.skip.Exception):
        smoke.test_nebius_structured_independent_review_smoke()

    assert settings_loads == ([True] if opted_in else [])
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("use_entry", [False, True])
def test_tracing_is_disabled_and_restored_for_core_and_entry(
    use_entry: bool, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    class TracingCheckingModel(FakeIndependentReviewModel):
        def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
            assert get_tracing_context()["enabled"] is False
            return super().review(review_input)

    fake = TracingCheckingModel()
    settings = _settings(120.0)
    configurations: list[NebiusReviewConfiguration] = []

    def fake_adapter(configuration: NebiusReviewConfiguration) -> FakeIndependentReviewModel:
        assert get_tracing_context()["enabled"] is False
        configurations.append(configuration)
        return fake

    monkeypatch.setenv("SCHOLARPATH_RUN_LIVE_TESTS", "true")
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setattr(smoke, "load_nebius_review_settings", lambda: settings)
    monkeypatch.setattr(smoke, "NebiusReviewModelAdapter", fake_adapter)

    with tracing_context(enabled=True):
        if use_entry:
            smoke.test_nebius_structured_independent_review_smoke()
        else:
            with smoke._summarized_smoke() as diagnostics:
                smoke._run_review_smoke(fake, diagnostics)
        assert get_tracing_context()["enabled"] is True

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["review_calls"] == fake.call_count == 1
    assert summary["review_status"] == "accepted"
    assert len(configurations) == int(use_entry)
    if configurations:
        assert configurations[0].timeout_seconds == 60.0
    _assert_stage(summary, "configuration", "completed" if use_entry else "not_reached")
    assert settings.api_key is not None
    assert settings.api_key.get_secret_value() not in captured.out + captured.err


def test_configuration_failure_is_visible_without_a_model_call(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    failure = ValueError(_PRIVATE)

    def broken_configuration(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setenv("SCHOLARPATH_RUN_LIVE_TESTS", "true")
    monkeypatch.setattr(smoke, "load_nebius_review_settings", lambda: _settings())
    monkeypatch.setattr(smoke, "_smoke_configuration", broken_configuration)

    with pytest.raises(ValueError) as raised:
        smoke.test_nebius_structured_independent_review_smoke()

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert raised.value is failure
    assert summary["review_calls"] == 0
    _assert_stage(summary, "configuration", "failed", "configuration_invalid")
    _assert_stage(summary, "review_input", "not_reached")
    assert _PRIVATE not in captured.out + captured.err


def test_summary_drops_untyped_review_labels(capsys: pytest.CaptureFixture[str]) -> None:
    with smoke._summarized_smoke() as diagnostics:
        # Deliberate boundary corruption must not inject text into the projection.
        diagnostics.review_status = cast(IndependentReviewStatus, _PRIVATE)
        diagnostics.failure_kind = cast(IndependentReviewFailureKind, _PRIVATE)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["review_status"] is None
    assert summary["failure_kind"] is None
    assert _PRIVATE not in captured.out + captured.err


def test_unknown_stage_cannot_add_an_untrusted_summary_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with (
        pytest.raises(ValueError),
        smoke._summarized_smoke() as diagnostics,
        diagnostics.observe(cast(smoke._SmokeStage, _PRIVATE)),
    ):
        pytest.fail("Unknown stage must be rejected before entry")

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert set(summary["stage_outcomes"]) == {stage.value for stage in smoke._SmokeStage}
    assert _PRIVATE not in captured.out + captured.err
