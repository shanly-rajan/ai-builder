"""Offline post-fit diagnostics distinguish review, proposal and approval failures."""

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import cast

import pytest

from scholarpath.agents.independent_review import (
    IndependentReviewAgent,
    IndependentReviewInput,
    IndependentReviewModelInvocationError,
    IndependentReviewModelOutputError,
    IndependentReviewResult,
)
from scholarpath.agents.shortlist_synthesis import ShortlistSynthesisAgent
from scholarpath.domain import (
    CandidateProfile,
    CandidateReviewAction,
    CandidateReviewDecision,
    IndependentReviewFailureKind,
    IndependentReviewStatus,
    ProspectiveSupervisor,
    ResearchFitAssessment,
    SupervisorLifecycleStatus,
    VerifiedSupervisor,
    create_supervisor_shortlist,
)
from tests.fakes import FakeIndependentReviewModel, make_accepted_review, make_revised_review
from tests.fixtures import (
    make_candidate_profile,
    make_prospective_supervisor,
    make_research_fit_assessment,
    make_verified_supervisor,
)
from tests.integration import test_m13_live_canary as canary

_PRIVATE = "private-person@example.test SECRET_TOKEN https://private.example/research"


@dataclass(frozen=True)
class _Inputs:
    profile: CandidateProfile
    prospective: ProspectiveSupervisor
    verified: VerifiedSupervisor
    assessment: ResearchFitAssessment


@pytest.fixture
def inputs() -> _Inputs:
    return _Inputs(
        make_candidate_profile(),
        make_prospective_supervisor(1),
        make_verified_supervisor(1),
        make_research_fit_assessment(1),
    )


def _assert_stage(
    budget: canary._CallBudget,
    stage: canary._CanaryStage,
    status: str,
    category: str | None = None,
) -> None:
    assert canary._stage_summary(budget)[stage.value] == {
        "status": status,
        "failure_category": category,
    }


def _prior_calls(budget: canary._CallBudget) -> None:
    """Represent prior fake stages without invoking any provider."""
    for operation in (
        "openai_planning",
        "you_search",
        "tavily_extract",
        "openai_evidence",
        "openai_research_fit",
    ):
        budget.consume(operation)


@pytest.mark.parametrize("revised", [False, True])
def test_completed_review_proposal_and_approval_have_separate_stages(
    inputs: _Inputs, revised: bool, capsys: pytest.CaptureFixture[str]
) -> None:
    review_input = IndependentReviewInput.from_domain(
        inputs.profile, inputs.verified, inputs.assessment
    )
    outcome = (
        make_revised_review(review_input, recommended_score=75)
        if revised
        else make_accepted_review(review_input)
    )
    fake = FakeIndependentReviewModel({inputs.verified.supervisor_id: [outcome]})
    snapshots = tuple(
        item.model_dump_json()
        for item in (inputs.profile, inputs.prospective, inputs.verified, inputs.assessment)
    )

    with canary._summarized_call_budget() as budget:
        _prior_calls(budget)
        reviewed, proposal = canary._review_and_synthesize(
            inputs.profile,
            inputs.verified,
            inputs.assessment,
            canary._BudgetedReviewModel(fake, budget),
            budget,
        )
        assert budget.proposed_supervisor_count == 1
        assert budget.shortlisted_supervisor_count is None
        assert proposal.recommendations[0].supervisor.status is SupervisorLifecycleStatus.VERIFIED
        shortlist = canary._approve_canary_shortlist(
            inputs.profile, inputs.prospective, inputs.verified, proposal, budget
        )
        canary._check_canary_results(inputs.assessment, reviewed, proposal, shortlist, budget)

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["review_diagnostics"] == {
        "review_status": "revised" if revised else "accepted",
        "failure_kind": None,
    }
    assert summary["proposed_supervisor_count"] == 1
    assert summary["shortlisted_supervisor_count"] == 1
    assert summary["total_provider_calls"] == 6
    assert fake.call_count == 1
    assert fake.inputs == [review_input]
    for stage in (
        canary._CanaryStage.REVIEW_INPUT,
        canary._CanaryStage.REVIEW_MODEL_CALL,
        canary._CanaryStage.INDEPENDENT_REVIEW,
        canary._CanaryStage.REVIEW_GATE,
        canary._CanaryStage.SHORTLIST_SYNTHESIS,
        canary._CanaryStage.PROPOSAL_CHECKS,
        canary._CanaryStage.SYNTHETIC_APPROVAL,
        canary._CanaryStage.FINAL_CHECKS,
    ):
        _assert_stage(budget, stage, "completed")
    assert (
        tuple(
            item.model_dump_json()
            for item in (inputs.profile, inputs.prospective, inputs.verified, inputs.assessment)
        )
        == snapshots
    )
    assert reviewed.initial_assessment == inputs.assessment
    assert proposal.recommendations[0].supervisor.evidence == inputs.verified.evidence
    assert shortlist.shortlisted_supervisors[0].evidence == inputs.verified.evidence
    assert shortlist.shortlisted_supervisors[0].status is SupervisorLifecycleStatus.SHORTLISTED
    assert shortlist.shortlisted_supervisors[0].availability_status is (
        inputs.verified.availability_status
    )
    assert reviewed.review_status is (
        IndependentReviewStatus.REVISED if revised else IndependentReviewStatus.ACCEPTED
    )
    assert reviewed.effective_score == (75 if revised else inputs.assessment.overall_score)
    for private in (
        inputs.profile.candidate_id,
        inputs.profile.proposed_research_statement,
        inputs.verified.full_name,
        inputs.verified.institution,
        str(inputs.verified.profile_url),
        inputs.assessment.rationale,
        outcome.critique,
    ):
        assert private not in captured.out
    assert captured.err == ""


@pytest.mark.parametrize("failure", list(IndependentReviewFailureKind))
def test_unavailable_review_records_typed_failure_then_stops_at_gate(
    inputs: _Inputs,
    failure: IndependentReviewFailureKind,
    capsys: pytest.CaptureFixture[str],
) -> None:
    review_input = IndependentReviewInput.from_domain(
        inputs.profile, inputs.verified, inputs.assessment
    )
    outcome: IndependentReviewResult | Exception
    if failure is IndependentReviewFailureKind.MODEL_INVOCATION:
        outcome = IndependentReviewModelInvocationError(_PRIVATE)
    elif failure is IndependentReviewFailureKind.INVALID_OUTPUT:
        outcome = IndependentReviewModelOutputError(_PRIVATE)
    else:
        outcome = make_revised_review(
            review_input, recommended_score=75, unsupported_claim_ids=[_PRIVATE]
        )
    fake = FakeIndependentReviewModel({inputs.verified.supervisor_id: [outcome]})

    with pytest.raises(pytest.fail.Exception), canary._summarized_call_budget() as budget:
        canary._review_and_synthesize(
            inputs.profile,
            inputs.verified,
            inputs.assessment,
            canary._BudgetedReviewModel(fake, budget),
            budget,
        )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["review_diagnostics"] == {
        "review_status": "unavailable",
        "failure_kind": failure.value,
    }
    assert summary["proposed_supervisor_count"] is None
    assert summary["shortlisted_supervisor_count"] is None
    assert summary["provider_calls"]["nebius_review"] == 1
    assert fake.call_count == 1
    _assert_stage(budget, canary._CanaryStage.REVIEW_INPUT, "completed")
    _assert_stage(budget, canary._CanaryStage.INDEPENDENT_REVIEW, "completed")
    if failure is IndependentReviewFailureKind.INVALID_EVIDENCE_REFERENCE:
        _assert_stage(budget, canary._CanaryStage.REVIEW_MODEL_CALL, "completed")
    else:
        _assert_stage(budget, canary._CanaryStage.REVIEW_MODEL_CALL, "failed", failure.value)
    _assert_stage(budget, canary._CanaryStage.REVIEW_GATE, "failed", "review_not_completed")
    for stage in (
        canary._CanaryStage.SHORTLIST_SYNTHESIS,
        canary._CanaryStage.PROPOSAL_CHECKS,
        canary._CanaryStage.SYNTHETIC_APPROVAL,
        canary._CanaryStage.FINAL_CHECKS,
    ):
        _assert_stage(budget, stage, "not_reached")
    assert _PRIVATE not in captured.out + captured.err


def test_invalid_local_review_input_stops_before_model_call(
    inputs: _Inputs, capsys: pytest.CaptureFixture[str]
) -> None:
    corrupted = inputs.assessment.model_copy(update={"supervisor_id": "wrong-supervisor"})
    fake = FakeIndependentReviewModel()

    with pytest.raises(ValueError), canary._summarized_call_budget() as budget:
        canary._review_and_synthesize(
            inputs.profile,
            inputs.verified,
            corrupted,
            canary._BudgetedReviewModel(fake, budget),
            budget,
        )

    summary = json.loads(capsys.readouterr().out)
    _assert_stage(budget, canary._CanaryStage.REVIEW_INPUT, "failed", "input_validation")
    assert fake.call_count == 0
    assert summary["provider_calls"]["nebius_review"] == 0
    assert summary["review_diagnostics"] is None
    assert summary["proposed_supervisor_count"] is None
    assert summary["shortlisted_supervisor_count"] is None
    for stage in (
        canary._CanaryStage.REVIEW_MODEL_CALL,
        canary._CanaryStage.INDEPENDENT_REVIEW,
        canary._CanaryStage.REVIEW_GATE,
        canary._CanaryStage.SHORTLIST_SYNTHESIS,
    ):
        _assert_stage(budget, stage, "not_reached")


@pytest.mark.parametrize("error_type", [ValueError, AssertionError, pytest.fail.Exception])
def test_synthesis_failure_is_not_reported_as_review_failure(
    inputs: _Inputs,
    error_type: type[BaseException],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = error_type(_PRIVATE)

    def fail_synthesis(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(
        "tests.integration.test_m13_live_canary.ShortlistSynthesisAgent.synthesize", fail_synthesis
    )
    fake = FakeIndependentReviewModel()
    with pytest.raises(error_type) as raised, canary._summarized_call_budget() as budget:
        canary._review_and_synthesize(
            inputs.profile,
            inputs.verified,
            inputs.assessment,
            canary._BudgetedReviewModel(fake, budget),
            budget,
        )

    assert raised.value is failure
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    _assert_stage(budget, canary._CanaryStage.REVIEW_GATE, "completed")
    _assert_stage(
        budget,
        canary._CanaryStage.SHORTLIST_SYNTHESIS,
        "failed",
        "local_validation" if error_type is ValueError else "check_failed",
    )
    assert summary["review_diagnostics"] == {"review_status": "accepted", "failure_kind": None}
    assert summary["proposed_supervisor_count"] is None
    assert summary["shortlisted_supervisor_count"] is None
    assert fake.call_count == 1
    assert _PRIVATE not in captured.out + captured.err


@pytest.mark.parametrize("revised", [False, True])
def test_observed_helpers_preserve_original_pipeline_results(
    inputs: _Inputs, revised: bool
) -> None:
    snapshot = tuple(
        item.model_dump_json()
        for item in (inputs.profile, inputs.prospective, inputs.verified, inputs.assessment)
    )
    review_input = IndependentReviewInput.from_domain(
        inputs.profile, inputs.verified, inputs.assessment
    )
    response = (
        make_revised_review(review_input, recommended_score=75)
        if revised
        else make_accepted_review(review_input)
    )
    original_fake = FakeIndependentReviewModel({inputs.verified.supervisor_id: [response]})
    original_review = IndependentReviewAgent(original_fake).review(
        inputs.profile, inputs.verified, inputs.assessment
    )
    original_proposal = ShortlistSynthesisAgent(max_results=1).synthesize(
        inputs.profile.candidate_id,
        (inputs.verified,),
        (inputs.assessment,),
        datetime.now(UTC),
        (original_review,),
    )
    original_approval = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=(inputs.verified.supervisor_id,),
        reason="Explicit approval for the opt-in live canary.",
    )
    original_shortlist = create_supervisor_shortlist(
        inputs.profile.candidate_id,
        (inputs.verified,),
        original_approval,
        generated_at=datetime.now(UTC),
        briefing="One explicitly approved, evidence-backed live canary result.",
    )

    observed_fake = FakeIndependentReviewModel({inputs.verified.supervisor_id: [response]})
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))
    observed_review, observed_proposal = canary._review_and_synthesize(
        inputs.profile,
        inputs.verified,
        inputs.assessment,
        canary._BudgetedReviewModel(observed_fake, budget),
        budget,
    )
    observed_shortlist = canary._approve_canary_shortlist(
        inputs.profile, inputs.prospective, inputs.verified, observed_proposal, budget
    )

    assert observed_review == original_review
    assert observed_proposal.model_dump(exclude={"generated_at"}) == original_proposal.model_dump(
        exclude={"generated_at"}
    )
    assert observed_shortlist.model_dump(exclude={"generated_at"}) == original_shortlist.model_dump(
        exclude={"generated_at"}
    )
    assert (
        original_fake.call_count == observed_fake.call_count == budget.calls["nebius_review"] == 1
    )
    assert original_fake.inputs == observed_fake.inputs == [review_input]
    assert (
        tuple(
            item.model_dump_json()
            for item in (inputs.profile, inputs.prospective, inputs.verified, inputs.assessment)
        )
        == snapshot
    )


def test_failed_proposal_assertion_cannot_reach_synthetic_approval(inputs: _Inputs) -> None:
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))
    _, proposal = canary._review_and_synthesize(
        inputs.profile,
        inputs.verified,
        inputs.assessment,
        canary._BudgetedReviewModel(FakeIndependentReviewModel(), budget),
        budget,
    )
    invalid_proposal = type(proposal).model_construct(
        **{**proposal.model_dump(mode="python"), "recommendations": ()}
    )

    with pytest.raises(AssertionError):
        canary._approve_canary_shortlist(
            inputs.profile, inputs.prospective, inputs.verified, invalid_proposal, budget
        )

    _assert_stage(budget, canary._CanaryStage.PROPOSAL_CHECKS, "failed", "check_failed")
    _assert_stage(budget, canary._CanaryStage.SYNTHETIC_APPROVAL, "not_reached")
    assert budget.proposed_supervisor_count == 1
    assert budget.shortlisted_supervisor_count is None


@pytest.mark.parametrize("factory", ["CandidateReviewDecision", "create_supervisor_shortlist"])
def test_approval_factory_failure_keeps_shortlist_count_unknown(
    inputs: _Inputs,
    factory: str,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    failure = ValueError(_PRIVATE)

    def fail_approval(*args: object, **kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(canary, factory, fail_approval)
    with pytest.raises(ValueError) as raised, canary._summarized_call_budget() as budget:
        _, proposal = canary._review_and_synthesize(
            inputs.profile,
            inputs.verified,
            inputs.assessment,
            canary._BudgetedReviewModel(FakeIndependentReviewModel(), budget),
            budget,
        )
        canary._approve_canary_shortlist(
            inputs.profile, inputs.prospective, inputs.verified, proposal, budget
        )

    assert raised.value is failure
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    _assert_stage(budget, canary._CanaryStage.PROPOSAL_CHECKS, "completed")
    _assert_stage(budget, canary._CanaryStage.SYNTHETIC_APPROVAL, "failed", "local_validation")
    _assert_stage(budget, canary._CanaryStage.FINAL_CHECKS, "not_reached")
    assert summary["proposed_supervisor_count"] == 1
    assert summary["shortlisted_supervisor_count"] is None
    assert _PRIVATE not in captured.out + captured.err


def test_final_check_failure_retains_completed_review_and_approval_counts(inputs: _Inputs) -> None:
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))
    reviewed, proposal = canary._review_and_synthesize(
        inputs.profile,
        inputs.verified,
        inputs.assessment,
        canary._BudgetedReviewModel(FakeIndependentReviewModel(), budget),
        budget,
    )
    shortlist = canary._approve_canary_shortlist(
        inputs.profile, inputs.prospective, inputs.verified, proposal, budget
    )
    # Earlier pipeline calls are deliberately absent; existing final budget checks fail.
    with pytest.raises(AssertionError):
        canary._check_canary_results(inputs.assessment, reviewed, proposal, shortlist, budget)

    _assert_stage(budget, canary._CanaryStage.REVIEW_GATE, "completed")
    _assert_stage(budget, canary._CanaryStage.SYNTHETIC_APPROVAL, "completed")
    _assert_stage(budget, canary._CanaryStage.FINAL_CHECKS, "failed", "check_failed")
    assert budget.proposed_supervisor_count == 1
    assert budget.shortlisted_supervisor_count == 1


@pytest.mark.parametrize(
    "error_type", [IndependentReviewModelInvocationError, IndependentReviewModelOutputError]
)
def test_budgeted_review_preserves_adapter_exception_identity(
    inputs: _Inputs, error_type: type[Exception]
) -> None:
    failure = error_type(_PRIVATE)
    fake = FakeIndependentReviewModel({inputs.verified.supervisor_id: [failure]})
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))
    review_input = IndependentReviewInput.from_domain(
        inputs.profile, inputs.verified, inputs.assessment
    )

    with pytest.raises(error_type) as raised:
        canary._BudgetedReviewModel(fake, budget).review(review_input)

    assert raised.value is failure
    assert fake.call_count == 1
    assert budget.calls["nebius_review"] == 1


def test_budgeted_review_never_exceeds_one_delegate_call(inputs: _Inputs) -> None:
    fake = FakeIndependentReviewModel()
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))
    model = canary._BudgetedReviewModel(fake, budget)
    review_input = IndependentReviewInput.from_domain(
        inputs.profile, inputs.verified, inputs.assessment
    )
    model.review(review_input)

    with pytest.raises(AssertionError, match="call budget exhausted"):
        model.review(review_input)

    assert fake.call_count == 1
    assert budget.calls["nebius_review"] == 1
    assert sum(budget.limits.values()) == 9


@pytest.mark.parametrize("error_type", [KeyboardInterrupt, SystemExit])
def test_observation_does_not_relabel_process_control_exceptions(
    error_type: type[BaseException],
) -> None:
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))
    failure = error_type(_PRIVATE)

    with pytest.raises(error_type) as raised, budget.observe(canary._CanaryStage.REVIEW_GATE):
        raise failure

    assert raised.value is failure
    _assert_stage(budget, canary._CanaryStage.REVIEW_GATE, "started")


@pytest.mark.parametrize(
    "error_factory", [lambda: AssertionError(_PRIVATE), lambda: pytest.fail.Exception(_PRIVATE)]
)
def test_observation_records_assertions_without_changing_the_exception(
    error_factory: Callable[[], BaseException],
) -> None:
    failure = error_factory()
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))

    with pytest.raises(type(failure)) as raised, budget.observe(canary._CanaryStage.FINAL_CHECKS):
        raise failure

    assert raised.value is failure
    _assert_stage(budget, canary._CanaryStage.FINAL_CHECKS, "failed", "check_failed")


def test_invalid_returned_review_is_separate_from_failed_model_invocation(inputs: _Inputs) -> None:
    class MalformedReviewModel(FakeIndependentReviewModel):
        def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
            self.inputs.append(review_input)
            # Deliberately violate the provider contract to test the agent's
            # returned-output validation, not an exception from model invocation.
            return cast(IndependentReviewResult, {"recommended_score": -1})

    fake = MalformedReviewModel()
    budget = canary._CallBudget(dict(canary._LIVE_CALL_LIMITS))

    with pytest.raises(pytest.fail.Exception):
        canary._review_and_synthesize(
            inputs.profile,
            inputs.verified,
            inputs.assessment,
            canary._BudgetedReviewModel(fake, budget),
            budget,
        )

    _assert_stage(budget, canary._CanaryStage.REVIEW_MODEL_CALL, "completed")
    _assert_stage(budget, canary._CanaryStage.REVIEW_GATE, "failed", "review_not_completed")
    assert budget.review_diagnostics == {
        "review_status": "unavailable",
        "failure_kind": "invalid_output",
    }
    assert fake.call_count == 1


@pytest.mark.parametrize("untrusted_value", [_PRIVATE, "accepted"])
def test_review_projection_emits_only_typed_enum_values(
    inputs: _Inputs, untrusted_value: str
) -> None:
    reviewed = IndependentReviewAgent(FakeIndependentReviewModel()).review(
        inputs.profile, inputs.verified, inputs.assessment
    )
    corrupted = type(reviewed).model_construct(
        **{
            **reviewed.model_dump(mode="python"),
            "review_status": untrusted_value,
            "failure_kind": untrusted_value,
            "critique": _PRIVATE,
            "unsupported_claim_ids": (_PRIVATE,),
        }
    )

    projected = canary._review_diagnostics(corrupted)

    assert projected == {"review_status": None, "failure_kind": None}
    assert _PRIVATE not in json.dumps(projected)
