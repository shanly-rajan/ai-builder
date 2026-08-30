"""Explicitly opted-in, call-budgeted live ScholarPath provider canary."""

from __future__ import annotations

import os
from collections import Counter
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl, SecretStr, TypeAdapter, ValidationError

from scholarpath.agents import (
    EvidenceExtractionInput,
    EvidenceVerificationAgent,
    EvidenceVerificationModelPort,
    IndependentReviewAgent,
    IndependentReviewInput,
    IndependentReviewModelPort,
    IndependentReviewResult,
    OpenAIEvidenceVerificationModelAdapter,
    OpenAIPlanningModelAdapter,
    OpenAIResearchFitAdapter,
    PlanningInput,
    PlanningModelPort,
    ResearchFitEvaluationAgent,
    ResearchFitInput,
    ResearchFitModelPort,
    ResearchPlanningAgent,
    ShortlistSynthesisAgent,
    StructuredEvidenceExtractionResult,
    StructuredResearchFitResult,
    StructuredSearchPlanResponse,
    SupervisorDiscoveryAgent,
    canonical_profile_url,
)
from scholarpath.agents.nebius_review import NebiusReviewModelAdapter
from scholarpath.config import (
    Environment,
    LangSmithSettings,
    load_nebius_review_settings,
    load_openai_evidence_settings,
    load_openai_planning_settings,
    load_openai_research_fit_settings,
    load_tavily_extraction_settings,
    load_tavily_search_settings,
    load_you_search_settings,
)
from scholarpath.domain import (
    AvailabilityStatus,
    CandidateProfile,
    CandidateReviewAction,
    CandidateReviewDecision,
    EvidenceClaimType,
    ProspectiveSupervisor,
    ResearchFitRubric,
    SearchPlan,
    SearchResult,
    SearchSourceType,
    SourceKind,
    SupervisorLifecycleStatus,
    create_supervisor_shortlist,
    is_singular_person_profile_url,
    supervisor_names_are_title_equivalent,
)
from scholarpath.graph.verification import classify_evidence_source_kind
from scholarpath.observability import LangSmithObservability
from scholarpath.tools import (
    ContentExtractionPort,
    ExtractedContent,
    SupervisorSearchPort,
    TavilyExtractionAdapter,
    TavilySearchAdapter,
    YouSearchAdapter,
)

_HTTP_URL_ADAPTER = TypeAdapter(HttpUrl)
_LIVE_FLAGS = ("SCHOLARPATH_RUN_LIVE_TESTS", "SCHOLARPATH_RUN_LIVE_CANARY")
_TARGET_SETTINGS = (
    "SCHOLARPATH_LIVE_CANARY_SUPERVISOR_NAME",
    "SCHOLARPATH_LIVE_CANARY_INSTITUTION",
    "SCHOLARPATH_LIVE_CANARY_PROFILE_URL",
)


def _enabled(name: str) -> bool:
    return os.getenv(name, "").strip().casefold() in {"1", "true", "yes"}


def _secret_present(value: SecretStr | None) -> bool:
    return value is not None and bool(value.get_secret_value().strip())


def _normalized_text(value: str) -> str:
    return " ".join(value.casefold().split())


@dataclass(slots=True)
class _CallBudget:
    """Reject a live provider call before it can exceed its explicit ceiling."""

    limits: dict[str, int]
    calls: Counter[str] = field(default_factory=Counter)

    def consume(self, operation: str) -> None:
        limit = self.limits[operation]
        if self.calls[operation] >= limit:
            raise AssertionError(f"Live canary call budget exhausted for {operation}")
        self.calls[operation] += 1


class _BudgetedPlanningModel:
    def __init__(self, delegate: PlanningModelPort, budget: _CallBudget) -> None:
        self._delegate = delegate
        self._budget = budget

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        self._budget.consume("openai_planning")
        return self._delegate.generate(planning_input)


class _BudgetedSearch:
    def __init__(
        self,
        delegate: SupervisorSearchPort,
        budget: _CallBudget,
        operation: str,
    ) -> None:
        self._delegate = delegate
        self._budget = budget
        self._operation = operation

    def search(self, query: str) -> tuple[SearchResult, ...]:
        self._budget.consume(self._operation)
        return self._delegate.search(query)


class _BudgetedExtraction:
    def __init__(self, delegate: ContentExtractionPort, budget: _CallBudget) -> None:
        self._delegate = delegate
        self._budget = budget

    def extract(self, source_url: str | HttpUrl) -> ExtractedContent:
        self._budget.consume("tavily_extract")
        return self._delegate.extract(source_url)


class _BudgetedEvidenceModel:
    def __init__(self, delegate: EvidenceVerificationModelPort, budget: _CallBudget) -> None:
        self._delegate = delegate
        self._budget = budget

    def extract(
        self,
        extraction_input: EvidenceExtractionInput,
    ) -> StructuredEvidenceExtractionResult:
        self._budget.consume("openai_evidence")
        return self._delegate.extract(extraction_input)


class _BudgetedResearchFitModel:
    def __init__(self, delegate: ResearchFitModelPort, budget: _CallBudget) -> None:
        self._delegate = delegate
        self._budget = budget

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        self._budget.consume("openai_research_fit")
        return self._delegate.evaluate(fit_input, rubric)


class _BudgetedReviewModel:
    def __init__(self, delegate: IndependentReviewModelPort, budget: _CallBudget) -> None:
        self._delegate = delegate
        self._budget = budget

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        self._budget.consume("nebius_review")
        return self._delegate.review(review_input)


def _targeted_plan(
    plan: SearchPlan,
    *,
    supervisor_name: str,
    institution: str,
) -> tuple[SearchPlan, str]:
    official_index = next(
        index
        for index, item in enumerate(plan.search_queries)
        if SearchSourceType.OFFICIAL_UNIVERSITY_PROFILE in item.target_source_types
    )
    original = plan.search_queries[official_index]
    targeted_query = f"{supervisor_name} {institution} {original.query}"
    queries = list(plan.search_queries)
    queries[official_index] = original.model_copy(update={"query": targeted_query})
    targeted = SearchPlan.model_validate(
        {
            **plan.model_dump(mode="python"),
            "search_queries": queries,
        }
    )
    return targeted, targeted_query


def _matching_target(
    supervisors: tuple[ProspectiveSupervisor, ...],
    *,
    full_name: str,
    institution: str,
    profile_url: HttpUrl,
) -> ProspectiveSupervisor | None:
    expected_url = canonical_profile_url(str(profile_url))
    return next(
        (
            supervisor
            for supervisor in supervisors
            if supervisor_names_are_title_equivalent(supervisor.full_name, full_name)
            and _normalized_text(supervisor.institution) == _normalized_text(institution)
            and canonical_profile_url(str(supervisor.profile_url)) == expected_url
        ),
        None,
    )


@pytest.mark.live
def test_live_vertical_canary_stays_within_provider_call_budgets() -> None:
    """Exercise one configured public profile without running a costly five-result graph."""
    for flag in _LIVE_FLAGS:
        if not _enabled(flag):
            pytest.skip(f"Set {flag}=true to opt in to the M13 live canary")

    target_values = {name: os.getenv(name, "").strip() for name in _TARGET_SETTINGS}
    missing_target_settings = [name for name, value in target_values.items() if not value]
    if missing_target_settings:
        pytest.skip(
            "The M13 live canary requires these non-secret target settings: "
            + ", ".join(missing_target_settings)
        )

    planning_settings = load_openai_planning_settings()
    evidence_settings = load_openai_evidence_settings()
    research_fit_settings = load_openai_research_fit_settings()
    you_settings = load_you_search_settings()
    tavily_search_settings = load_tavily_search_settings()
    tavily_extraction_settings = load_tavily_extraction_settings()
    nebius_settings = load_nebius_review_settings()
    missing_credentials = []
    if not _secret_present(planning_settings.api_key):
        missing_credentials.append("OPENAI_API_KEY")
    if not _secret_present(evidence_settings.api_key):
        missing_credentials.append("OPENAI_API_KEY")
    if not _secret_present(research_fit_settings.api_key):
        missing_credentials.append("OPENAI_API_KEY")
    if not _secret_present(you_settings.api_key):
        missing_credentials.append("YDC_API_KEY")
    if not _secret_present(tavily_search_settings.api_key):
        missing_credentials.append("TAVILY_API_KEY")
    if not _secret_present(tavily_extraction_settings.api_key):
        missing_credentials.append("TAVILY_API_KEY")
    if not _secret_present(nebius_settings.api_key):
        missing_credentials.append("NEBIUS_API_KEY")
    if missing_credentials:
        pytest.skip(
            "The M13 live canary requires: " + ", ".join(dict.fromkeys(missing_credentials))
        )

    try:
        target_url = _HTTP_URL_ADAPTER.validate_python(
            target_values["SCHOLARPATH_LIVE_CANARY_PROFILE_URL"]
        )
    except ValidationError:
        pytest.fail("The M13 live canary profile URL is invalid", pytrace=False)
    if target_url.scheme != "https":
        pytest.fail("The M13 live canary profile URL must use HTTPS", pytrace=False)
    if not is_singular_person_profile_url(str(target_url)):
        pytest.fail(
            "The M13 live canary profile URL must be a singular person-profile route",
            pytrace=False,
        )
    preflight_source_kind = classify_evidence_source_kind(target_url)
    if preflight_source_kind not in {
        SourceKind.UNIVERSITY_PROFILE,
        SourceKind.INSTITUTIONAL_DIRECTORY,
    }:
        pytest.fail(
            "The M13 live canary target must be an official academic profile",
            pytrace=False,
        )

    budget = _CallBudget(
        limits={
            "openai_planning": 2,
            "you_search": 1,
            "tavily_search": 1,
            "tavily_extract": 1,
            "openai_evidence": 1,
            "openai_research_fit": 2,
            "nebius_review": 1,
        }
    )
    planning_configuration = planning_settings.for_planning_model().model_copy(
        update={"timeout_seconds": min(planning_settings.planning_timeout_seconds, 60.0)}
    )
    you_configuration = you_settings.for_search_adapter().model_copy(
        update={"timeout_seconds": min(you_settings.timeout_seconds, 20.0), "result_count": 3}
    )
    tavily_search_configuration = tavily_search_settings.for_search_adapter().model_copy(
        update={
            "timeout_seconds": min(tavily_search_settings.timeout_seconds, 20.0),
            "result_count": 3,
        }
    )
    extraction_configuration = tavily_extraction_settings.for_extraction_adapter().model_copy(
        update={
            "provider_timeout_seconds": 20,
            "request_timeout_seconds": 25.0,
            "extract_depth": "basic",
            "max_content_characters": 20_000,
        }
    )
    evidence_configuration = evidence_settings.for_evidence_model().model_copy(
        update={"timeout_seconds": min(evidence_settings.evidence_timeout_seconds, 60.0)}
    )
    research_fit_configuration = research_fit_settings.for_research_fit_model().model_copy(
        update={"timeout_seconds": min(research_fit_settings.research_fit_timeout_seconds, 60.0)}
    )
    nebius_configuration = nebius_settings.for_review_model().model_copy(
        update={"timeout_seconds": min(nebius_settings.review_timeout_seconds, 60.0)}
    )
    planning_model = _BudgetedPlanningModel(
        OpenAIPlanningModelAdapter(planning_configuration),
        budget,
    )
    you_search = _BudgetedSearch(
        YouSearchAdapter(you_configuration),
        budget,
        "you_search",
    )
    tavily_search = _BudgetedSearch(
        TavilySearchAdapter(tavily_search_configuration),
        budget,
        "tavily_search",
    )
    content_extractor = _BudgetedExtraction(
        TavilyExtractionAdapter(extraction_configuration),
        budget,
    )
    evidence_model = _BudgetedEvidenceModel(
        OpenAIEvidenceVerificationModelAdapter(evidence_configuration),
        budget,
    )
    research_fit_model = _BudgetedResearchFitModel(
        OpenAIResearchFitAdapter(research_fit_configuration),
        budget,
    )
    review_model = _BudgetedReviewModel(
        NebiusReviewModelAdapter(nebius_configuration),
        budget,
    )
    observability = LangSmithObservability(LangSmithSettings(tracing=False), Environment.TEST)
    profile = CandidateProfile(
        candidate_id="candidate-m13-live-canary",
        proposed_research_statement=(
            "Evaluate applied enterprise architecture controls for responsible AI systems."
        ),
        research_topics=("enterprise architecture", "responsible AI governance"),
        preferred_regions=(),
        preferred_study_modes=(),
        preferred_research_orientation="applied",
        methodological_interests=("design science",),
        exclusions=(),
    )

    with observability.activate():
        plan = ResearchPlanningAgent(planning_model).plan(
            profile,
            (),
            target_regions=(),
            exclusions=(),
        )
        targeted_plan, query = _targeted_plan(
            plan,
            supervisor_name=target_values["SCHOLARPATH_LIVE_CANARY_SUPERVISOR_NAME"],
            institution=target_values["SCHOLARPATH_LIVE_CANARY_INSTITUTION"],
        )
        discovery_agent = SupervisorDiscoveryAgent()
        results = you_search.search(query)
        discovery = discovery_agent.discover(targeted_plan, results)
        prospective = _matching_target(
            discovery.prospective_supervisors,
            full_name=target_values["SCHOLARPATH_LIVE_CANARY_SUPERVISOR_NAME"],
            institution=target_values["SCHOLARPATH_LIVE_CANARY_INSTITUTION"],
            profile_url=target_url,
        )
        if prospective is None:
            fallback_results = tavily_search.search(query)
            discovery = discovery_agent.discover(
                targeted_plan,
                (*results, *fallback_results),
            )
            prospective = _matching_target(
                discovery.prospective_supervisors,
                full_name=target_values["SCHOLARPATH_LIVE_CANARY_SUPERVISOR_NAME"],
                institution=target_values["SCHOLARPATH_LIVE_CANARY_INSTITUTION"],
                profile_url=target_url,
            )
        if prospective is None:
            pytest.fail(
                "The live search providers did not recover the configured target profile",
                pytrace=False,
            )

        extracted_content = content_extractor.extract(prospective.profile_url)
        source_kind = classify_evidence_source_kind(
            extracted_content.source_url,
            title=prospective.full_name,
        )
        evidence_agent = EvidenceVerificationAgent(evidence_model)
        claims = evidence_agent.extract_claims(prospective, extracted_content, source_kind)
        verification = evidence_agent.build_verification_record(prospective, claims)
        verified = verification.verified_supervisor
        if verified is None:
            pytest.fail(
                "The configured live profile did not satisfy the verification minimum",
                pytrace=False,
            )

        assessment = ResearchFitEvaluationAgent(research_fit_model).evaluate(profile, verified)
        reviewed = IndependentReviewAgent(review_model).review(profile, verified, assessment)
        proposal = ShortlistSynthesisAgent(max_results=1).synthesize(
            profile.candidate_id,
            (verified,),
            (assessment,),
            datetime.now(UTC),
            (reviewed,),
        )

    assert prospective.status is SupervisorLifecycleStatus.PROSPECTIVE
    assert verified.status is SupervisorLifecycleStatus.VERIFIED
    availability_claims = tuple(
        claim for claim in verified.evidence if claim.claim_type is EvidenceClaimType.AVAILABILITY
    )
    if not availability_claims:
        assert verified.availability_status is AvailabilityStatus.NOT_STATED
    assert len(proposal.recommendations) == 1
    assert proposal.recommendations[0].supervisor.status is SupervisorLifecycleStatus.VERIFIED

    approval = CandidateReviewDecision(
        action=CandidateReviewAction.APPROVE,
        supervisor_ids=(verified.supervisor_id,),
        reason="Explicit approval for the opt-in live canary.",
    )
    shortlist = create_supervisor_shortlist(
        profile.candidate_id,
        (verified,),
        approval,
        generated_at=datetime.now(UTC),
        briefing="One explicitly approved, evidence-backed live canary result.",
    )
    assert shortlist.shortlisted_supervisors[0].status is SupervisorLifecycleStatus.SHORTLISTED
    assert budget.calls["openai_planning"] in {1, 2}
    assert budget.calls["you_search"] == 1
    assert budget.calls["tavily_search"] in {0, 1}
    assert budget.calls["tavily_extract"] == 1
    assert budget.calls["openai_evidence"] == 1
    assert budget.calls["openai_research_fit"] in {1, 2}
    assert budget.calls["nebius_review"] == 1
    assert sum(budget.calls.values()) <= 9
    assert all(
        forbidden not in payload.casefold()
        for payload in (
            assessment.model_dump_json(),
            reviewed.model_dump_json(),
            proposal.model_dump_json(),
            shortlist.model_dump_json(),
        )
        for forbidden in ("admission probability", "chance of admission")
    )
