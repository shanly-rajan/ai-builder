"""Offline checks prevent degraded reviews being reported as live canary success."""

import json

import pytest

from scholarpath.agents.independent_review import (
    IndependentReviewAgent,
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewModelOutputError,
    IndependentReviewResult,
)
from scholarpath.domain import IndependentReviewFailureKind, IndependentReviewStatus
from tests.fakes import (
    FakeIndependentReviewModel,
    FakeSupervisorSearch,
    make_accepted_review,
    make_revised_review,
)
from tests.fixtures import (
    make_candidate_profile,
    make_research_fit_assessment,
    make_verified_supervisor,
)
from tests.integration import test_m13_live_canary as canary

PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"


@pytest.mark.parametrize("revised", [False, True])
def test_canary_accepts_a_completed_fake_review(revised: bool) -> None:
    profile = make_candidate_profile()
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    review_input = IndependentReviewInput.from_domain(profile, supervisor, assessment)
    outcome = (
        make_revised_review(review_input, recommended_score=75)
        if revised
        else make_accepted_review(review_input)
    )
    fake = FakeIndependentReviewModel({supervisor.supervisor_id: [outcome]})
    review = IndependentReviewAgent(fake).review(profile, supervisor, assessment)

    canary._require_completed_review(review)

    assert fake.call_count == 1
    assert review.failure_kind is None
    assert review.review_status is (
        IndependentReviewStatus.REVISED if revised else IndependentReviewStatus.ACCEPTED
    )


@pytest.mark.parametrize("failure", list(IndependentReviewFailureKind))
def test_canary_rejects_unavailable_fake_reviews_without_exposing_errors(
    failure: IndependentReviewFailureKind,
) -> None:
    profile = make_candidate_profile()
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    review_input = IndependentReviewInput.from_domain(profile, supervisor, assessment)
    outcome: IndependentReviewResult | Exception
    if failure is IndependentReviewFailureKind.MODEL_INVOCATION:
        outcome = IndependentReviewModelInvocationError(PRIVATE)
    elif failure is IndependentReviewFailureKind.INVALID_OUTPUT:
        outcome = IndependentReviewModelOutputError(PRIVATE)
    else:
        outcome = make_revised_review(
            review_input,
            recommended_score=75,
            unsupported_claim_ids=[PRIVATE],
        )
    fake = FakeIndependentReviewModel({supervisor.supervisor_id: [outcome]})
    review = IndependentReviewAgent(fake).review(profile, supervisor, assessment)

    with pytest.raises(pytest.fail.Exception) as error:
        canary._require_completed_review(review)

    assert fake.call_count == 1
    assert review.review_status is IndependentReviewStatus.UNAVAILABLE
    assert review.failure_kind is failure
    assert PRIVATE not in str(error.value)
    assert str(error.value) == (
        "The live Nebius review did not return a valid completed independent review"
    )


def test_canary_rejects_a_completed_status_with_a_failure_category() -> None:
    profile = make_candidate_profile()
    supervisor = make_verified_supervisor(1)
    assessment = make_research_fit_assessment(1)
    review = IndependentReviewAgent(FakeIndependentReviewModel()).review(
        profile, supervisor, assessment
    )
    # Deliberately bypass domain validation to check the canary's defensive boundary.
    inconsistent_review = type(review).model_construct(
        **{
            **review.model_dump(mode="python"),
            "failure_kind": IndependentReviewFailureKind.INVALID_OUTPUT,
        }
    )

    with pytest.raises(pytest.fail.Exception, match="valid completed independent review"):
        canary._require_completed_review(inconsistent_review)


def test_canary_summary_reports_attempts_and_unmeasured_usage(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    clock_values = iter((100.0, 101.23456))
    monkeypatch.setattr(canary, "monotonic", lambda: next(clock_values))

    with canary._summarized_call_budget() as budget:
        budget.consume("openai_planning")
        budget.consume("openai_planning")
        budget.consume("you_search")
        budget.calls[PRIVATE] = 99

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary == {
        "event": "live_canary.summary",
        "provider_calls": {
            "openai_planning": 2,
            "you_search": 1,
            "tavily_search": 0,
            "tavily_extract": 0,
            "openai_evidence": 0,
            "openai_research_fit": 0,
            "nebius_review": 0,
        },
        "total_provider_calls": 3,
        "elapsed_seconds": 1.235,
        "stage_outcomes": {
            stage.value: {"status": "not_reached", "failure_category": None}
            for stage in canary._CanaryStage
        },
        "verification_diagnostics": None,
        "grounding_diagnostics": None,
        "review_diagnostics": None,
        "proposed_supervisor_count": None,
        "shortlisted_supervisor_count": None,
        "token_usage": None,
        "cost_usd": None,
    }
    assert PRIVATE not in captured.out
    assert captured.err == ""


def test_canary_summary_survives_early_provider_failure(
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeSupervisorSearch({PRIVATE: RuntimeError(PRIVATE)})

    with (
        pytest.raises(RuntimeError, match="SECRET_TOKEN"),
        canary._summarized_call_budget() as budget,
    ):
        canary._BudgetedSearch(fake, budget, "you_search").search(PRIVATE)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert fake.calls == [PRIVATE]
    assert summary["provider_calls"]["you_search"] == 1
    assert summary["total_provider_calls"] == 1
    assert summary["elapsed_seconds"] >= 0
    assert "success" not in summary
    assert PRIVATE not in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("operation,limit", list(canary._LIVE_CALL_LIMITS.items()))
def test_canary_summary_survives_retry_budget_exhaustion_without_an_extra_call(
    operation: str,
    limit: int,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fake = FakeSupervisorSearch({PRIVATE: ()})

    with (
        pytest.raises(AssertionError, match="Live canary call budget exhausted"),
        canary._summarized_call_budget() as budget,
    ):
        search = canary._BudgetedSearch(fake, budget, operation)
        for _ in range(limit + 1):
            search.search(PRIVATE)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert len(fake.calls) == limit
    assert summary["provider_calls"][operation] == limit
    assert summary["total_provider_calls"] == limit
    assert summary["token_usage"] is None
    assert summary["cost_usd"] is None
    assert PRIVATE not in captured.out


def test_canary_limits_remain_nine_calls() -> None:
    assert sum(canary._LIVE_CALL_LIMITS.values()) == 9
