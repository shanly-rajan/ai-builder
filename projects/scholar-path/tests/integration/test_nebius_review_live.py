"""Optional live smoke test for Nebius independent Research Fit review."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import StrEnum
from time import monotonic

import pytest
from langsmith import tracing_context

from scholarpath.agents.independent_review import (
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewModelOutputError,
    IndependentReviewModelPort,
    IndependentReviewResult,
    reconcile_research_fit_assessment,
)
from scholarpath.agents.nebius_review import NebiusReviewModelAdapter
from scholarpath.config import (
    NebiusReviewConfiguration,
    NebiusReviewSettings,
    load_nebius_review_settings,
)
from scholarpath.domain import (
    IndependentReviewDecision,
    IndependentReviewFailureKind,
    IndependentReviewStatus,
    ReconciledResearchFitAssessment,
)
from tests.fixtures import (
    make_candidate_profile,
    make_research_fit_assessment,
    make_verified_supervisor,
)


class _SmokeStage(StrEnum):
    CONFIGURATION = "configuration"
    REVIEW_INPUT = "review_input"
    MODEL_CALL = "model_call"
    RESPONSE_CHECKS = "response_checks"
    RECONCILIATION = "reconciliation"
    FINAL_CHECKS = "final_checks"


class _Status(StrEnum):
    NOT_REACHED = "not_reached"
    STARTED = "started"
    COMPLETED = "completed"
    FAILED = "failed"


class _Failure(StrEnum):
    CONFIGURATION_INVALID = "configuration_invalid"
    INPUT_VALIDATION = "input_validation"
    MODEL_INVOCATION = "model_invocation"
    INVALID_OUTPUT = "invalid_output"
    INVALID_EVIDENCE_REFERENCE = "invalid_evidence_reference"
    REVIEW_NOT_COMPLETED = "review_not_completed"
    CHECK_FAILED = "check_failed"
    LOCAL_VALIDATION = "local_validation"
    UNEXPECTED_FAILURE = "unexpected_failure"
    CALL_LIMIT = "call_limit"


class _ReviewCallLimitError(AssertionError):
    """Prevent a second model invocation within one smoke-test execution."""


class _InvalidReviewReferencesError(AssertionError):
    """The original response allowlist check did not pass."""


class _IncompleteReviewError(AssertionError):
    """The original reconciliation check did not pass."""


def _failure_category(stage: _SmokeStage, error: BaseException) -> _Failure:
    """Classify known types without parsing or emitting exception messages."""
    if isinstance(error, _ReviewCallLimitError):
        return _Failure.CALL_LIMIT
    if isinstance(error, _InvalidReviewReferencesError):
        return _Failure.INVALID_EVIDENCE_REFERENCE
    if isinstance(error, _IncompleteReviewError):
        return _Failure.REVIEW_NOT_COMPLETED
    if isinstance(error, (AssertionError, pytest.fail.Exception)):
        return _Failure.CHECK_FAILED
    if stage is _SmokeStage.MODEL_CALL:
        if isinstance(error, IndependentReviewModelInvocationError):
            return _Failure.MODEL_INVOCATION
        if isinstance(error, (IndependentReviewModelOutputError, ValueError)):
            return _Failure.INVALID_OUTPUT
    if isinstance(error, ValueError):
        return {
            _SmokeStage.CONFIGURATION: _Failure.CONFIGURATION_INVALID,
            _SmokeStage.REVIEW_INPUT: _Failure.INPUT_VALIDATION,
            _SmokeStage.RESPONSE_CHECKS: _Failure.INVALID_OUTPUT,
        }.get(stage, _Failure.LOCAL_VALIDATION)
    return _Failure.UNEXPECTED_FAILURE


@dataclass(frozen=True, slots=True)
class _Outcome:
    status: _Status = _Status.NOT_REACHED
    failure_category: _Failure | None = None


@dataclass(slots=True)
class _SmokeDiagnostics:
    review_calls: int = 0
    outcomes: dict[_SmokeStage, _Outcome] = field(default_factory=dict)
    review_status: IndependentReviewStatus | None = None
    failure_kind: IndependentReviewFailureKind | None = None

    def consume_review_call(self) -> None:
        if self.review_calls >= 1:
            raise _ReviewCallLimitError("The isolated Nebius smoke permits one model call")
        self.review_calls += 1

    @contextmanager
    def observe(self, stage: _SmokeStage) -> Iterator[None]:
        if not isinstance(stage, _SmokeStage):
            raise ValueError("Unknown isolated Nebius smoke stage")
        self.outcomes[stage] = _Outcome(_Status.STARTED)
        try:
            yield
        except (Exception, pytest.fail.Exception) as error:
            self.outcomes[stage] = _Outcome(_Status.FAILED, _failure_category(stage, error))
            raise
        else:
            self.outcomes[stage] = _Outcome(_Status.COMPLETED)


@contextmanager
def _summarized_smoke() -> Iterator[_SmokeDiagnostics]:
    """Emit only fixed stage codes, enum outcomes, counts and elapsed time."""
    diagnostics = _SmokeDiagnostics()
    started_at = monotonic()
    try:
        yield diagnostics
    finally:
        stages = {}
        for stage in _SmokeStage:
            outcome = diagnostics.outcomes.get(stage, _Outcome())
            stages[stage.value] = {
                "status": outcome.status.value,
                "failure_category": (
                    outcome.failure_category.value if outcome.failure_category is not None else None
                ),
            }
        print(
            json.dumps(
                {
                    "event": "nebius_smoke.summary",
                    "stage_outcomes": stages,
                    "review_calls": diagnostics.review_calls,
                    "review_status": (
                        diagnostics.review_status.value
                        if isinstance(diagnostics.review_status, IndependentReviewStatus)
                        else None
                    ),
                    "failure_kind": (
                        diagnostics.failure_kind.value
                        if isinstance(diagnostics.failure_kind, IndependentReviewFailureKind)
                        else None
                    ),
                    "elapsed_seconds": round(monotonic() - started_at, 3),
                    "token_usage": None,
                    "cost_usd": None,
                },
                sort_keys=True,
            )
        )


def _smoke_configuration(settings: NebiusReviewSettings) -> NebiusReviewConfiguration:
    configuration = settings.for_review_model()
    return configuration.model_copy(
        update={"timeout_seconds": min(configuration.timeout_seconds, 60.0)}
    )


@contextmanager
def _tracing_disabled() -> Iterator[None]:
    # The same context used by LangSmithObservability's disabled path; no settings load.
    with tracing_context(enabled=False):
        yield


def _run_review_smoke(
    model: IndependentReviewModelPort,
    diagnostics: _SmokeDiagnostics,
) -> ReconciledResearchFitAssessment:
    """Exercise the existing fixed-input assertions without other providers or persistence."""
    with _tracing_disabled():
        with diagnostics.observe(_SmokeStage.REVIEW_INPUT):
            review_input = IndependentReviewInput.from_domain(
                make_candidate_profile(),
                make_verified_supervisor(1),
                make_research_fit_assessment(1),
            )
        with diagnostics.observe(_SmokeStage.MODEL_CALL):
            diagnostics.consume_review_call()
            raw_result = model.review(review_input)
        with diagnostics.observe(_SmokeStage.RESPONSE_CHECKS):
            result = IndependentReviewResult.model_validate(raw_result)
            assert result.decision in {
                IndependentReviewDecision.ACCEPT,
                IndependentReviewDecision.REVISE,
            }
            assert 0 <= result.recommended_score <= 100
            if not set(result.unsupported_claim_ids).issubset(
                review_input.removable_supporting_evidence_ids
            ):
                raise _InvalidReviewReferencesError("Unsupported claim IDs are not eligible")
            if not set(result.overlooked_evidence_ids).issubset(
                review_input.eligible_overlooked_evidence_ids
            ):
                raise _InvalidReviewReferencesError("Overlooked evidence IDs are not eligible")
        with diagnostics.observe(_SmokeStage.RECONCILIATION):
            reconciled = reconcile_research_fit_assessment(
                review_input.verified_supervisor,
                review_input.initial_assessment,
                result,
            )
            diagnostics.review_status = reconciled.review_status
            diagnostics.failure_kind = reconciled.failure_kind
        with diagnostics.observe(_SmokeStage.FINAL_CHECKS):
            if reconciled.failure_kind is not None:
                raise _IncompleteReviewError("The isolated review did not reconcile successfully")
        return reconciled


def _live_tests_enabled() -> bool:
    return os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.live
def test_nebius_structured_independent_review_smoke() -> None:
    if not _live_tests_enabled():
        pytest.skip("Set SCHOLARPATH_RUN_LIVE_TESTS=true to opt in to live tests")
    settings = load_nebius_review_settings()
    if settings.api_key is None or not settings.api_key.get_secret_value().strip():
        pytest.skip("NEBIUS_API_KEY is required for the live independent-review smoke test")

    with _summarized_smoke() as diagnostics, _tracing_disabled():
        with diagnostics.observe(_SmokeStage.CONFIGURATION):
            model = NebiusReviewModelAdapter(_smoke_configuration(settings))
        _run_review_smoke(model, diagnostics)
