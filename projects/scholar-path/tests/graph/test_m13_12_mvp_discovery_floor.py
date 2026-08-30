"""Regression tests for aligning the implicit MVP discovery and verification floors."""

from typing import cast

from scholarpath.config import ApplicationSettings, Environment, LangSmithSettings, LogLevel
from scholarpath.domain import SearchResult, VerificationEvidenceStandard
from scholarpath.graph import (
    DiscoveryPolicy,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    VerificationPolicy,
    candidate_review_payload_from_graph_output,
    run_scholarpath_graph,
)
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_fake_search_outcomes,
)


def _three_prospective_outcomes() -> dict[str, tuple[SearchResult, ...]]:
    remaining = 3
    outcomes: dict[str, tuple[SearchResult, ...]] = {}
    for query, results in make_fake_search_outcomes().items():
        selected = results[:remaining]
        outcomes[query] = selected
        remaining -= len(selected)
    assert remaining == 0
    return outcomes


def _empty_outcomes() -> dict[str, tuple[SearchResult, ...]]:
    return {query: () for query in make_fake_search_outcomes()}


def _run_with_exactly_three_prospective_supervisors(
    standard: VerificationEvidenceStandard,
    *,
    config: GraphFixtureConfig | None = None,
) -> tuple[ScholarPathState, FakeSupervisorSearch, FakeSupervisorSearch]:
    you_search = FakeSupervisorSearch(_three_prospective_outcomes())
    tavily_search = FakeSupervisorSearch(_empty_outcomes())
    output = run_scholarpath_graph(
        config,
        thread_id=f"m13-12-{standard.value}-{config is not None}",
        planning_model=FakePlanningModel(),
        supervisor_search=you_search,
        tavily_search=tavily_search,
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        candidate_preference_memory=FakeCandidatePreferenceMemory(),
        alternate_evidence_search=tavily_search,
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            log_level=LogLevel.ERROR,
            verification_evidence_standard=standard,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
    )
    return cast(ScholarPathState, output), you_search, tavily_search


def test_implicit_policy_floors_follow_the_closed_verification_standard() -> None:
    strict = GraphFixtureConfig.for_verification_standard(VerificationEvidenceStandard.STRICT)
    mvp = GraphFixtureConfig.for_verification_standard(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )

    assert strict.discovery_policy.minimum_unique_supervisors == 5
    assert strict.verification_policy.minimum_verified_supervisors == 5
    assert mvp.discovery_policy.minimum_unique_supervisors == 3
    assert mvp.verification_policy.minimum_verified_supervisors == 3
    assert DiscoveryPolicy().minimum_unique_supervisors == 5


def test_exactly_three_mvp_prospective_supervisors_reach_candidate_review() -> None:
    state, _, tavily_search = _run_with_exactly_three_prospective_supervisors(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )

    assert state["review_status"] is ReviewStatus.PROPOSED
    assert len(state["prospective_supervisors"]) == 3
    assert len(state["verified_supervisors"]) == 3
    assert "deduplicate_supervisors" in state["execution_log"]
    assert "extract_supervisor_evidence" in state["execution_log"]
    assert candidate_review_payload_from_graph_output(state) is not None
    assert tavily_search.calls == []
    assert state["shortlisted_supervisors"] == []


def test_exactly_three_strict_prospective_supervisors_stop_at_discovery() -> None:
    state, _, tavily_search = _run_with_exactly_three_prospective_supervisors(
        VerificationEvidenceStandard.STRICT
    )

    assert state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE
    assert len(state["prospective_supervisors"]) == 3
    assert state["verified_supervisors"] == []
    assert "deduplicate_supervisors" not in state["execution_log"]
    assert "extract_supervisor_evidence" not in state["execution_log"]
    assert len(tavily_search.calls) == 4


def test_explicit_mvp_discovery_override_remains_authoritative() -> None:
    explicit_config = GraphFixtureConfig(
        discovery_policy=DiscoveryPolicy(minimum_unique_supervisors=4),
        verification_policy=VerificationPolicy(
            verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
        ),
    )

    state, _, _ = _run_with_exactly_three_prospective_supervisors(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
        config=explicit_config,
    )

    assert state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE
    assert "extract_supervisor_evidence" not in state["execution_log"]
