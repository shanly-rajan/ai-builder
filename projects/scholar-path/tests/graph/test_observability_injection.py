"""Graph execution accepts a caller-owned tracing scope without replacing it."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import TypedDict, cast

import pytest

from scholarpath.agents import PlanningInput, StructuredSearchPlanResponse
from scholarpath.config import ApplicationSettings, Environment, LangSmithSettings
from scholarpath.graph import (
    CandidateApproveResponse,
    ReviewStatus,
    ScholarPathState,
    build_scholarpath_runtime,
    default_review_decision,
    run_scholarpath_graph,
)
from scholarpath.observability import LangSmithObservability
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
)


class FakePorts(TypedDict):
    planning_model: FakePlanningModel
    supervisor_search: FakeSupervisorSearch
    tavily_search: FakeSupervisorSearch
    content_extractor: FakeContentExtraction
    evidence_model: FakeEvidenceVerificationModel
    research_fit_model: FakeResearchFitModel
    independent_review_model: FakeIndependentReviewModel
    candidate_preference_memory: FakeCandidatePreferenceMemory
    alternate_evidence_search: FakeSupervisorSearch


@pytest.fixture
def fake_ports() -> FakePorts:
    return FakePorts(
        planning_model=FakePlanningModel(),
        supervisor_search=FakeSupervisorSearch(),
        tavily_search=FakeSupervisorSearch(),
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        candidate_preference_memory=FakeCandidatePreferenceMemory(),
        alternate_evidence_search=FakeSupervisorSearch(),
    )


class RecordingObservability(LangSmithObservability):
    """Record activation boundaries while explicitly retaining offline tracing."""

    def __init__(self) -> None:
        super().__init__(LangSmithSettings(tracing=False), Environment.TEST)
        self.entered = 0
        self.exited = 0
        self.active = False

    @contextmanager
    def activate(self) -> Iterator[None]:
        self.entered += 1
        self.active = True
        try:
            with super().activate():
                yield
        finally:
            self.active = False
            self.exited += 1


class ScopeCheckingPlanningModel(FakePlanningModel):
    def __init__(self, observability: RecordingObservability) -> None:
        super().__init__()
        self.observability = observability

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        assert self.observability.active, "Graph providers must run inside the supplied scope"
        return super().generate(planning_input)


def test_runtime_retains_supplied_observability_without_loading_tracing_settings(
    fake_ports: FakePorts,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observability = RecordingObservability()

    def unexpected_settings_load() -> LangSmithSettings:
        raise AssertionError("Injected observability must own its configuration")

    monkeypatch.setattr(
        "scholarpath.graph.workflow.load_langsmith_settings", unexpected_settings_load
    )

    runtime = build_scholarpath_runtime(
        **fake_ports,
        observability=observability,
        application_settings=ApplicationSettings(environment=Environment.TEST),
    )

    assert runtime.observability is observability
    assert observability.entered == 0


def test_run_activates_supplied_scope_for_execution_and_approval_resume(
    fake_ports: FakePorts,
) -> None:
    observability = RecordingObservability()
    fake_ports["planning_model"] = ScopeCheckingPlanningModel(observability)
    approval = CandidateApproveResponse(
        action="approve", supervisor_ids=default_review_decision().supervisor_ids
    )

    state = cast(
        ScholarPathState,
        run_scholarpath_graph(
            **fake_ports,
            observability=observability,
            thread_id="observability-injection-test",
            candidate_review_responses=(approval,),
            application_settings=ApplicationSettings(environment=Environment.TEST),
        ),
    )

    assert state["review_status"] is ReviewStatus.COMPLETED
    assert len(state["shortlisted_supervisors"]) == 5
    assert state["execution_log"][-1] == "generate_shortlist_briefing"
    assert observability.entered == observability.exited == 1
    assert observability.active is False


def test_default_runtime_still_builds_settings_based_observability(fake_ports: FakePorts) -> None:
    runtime = build_scholarpath_runtime(
        **fake_ports,
        application_settings=ApplicationSettings(environment=Environment.TEST),
        langsmith_settings=LangSmithSettings(tracing=False),
    )

    assert type(runtime.observability) is LangSmithObservability
    assert "environment:test" in runtime.observability.tags
