"""Offline M11.3 regressions for realistic academic-profile discovery context."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import cast

import pytest
from pydantic import HttpUrl

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
)
from scholarpath.domain import SearchResult
from scholarpath.graph import (
    CandidateApproveResponse,
    DiscoveryPolicy,
    GraphFixtureConfig,
    ReviewStatus,
    ScholarPathState,
    build_walking_skeleton_fixtures,
    default_review_decision,
    run_scholarpath_graph,
)
from scholarpath.tools import SearchProvider
from tests.fakes import (
    FakeCandidatePreferenceMemory,
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
    make_graph_content_outcomes,
    make_graph_evidence_outcomes,
    make_valid_planning_response,
)

_ACADEMIC_TITLE_PREFIX = re.compile(r"^(?:Professor|Dr)\s+")
_LIVE_ADAPTER_NAMES = (
    "YouSearchAdapter",
    "TavilySearchAdapter",
    "TavilyExtractionAdapter",
    "OpenAIPlanningModelAdapter",
    "OpenAIEvidenceVerificationModelAdapter",
    "OpenAIResearchFitAdapter",
    "NebiusReviewModelAdapter",
    "Mem0CandidatePreferenceAdapter",
)


@dataclass(frozen=True, slots=True)
class _OfflineRun:
    state: ScholarPathState
    primary_search: FakeSupervisorSearch
    tavily_search: FakeSupervisorSearch
    content_extractor: FakeContentExtraction


@pytest.fixture(autouse=True)
def _forbid_live_adapter_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail immediately if the offline regression crosses a production boundary."""

    def fail_if_constructed(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("M11.3 graph regressions must use injected offline fakes")

    for adapter_name in _LIVE_ADAPTER_NAMES:
        monkeypatch.setattr(
            f"scholarpath.graph.workflow.{adapter_name}",
            fail_if_constructed,
        )


def _planned_queries() -> tuple[str, ...]:
    return tuple(item.query for item in make_valid_planning_response().search_queries)


def _search_outcomes(
    results: tuple[SearchResult, ...],
) -> dict[str, tuple[SearchResult, ...]]:
    queries = _planned_queries()
    return {query: results if index == 0 else () for index, query in enumerate(queries)}


def _run_offline(
    outcomes: dict[str, tuple[SearchResult, ...]],
    *,
    discovery_policy: DiscoveryPolicy | None = None,
    remapped_profile_results: tuple[SearchResult, ...] | None = None,
) -> _OfflineRun:
    primary_search = FakeSupervisorSearch(outcomes)
    tavily_search = FakeSupervisorSearch()
    evidence_model = FakeEvidenceVerificationModel()
    content_extractor = FakeContentExtraction()
    if remapped_profile_results is not None:
        profiles = build_walking_skeleton_fixtures().raw_search_results[
            : len(remapped_profile_results)
        ]
        base_content = make_graph_content_outcomes()
        base_evidence = make_graph_evidence_outcomes()
        content_extractor = FakeContentExtraction(
            {
                str(result.url): base_content[str(profile.profile_url)].model_copy(
                    update={"source_url": result.url}
                )
                for profile, result in zip(
                    profiles,
                    remapped_profile_results,
                    strict=True,
                )
            }
        )
        evidence_model = FakeEvidenceVerificationModel(
            {
                str(result.url): base_evidence[str(profile.profile_url)]
                for profile, result in zip(
                    profiles,
                    remapped_profile_results,
                    strict=True,
                )
            }
        )
    approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )
    output = run_scholarpath_graph(
        GraphFixtureConfig(
            discovery_policy=discovery_policy or DiscoveryPolicy(),
        ),
        thread_id="m11-3-offline-academic-profile-regression",
        candidate_review_responses=(approval,),
        planning_model=FakePlanningModel(),
        candidate_preference_memory=FakeCandidatePreferenceMemory(),
        supervisor_search=primary_search,
        tavily_search=tavily_search,
        content_extractor=content_extractor,
        evidence_model=evidence_model,
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        alternate_evidence_search=FakeSupervisorSearch(),
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.OFF,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
    )
    return _OfflineRun(
        state=cast(ScholarPathState, output),
        primary_search=primary_search,
        tavily_search=tavily_search,
        content_extractor=content_extractor,
    )


def _untitled_academic_profile_results() -> tuple[SearchResult, ...]:
    query = _planned_queries()[0]
    profiles = build_walking_skeleton_fixtures().raw_search_results[:6]
    results: list[SearchResult] = []
    for profile in profiles:
        untitled_name = _ACADEMIC_TITLE_PREFIX.sub("", profile.full_name)
        profile_slug = re.sub(r"[^a-z0-9]+", "-", untitled_name.casefold()).strip("-")
        results.append(
            SearchResult(
                url=HttpUrl(f"https://profiles.scholarpath.example/persons/{profile_slug}"),
                title=f"{untitled_name} | {profile.institution}",
                description=(
                    f"{untitled_name}'s research focuses on enterprise architecture and "
                    "responsible AI governance."
                ),
                snippets=("Official institutional profile page.",),
                originating_query=query,
            )
        )
    return tuple(results)


def _generic_topic_results() -> tuple[SearchResult, ...]:
    query = _planned_queries()[0]
    profiles = build_walking_skeleton_fixtures().raw_search_results[:6]
    topics = (
        "Enterprise Architecture Research",
        "Responsible AI Governance",
        "Digital Transformation Research",
        "Organisational Resilience",
        "Information Systems Research",
        "Sociotechnical Systems",
    )
    return tuple(
        SearchResult(
            url=HttpUrl(f"https://profiles.scholarpath.example/research/topic-{index}"),
            title=f"{topic} | {profile.institution}",
            description=(
                f"Explore the {topic.casefold()} themes and publications at {profile.institution}."
            ),
            originating_query=query,
        )
        for index, (profile, topic) in enumerate(zip(profiles, topics, strict=True), start=1)
    )


def test_m11_3_untitled_academic_profiles_continue_downstream_without_tavily() -> None:
    results = _untitled_academic_profile_results()

    run = _run_offline(
        _search_outcomes(results),
        remapped_profile_results=results,
    )

    retained = run.state["prospective_supervisors"]
    assert len(retained) == 6
    assert {item.full_name for item in retained} == {
        "Amara Ndlovu",
        "Elias Hart",
        "Noor van Dijk",
        "Sofia Mensah",
        "Theo Laurent",
        "Lina Okafor",
    }
    assert run.state["fallback_search_used"] is False
    assert run.tavily_search.calls == []
    assert {attempt.provider_used for attempt in run.state["search_attempts"]} == {
        SearchProvider.YOU
    }
    assert "deduplicate_supervisors" in run.state["execution_log"]
    assert "extract_supervisor_evidence" in run.state["execution_log"]
    assert set(run.content_extractor.calls) == {str(result.url) for result in results}
    assert run.state["review_status"] is not ReviewStatus.DISCOVERY_INCOMPLETE


def test_m11_3_generic_topic_layouts_do_not_create_prospective_supervisors() -> None:
    results = _generic_topic_results()

    run = _run_offline(
        _search_outcomes(results),
        discovery_policy=DiscoveryPolicy(
            maximum_you_retry_count=0,
            maximum_tavily_fallback_count=0,
        ),
    )

    assert run.state["prospective_supervisors"] == []
    assert run.state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE
    assert run.state["fallback_search_used"] is False
    assert run.tavily_search.calls == []
    assert run.content_extractor.calls == []
    assert all(attempt.plausible_supervisor_count == 0 for attempt in run.state["search_attempts"])
