"""Graph scenarios for evidence-cited M7 Research Fit and proposal synthesis."""

from dataclasses import dataclass
from datetime import UTC, datetime

from scholarpath.agents import ResearchFitModelInvocationError
from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    SupervisorLifecycleStatus,
    validate_research_fit_evidence,
)
from scholarpath.graph import (
    FIXTURE_RETRIEVED_AT,
    ReviewStatus,
    ScholarPathState,
    UtcClockPort,
    run_scholarpath_graph,
)
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
)


@dataclass(frozen=True, slots=True)
class FixedUtcClock:
    """Deterministic UTC clock for graph timestamp assertions."""

    timestamp: datetime

    def now(self) -> datetime:
        """Return the configured aware UTC timestamp."""
        return self.timestamp


def _run(
    model: FakeResearchFitModel,
    *,
    utc_clock: UtcClockPort | None = None,
) -> ScholarPathState:
    return run_scholarpath_graph(
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=model,
        alternate_evidence_search=FakeSupervisorSearch(),
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.OFF,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
        utc_clock=utc_clock,
    )


def test_graph_uses_the_fake_model_for_every_verified_supervisor() -> None:
    model = FakeResearchFitModel()

    final_state = _run(model)

    assert model.call_count == len(final_state["verified_supervisors"])
    assert len(final_state["research_fit_assessments"]) == model.call_count
    assert final_state["review_status"] is ReviewStatus.COMPLETED


def test_every_graph_assessment_has_deterministic_arithmetic_and_owned_citations() -> None:
    final_state = _run(FakeResearchFitModel())
    supervisors = {
        supervisor.supervisor_id: supervisor for supervisor in final_state["verified_supervisors"]
    }

    for assessment in final_state["research_fit_assessments"]:
        validate_research_fit_evidence(supervisors[assessment.supervisor_id], assessment)
        components = (
            assessment.breakdown.topic_alignment,
            assessment.breakdown.methodological_alignment,
            assessment.breakdown.research_orientation_alignment,
            assessment.breakdown.recent_research_alignment,
            assessment.breakdown.practical_constraint_alignment,
        )
        assert assessment.overall_score == sum(component.score for component in components)
        assert all(component.supporting_evidence_ids for component in components if component.score)


def test_graph_excludes_availability_from_scores_and_preserves_not_stated_status() -> None:
    model = FakeResearchFitModel()

    final_state = _run(model)

    assert all(
        evidence.claim_type is not EvidenceClaimType.AVAILABILITY
        for fit_input in model.inputs
        for evidence in fit_input.evidence
    )
    not_stated = [
        supervisor
        for supervisor in final_state["verified_supervisors"]
        if supervisor.availability_status is AvailabilityStatus.NOT_STATED
    ]
    assert not_stated
    assert all(
        supervisor.availability_status is AvailabilityStatus.NOT_STATED for supervisor in not_stated
    )


def test_preliminary_proposal_is_ranked_and_remains_unapproved() -> None:
    final_state = _run(FakeResearchFitModel())
    proposal = final_state["proposed_shortlist"]

    assert proposal is not None
    assert len(proposal.recommendations) == 5
    assert [item.assessment.overall_score for item in proposal.recommendations] == [
        87,
        82,
        75,
        72,
        68,
    ]
    assert all(
        recommendation.supervisor.status is SupervisorLifecycleStatus.VERIFIED
        for recommendation in proposal.recommendations
    )
    assert all(
        recommendation.availability_status is recommendation.supervisor.availability_status
        for recommendation in proposal.recommendations
    )


def test_preliminary_proposal_uses_injected_utc_clock_without_changing_final_timestamp() -> None:
    generated_at = datetime(2026, 8, 29, 14, 45, tzinfo=UTC)

    final_state = _run(
        FakeResearchFitModel(),
        utc_clock=FixedUtcClock(generated_at),
    )

    proposal = final_state["proposed_shortlist"]
    final_shortlist = final_state["supervisor_shortlist"]
    assert proposal is not None
    assert final_shortlist is not None
    assert proposal.generated_at == generated_at
    assert final_shortlist.generated_at == FIXTURE_RETRIEVED_AT


def test_one_model_failure_is_sanitized_while_other_results_survive() -> None:
    baseline = _run(FakeResearchFitModel())
    failed_id = baseline["verified_supervisors"][-1].supervisor_id
    sensitive_message = "secret-key candidate-private@example.test"
    model = FakeResearchFitModel({failed_id: (ResearchFitModelInvocationError(sensitive_message),)})

    final_state = _run(model)

    assert final_state["review_status"] is ReviewStatus.COMPLETED
    assert len(final_state["research_fit_assessments"]) == 7
    fit_error = next(
        error for error in final_state["tool_errors"] if error.node == "evaluate_research_fit"
    )
    assert fit_error.code == "research_fit_model_invocation"
    assert sensitive_message not in fit_error.message
    assert failed_id not in {
        assessment.supervisor_id for assessment in final_state["research_fit_assessments"]
    }


def test_graph_outputs_never_calculate_admission_probability() -> None:
    final_state = _run(FakeResearchFitModel())
    rendered = "\n".join(
        assessment.model_dump_json() for assessment in final_state["research_fit_assessments"]
    ).casefold()
    proposal = final_state["proposed_shortlist"]

    assert proposal is not None
    rendered += proposal.model_dump_json().casefold()
    assert "admission probability" not in rendered
    assert "admission likelihood" not in rendered
