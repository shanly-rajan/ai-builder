"""LangSmith-compatible target functions for ScholarPath evaluation scenarios."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from typing import Literal, cast

from ..agents import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    INDEPENDENT_REVIEW_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    RESEARCH_PLANNING_PROMPT_VERSION,
    EvidenceVerificationAgent,
    EvidenceVerificationModelPort,
    IndependentReviewPolicy,
    IndependentReviewResult,
    PlanningModelPort,
    ResearchFitEvaluationAgent,
    ResearchFitModelPort,
    ResearchPlanningAgent,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
)
from ..config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    EvaluationSettings,
    LangSmithSettings,
    load_settings,
)
from ..domain import (
    CandidatePreferenceRevision,
    CandidateProfile,
    EvidenceClaim,
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewDecision,
    ResearchFitRubric,
    SearchResult,
    SourceKind,
    SupervisorVerificationRecord,
    VerifiedSupervisor,
)
from ..graph import (
    CandidateRejectionReason,
    CandidateRejectResponse,
    GraphFixtureConfig,
    ScholarPathState,
    build_walking_skeleton_fixtures,
    candidate_review_payload_from_graph_output,
    create_test_checkpointer,
    run_scholarpath_graph,
)
from ..observability import GRAPH_VERSION
from ..tools import (
    ContentExtractionError,
    ContentExtractionErrorCategory,
    ContentExtractionProvider,
    ExtractedContent,
    SupervisorSearchTimeoutError,
)
from .fakes import (
    EVALUATION_RETRIEVED_AT,
    FixedEvaluationClock,
    InMemoryCandidatePreferenceMemory,
    ScriptedContentExtraction,
    ScriptedEvidenceModel,
    ScriptedIndependentReviewModel,
    ScriptedResearchFitModel,
    ScriptedSupervisorSearch,
    StaticPlanningModel,
    make_evaluation_evidence_outcomes,
    make_evaluation_planning_response,
    make_evaluation_search_outcomes,
    make_weak_research_fit_response,
)
from .models import (
    CandidatePreferenceProjection,
    CandidateReviewOutcome,
    CandidateReviewProjection,
    EvaluationScenario,
    EvaluationTargetKind,
    EvidenceReferenceProjection,
    EvidenceVerificationTargetOutput,
    GraphTargetOutput,
    IndependentReviewProjection,
    ResearchFitAssessmentProjection,
    ResearchFitTargetOutput,
    SearchAttemptProjection,
    SearchPlanningTargetOutput,
    ShortlistRecommendationProjection,
    SupervisorProvenanceProjection,
    VerificationRecordProjection,
)
from .tracing import EvaluationTraceContext, tag_current_evaluation_run

type EvaluationTarget = Callable[[dict[str, object]], dict[str, object]]
type GraphTargetKind = Literal[
    EvaluationTargetKind.GRAPH_FAKE,
    EvaluationTargetKind.GRAPH_LIVE,
]

_GRAPH_PROMPT_VERSIONS = (
    RESEARCH_PLANNING_PROMPT_VERSION,
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    RESEARCH_FIT_PROMPT_VERSION,
    INDEPENDENT_REVIEW_PROMPT_VERSION,
)


def _model_provider_label(model: object) -> str:
    """Return a coarse provider label without serializing model configuration."""
    qualified_name = f"{model.__class__.__module__}.{model.__class__.__name__}".casefold()
    if "openai" in qualified_name:
        return "openai"
    if "nebius" in qualified_name:
        return "nebius"
    return "fake"


def _tag_target_run(
    scenario: EvaluationScenario,
    *,
    target: EvaluationTargetKind,
    prompt_versions: tuple[str, ...],
    model_providers: tuple[str, ...],
    environment: str,
    fallback_search_used: bool | None = None,
    candidate_review_outcome: CandidateReviewOutcome = (CandidateReviewOutcome.NOT_APPLICABLE),
    completed: bool = True,
) -> None:
    """Attach only allowlisted evaluation dimensions to an active target trace."""
    tag_current_evaluation_run(
        EvaluationTraceContext(
            scenario_id=scenario.scenario_id,
            target=target,
            environment=environment,
            graph_version=GRAPH_VERSION,
            prompt_versions=prompt_versions,
            model_providers=model_providers,
            fallback_search_used=fallback_search_used,
            candidate_review_outcome=candidate_review_outcome,
        ),
        include_static=not completed,
        include_dynamic=completed,
    )


def _scenario_from_inputs(inputs: Mapping[str, object]) -> EvaluationScenario:
    raw_scenario = inputs.get("scenario", inputs)
    return EvaluationScenario.model_validate(raw_scenario)


def _require_target(
    scenario: EvaluationScenario,
    expected_target: EvaluationTargetKind,
) -> None:
    if scenario.target is not expected_target:
        raise ValueError(
            f"Scenario {scenario.scenario_id!r} targets {scenario.target.value}, "
            f"not {expected_target.value}."
        )


def _preferences(scenario: EvaluationScenario) -> CandidatePreferenceProjection:
    if scenario.candidate_preferences is None:
        raise ValueError(f"Scenario {scenario.scenario_id!r} requires Candidate preferences")
    return scenario.candidate_preferences


def _candidate_profile(scenario: EvaluationScenario) -> CandidateProfile:
    preferences = _preferences(scenario)
    return CandidateProfile(
        candidate_id=f"evaluation-{scenario.scenario_id}",
        proposed_research_statement=(
            "A synthetic research-degree statement combining the supplied research themes, "
            "orientation, methods, and practical constraints."
        ),
        research_topics=preferences.research_topics,
        preferred_regions=preferences.preferred_regions,
        preferred_study_modes=preferences.preferred_study_modes,
        preferred_research_orientation=preferences.preferred_research_orientation,
        methodological_interests=preferences.methodological_interests,
        exclusions=preferences.exclusions,
    )


def _preference_revision(scenario: EvaluationScenario) -> CandidatePreferenceRevision:
    preferences = _preferences(scenario)
    return CandidatePreferenceRevision(
        research_topics=preferences.research_topics,
        preferred_regions=preferences.preferred_regions,
        preferred_study_modes=preferences.preferred_study_modes,
        preferred_research_orientation=preferences.preferred_research_orientation,
        methodological_interests=preferences.methodological_interests,
        exclusions=preferences.exclusions,
    )


def _config_int(scenario: EvaluationScenario, key: str, default: int) -> int:
    value = scenario.config.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"Scenario config {key!r} must be an integer")
    return value


def _config_str(scenario: EvaluationScenario, key: str, default: str) -> str:
    value = scenario.config.get(key, default)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Scenario config {key!r} must be non-empty text")
    return value


def _evidence_projection(claim: EvidenceClaim) -> EvidenceReferenceProjection:
    return EvidenceReferenceProjection(
        evidence_id=claim.evidence_id,
        supervisor_id=claim.supervisor_id,
        claim_type=claim.claim_type,
        claim_summary=claim.claim,
        source_url=claim.source_url,
        directly_supported=claim.directly_supported,
        confidence=claim.confidence,
        availability_status=claim.availability_status,
    )


def _verification_projection(
    record: SupervisorVerificationRecord,
) -> VerificationRecordProjection:
    return VerificationRecordProjection(
        supervisor_id=record.prospective_supervisor.supervisor_id,
        verification_status=record.verification_status,
        availability_status=record.availability_status,
        evidence=tuple(_evidence_projection(claim) for claim in record.evidence),
        verification_concerns=record.verification_concerns,
        missing_required_evidence=record.missing_required_evidence,
        verified_supervisor_present=record.verified_supervisor is not None,
    )


def _fit_projection(
    assessment: object,
    supervisor: VerifiedSupervisor,
) -> ResearchFitAssessmentProjection:
    from ..domain import ResearchFitAssessment

    validated_assessment = ResearchFitAssessment.model_validate(assessment)
    return ResearchFitAssessmentProjection(
        assessment=validated_assessment,
        evidence=tuple(_evidence_projection(claim) for claim in supervisor.evidence),
    )


def make_search_planning_target(
    model: PlanningModelPort | None = None,
) -> EvaluationTarget:
    """Create a planning target backed by an injected structured model port."""
    resolved_model = model or StaticPlanningModel()

    def target(inputs: dict[str, object]) -> dict[str, object]:
        scenario = _scenario_from_inputs(inputs)
        _require_target(scenario, EvaluationTargetKind.SEARCH_PLANNING)
        _tag_target_run(
            scenario,
            target=EvaluationTargetKind.SEARCH_PLANNING,
            prompt_versions=(RESEARCH_PLANNING_PROMPT_VERSION,),
            model_providers=(_model_provider_label(resolved_model),),
            environment=Environment.TEST.value,
            completed=False,
        )
        profile = _candidate_profile(scenario)
        preference = _preference_revision(scenario)
        plan = ResearchPlanningAgent(resolved_model).plan(
            profile,
            (preference,),
            target_regions=preference.preferred_regions or profile.preferred_regions,
            exclusions=preference.exclusions or profile.exclusions,
        )
        output = SearchPlanningTargetOutput(
            target=EvaluationTargetKind.SEARCH_PLANNING,
            scenario_id=scenario.scenario_id,
            search_plan=plan,
        )
        _tag_target_run(
            scenario,
            target=EvaluationTargetKind.SEARCH_PLANNING,
            prompt_versions=(RESEARCH_PLANNING_PROMPT_VERSION,),
            model_providers=(_model_provider_label(resolved_model),),
            environment=Environment.TEST.value,
        )
        return output.model_dump(mode="json")

    return target


def _conflicting_affiliation_source(
    supervisor: object,
) -> tuple[ExtractedContent, StructuredEvidenceExtractionResult]:
    from ..domain import ProspectiveSupervisor

    prospective = ProspectiveSupervisor.model_validate(supervisor)
    source_url = "https://directory.northbridge.example/evaluation/affiliation-conflict"
    identity_excerpt = f"The official directory names {prospective.full_name}."
    affiliation_excerpt = (
        f"{prospective.full_name} is Professor in School of Computing and Strategy at "
        "Northbridge University."
    )
    research_excerpt = (
        f"{prospective.full_name}'s current research interests include enterprise architecture "
        "and responsible AI governance."
    )
    content = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": "\n".join((identity_excerpt, affiliation_excerpt, research_excerpt)),
            "retrieved_at": EVALUATION_RETRIEVED_AT,
        }
    )
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.IDENTITY,
                claim=f"The official directory identifies {prospective.full_name}.",
                supporting_excerpt=identity_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=prospective.full_name,
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim="The directory asserts a current role at Northbridge University.",
                supporting_excerpt=affiliation_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=prospective.full_name,
                asserted_institution="Northbridge University",
                asserted_department="School of Computing and Strategy",
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.RESEARCH_INTEREST,
                claim="The directory states enterprise architecture and responsible AI work.",
                supporting_excerpt=research_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=prospective.full_name,
            ),
        ]
    )
    return content, response


def make_evidence_verification_target(
    model: EvidenceVerificationModelPort | None = None,
) -> EvaluationTarget:
    """Create an evidence target using an injected extraction-model boundary."""

    def target(inputs: dict[str, object]) -> dict[str, object]:
        scenario = _scenario_from_inputs(inputs)
        _require_target(scenario, EvaluationTargetKind.EVIDENCE_VERIFICATION)
        _tag_target_run(
            scenario,
            target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
            prompt_versions=(EVIDENCE_VERIFICATION_PROMPT_VERSION,),
            model_providers=("fake" if model is None else _model_provider_label(model),),
            environment=Environment.TEST.value,
            completed=False,
        )
        fixtures = build_walking_skeleton_fixtures()
        index = _config_int(scenario, "supervisor_index", 1)
        if not 1 <= index <= len(fixtures.raw_search_results):
            raise ValueError("supervisor_index is outside the synthetic fixture cohort")
        supervisor = fixtures.raw_search_results[index - 1].to_prospective_supervisor()
        content_outcomes, evidence_outcomes = make_evaluation_evidence_outcomes(fixtures)
        source_urls = [str(supervisor.profile_url)]
        if _config_str(scenario, "evidence_case", "not_stated") == "affiliation_conflict":
            conflict_content, conflict_response = _conflicting_affiliation_source(supervisor)
            conflict_url = str(conflict_content.source_url)
            content_outcomes[conflict_url] = conflict_content
            evidence_outcomes[conflict_url] = conflict_response
            source_urls.append(conflict_url)
        resolved_model = model or ScriptedEvidenceModel(evidence_outcomes)
        agent = EvidenceVerificationAgent(resolved_model)
        evidence: list[EvidenceClaim] = []
        for source_url in source_urls:
            page = content_outcomes[source_url]
            evidence.extend(
                agent.extract_claims(
                    supervisor,
                    page,
                    SourceKind.UNIVERSITY_PROFILE,
                )
            )
        record = agent.build_verification_record(supervisor, tuple(evidence))
        output = EvidenceVerificationTargetOutput(
            target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
            scenario_id=scenario.scenario_id,
            verification_records=(_verification_projection(record),),
        )
        _tag_target_run(
            scenario,
            target=EvaluationTargetKind.EVIDENCE_VERIFICATION,
            prompt_versions=(EVIDENCE_VERIFICATION_PROMPT_VERSION,),
            model_providers=(_model_provider_label(resolved_model),),
            environment=Environment.TEST.value,
        )
        return output.model_dump(mode="json")

    return target


def make_research_fit_target(
    model: ResearchFitModelPort | None = None,
) -> EvaluationTarget:
    """Create a Research Fit target backed by an injected structured model port."""

    def target(inputs: dict[str, object]) -> dict[str, object]:
        scenario = _scenario_from_inputs(inputs)
        _require_target(scenario, EvaluationTargetKind.RESEARCH_FIT)
        _tag_target_run(
            scenario,
            target=EvaluationTargetKind.RESEARCH_FIT,
            prompt_versions=(RESEARCH_FIT_PROMPT_VERSION,),
            model_providers=("fake" if model is None else _model_provider_label(model),),
            environment=Environment.TEST.value,
            completed=False,
        )
        fixtures = build_walking_skeleton_fixtures()
        index = _config_int(scenario, "supervisor_index", 1)
        if not 1 <= index <= len(fixtures.verified_supervisors):
            raise ValueError("supervisor_index is outside the Verified Supervisor cohort")
        supervisor = fixtures.verified_supervisors[index - 1]
        fit_case = _config_str(scenario, "fit_case", "strong")
        resolved_model = model
        if resolved_model is None:
            outcomes = (
                {supervisor.supervisor_id: (make_weak_research_fit_response(),)}
                if fit_case == "superficial"
                else None
            )
            resolved_model = ScriptedResearchFitModel(outcomes)
        assessment = ResearchFitEvaluationAgent(resolved_model).evaluate(
            _candidate_profile(scenario),
            supervisor,
            preferences=_preference_revision(scenario),
            rubric=ResearchFitRubric(),
        )
        output = ResearchFitTargetOutput(
            target=EvaluationTargetKind.RESEARCH_FIT,
            scenario_id=scenario.scenario_id,
            candidate_preferences=_preferences(scenario),
            assessments=(_fit_projection(assessment, supervisor),),
        )
        _tag_target_run(
            scenario,
            target=EvaluationTargetKind.RESEARCH_FIT,
            prompt_versions=(RESEARCH_FIT_PROMPT_VERSION,),
            model_providers=(_model_provider_label(resolved_model),),
            environment=Environment.TEST.value,
        )
        return output.model_dump(mode="json")

    return target


def search_planning_target(inputs: dict[str, object]) -> dict[str, object]:
    """Evaluate search planning with the deterministic default model."""
    return make_search_planning_target()(inputs)


def evidence_verification_target(inputs: dict[str, object]) -> dict[str, object]:
    """Evaluate evidence verification with source-keyed structured fixtures."""
    return make_evidence_verification_target()(inputs)


def research_fit_target(inputs: dict[str, object]) -> dict[str, object]:
    """Evaluate Research Fit with the deterministic evidence-cited model."""
    return make_research_fit_target()(inputs)


def _duplicate_search_outcomes() -> dict[str, tuple[SearchResult, ...]]:
    outcomes = make_evaluation_search_outcomes()
    queries = tuple(outcomes)
    duplicate = outcomes[queries[0]][0].model_copy(update={"originating_query": queries[1]})
    outcomes[queries[1]] = (duplicate, *outcomes[queries[1]])
    return outcomes


def _graph_state(output: ScholarPathState | dict[str, object]) -> ScholarPathState:
    return cast(ScholarPathState, output)


def _candidate_review_outcome(
    output: ScholarPathState | dict[str, object],
) -> CandidateReviewOutcome:
    """Project the latest explicit action or the current review interrupt."""
    state = _graph_state(output)
    if state["candidate_feedback"]:
        return CandidateReviewOutcome(state["candidate_feedback"][-1].action.value)
    if candidate_review_payload_from_graph_output(output) is not None:
        return CandidateReviewOutcome.AWAITING_REVIEW
    return CandidateReviewOutcome.NOT_APPLICABLE


def _project_graph_output(
    scenario: EvaluationScenario,
    output: ScholarPathState | dict[str, object],
    *,
    target_kind: GraphTargetKind,
) -> dict[str, object]:
    state = _graph_state(output)
    interrupted = candidate_review_payload_from_graph_output(output) is not None
    verified_by_id = {
        supervisor.supervisor_id: supervisor for supervisor in state["verified_supervisors"]
    }
    assessment_projections = tuple(
        _fit_projection(assessment, verified_by_id[assessment.supervisor_id])
        for assessment in state["research_fit_assessments"]
        if assessment.supervisor_id in verified_by_id
    )
    proposal = state["proposed_shortlist"]
    recommendations = proposal.recommendations if proposal is not None else ()
    shortlist_projections: list[ShortlistRecommendationProjection] = []
    for recommendation in recommendations:
        source_urls = tuple(
            dict.fromkeys(
                (
                    recommendation.supervisor.profile_url,
                    *(claim.source_url for claim in recommendation.supervisor.evidence),
                )
            )
        )
        shortlist_projections.append(
            ShortlistRecommendationProjection(
                rank=recommendation.rank,
                supervisor_id=recommendation.supervisor.supervisor_id,
                institution=recommendation.supervisor.institution,
                effective_score=recommendation.effective_score,
                evidence_confidence=recommendation.evidence_confidence,
                availability_status=recommendation.availability_status,
                strengths=recommendation.strengths,
                concerns=recommendation.concerns,
                source_urls=source_urls,
            )
        )
    result = GraphTargetOutput(
        target=target_kind,
        scenario_id=scenario.scenario_id,
        candidate_preferences=_preferences(scenario),
        review_status=state["review_status"],
        interrupted=interrupted,
        execution_log=tuple(state["execution_log"]),
        fallback_search_used=state["fallback_search_used"],
        search_attempts=tuple(
            SearchAttemptProjection(
                provider_used=attempt.provider_used,
                attempt_number=attempt.attempt_number,
                result_count=attempt.result_count,
                plausible_supervisor_count=attempt.plausible_supervisor_count,
                error_category=attempt.error_category,
                retryable=attempt.retryable,
                discovery_round=attempt.discovery_round,
            )
            for attempt in state["search_attempts"]
        ),
        raw_search_result_count=sum(item.result_count for item in state["search_attempts"]),
        plausible_profile_count=sum(
            item.plausible_supervisor_count for item in state["search_attempts"]
        ),
        prospective_supervisor_ids=tuple(
            supervisor.supervisor_id for supervisor in state["prospective_supervisors"]
        ),
        supervisor_provenance=tuple(
            SupervisorProvenanceProjection(
                supervisor_id=supervisor.supervisor_id,
                provenance_count=max(1, len(supervisor.discovery_provenance)),
            )
            for supervisor in state["prospective_supervisors"]
        ),
        verification_records=tuple(
            _verification_projection(record) for record in state["verification_records"]
        ),
        assessments=assessment_projections,
        independent_reviews=tuple(
            IndependentReviewProjection(
                supervisor_id=review.supervisor_id,
                review_status=review.review_status,
                effective_score=review.effective_score,
                effective_rationale=review.effective_rationale,
                effective_confidence=review.effective_confidence,
                unsupported_claim_ids=review.unsupported_claim_ids,
                overlooked_evidence_ids=review.overlooked_evidence_ids,
                critique=review.critique,
                requires_candidate_attention=review.requires_candidate_attention,
            )
            for review in state["research_fit_review_records"]
        ),
        proposed_supervisor_ids=tuple(
            recommendation.supervisor.supervisor_id for recommendation in recommendations
        ),
        shortlist_recommendations=tuple(shortlist_projections),
        shortlisted_supervisor_ids=tuple(
            supervisor.supervisor_id for supervisor in state["shortlisted_supervisors"]
        ),
        rejected_supervisor_ids=tuple(
            supervisor.supervisor_id for supervisor in state["rejected_supervisors"]
        ),
        candidate_reviews=tuple(
            CandidateReviewProjection(
                action=decision.action,
                supervisor_ids=decision.supervisor_ids,
            )
            for decision in state["candidate_feedback"]
        ),
        tool_error_codes=tuple(error.code for error in state["tool_errors"]),
    )
    return result.model_dump(mode="json")


def fake_end_to_end_target(inputs: dict[str, object]) -> dict[str, object]:
    """Run one complete fake-only LangGraph scenario through the Candidate gate."""
    scenario = _scenario_from_inputs(inputs)
    _require_target(scenario, EvaluationTargetKind.GRAPH_FAKE)
    _tag_target_run(
        scenario,
        target=EvaluationTargetKind.GRAPH_FAKE,
        prompt_versions=_GRAPH_PROMPT_VERSIONS,
        model_providers=("fake",),
        environment=Environment.TEST.value,
        completed=False,
    )
    graph_case = _config_str(scenario, "graph_case", "approval_pause")
    fixtures = build_walking_skeleton_fixtures()
    fixtures = replace(fixtures, candidate_profile=_candidate_profile(scenario))
    base_content_outcomes, evidence_outcomes = make_evaluation_evidence_outcomes(fixtures)
    content_outcomes: dict[str, ExtractedContent | Exception] = dict(base_content_outcomes)
    you_search = ScriptedSupervisorSearch(make_evaluation_search_outcomes(fixtures))
    tavily_search = ScriptedSupervisorSearch(make_evaluation_search_outcomes(fixtures))
    alternate_search = ScriptedSupervisorSearch({})
    review_outcomes: dict[str, Sequence[IndependentReviewResult | Exception]] = {}
    review_responses: tuple[CandidateRejectResponse, ...] = ()

    if graph_case == "duplicate_provenance":
        duplicate_outcomes = _duplicate_search_outcomes()
        you_search = ScriptedSupervisorSearch(duplicate_outcomes)
    elif graph_case == "you_timeout_tavily":
        first_query = make_evaluation_planning_response().search_queries[0].query
        timeout = SupervisorSearchTimeoutError("Synthetic evaluation timeout.")
        you_search = ScriptedSupervisorSearch(
            make_evaluation_search_outcomes(fixtures),
            scripts={first_query: (timeout, timeout)},
        )
    elif graph_case == "extraction_failure":
        failed_index = _config_int(scenario, "failed_supervisor_index", 1)
        failed_url = str(fixtures.raw_search_results[failed_index - 1].profile_url)
        content_outcomes[failed_url] = ContentExtractionError(
            "Synthetic extraction failure.",
            provider=ContentExtractionProvider.TAVILY,
            category=ContentExtractionErrorCategory.EXTRACTION_FAILED,
            retryable=True,
            source_url=failed_url,
        )
    elif graph_case == "reviewer_disagreement":
        reviewed_index = _config_int(scenario, "reviewed_supervisor_index", 1)
        reviewed_id = fixtures.raw_search_results[reviewed_index - 1].supervisor_id
        reviewed_score = _config_int(scenario, "reviewed_score", 60)
        review_outcomes[reviewed_id] = (
            IndependentReviewResult(
                decision=IndependentReviewDecision.REVISE,
                recommended_score=reviewed_score,
                unsupported_claim_ids=[],
                overlooked_evidence_ids=[],
                confidence=EvidenceConfidence.MEDIUM,
                critique=(
                    "The supplied evidence supports a materially lower Research Fit Score and "
                    "requires Candidate attention."
                ),
            ),
        )
    elif graph_case == "reject_theoretical":
        rejected_index = _config_int(scenario, "rejected_supervisor_index", 1)
        rejected_id = fixtures.raw_search_results[rejected_index - 1].supervisor_id
        review_responses = (
            CandidateRejectResponse(
                action="reject",
                rejections=(
                    CandidateRejectionReason(
                        supervisor_id=rejected_id,
                        reason=(
                            "The Supervisor's research orientation is too theoretical for the "
                            "Candidate's applied direction."
                        ),
                    ),
                ),
            ),
        )
    elif graph_case != "approval_pause":
        raise ValueError(f"Unknown fake graph evaluation case: {graph_case}")

    graph_config = GraphFixtureConfig(
        fixtures=fixtures,
        independent_review_policy=IndependentReviewPolicy(disagreement_threshold=5),
    )
    output = run_scholarpath_graph(
        graph_config,
        thread_id=f"m12-{scenario.scenario_id}",
        candidate_review_responses=review_responses,
        checkpointer=create_test_checkpointer(),
        planning_model=StaticPlanningModel(),
        supervisor_search=you_search,
        tavily_search=tavily_search,
        content_extractor=ScriptedContentExtraction(content_outcomes),
        evidence_model=ScriptedEvidenceModel(evidence_outcomes),
        research_fit_model=ScriptedResearchFitModel(),
        independent_review_model=ScriptedIndependentReviewModel(review_outcomes),
        candidate_preference_memory=InMemoryCandidatePreferenceMemory(),
        alternate_evidence_search=alternate_search,
        application_settings=ApplicationSettings(
            environment=Environment.TEST,
            discovery_failure_mode=DiscoveryFailureMode.OFF,
        ),
        langsmith_settings=LangSmithSettings(tracing=False),
        utc_clock=FixedEvaluationClock(),
    )
    state = _graph_state(output)
    _tag_target_run(
        scenario,
        target=EvaluationTargetKind.GRAPH_FAKE,
        prompt_versions=_GRAPH_PROMPT_VERSIONS,
        model_providers=("fake",),
        environment=Environment.TEST.value,
        fallback_search_used=state["fallback_search_used"],
        candidate_review_outcome=_candidate_review_outcome(output),
    )
    return _project_graph_output(
        scenario,
        output,
        target_kind=EvaluationTargetKind.GRAPH_FAKE,
    )


def live_end_to_end_target(inputs: dict[str, object]) -> dict[str, object]:
    """Run the production adapters only after the separate live-evaluation opt-in."""
    scenario = _scenario_from_inputs(inputs)
    if scenario.target not in {
        EvaluationTargetKind.GRAPH_FAKE,
        EvaluationTargetKind.GRAPH_LIVE,
    }:
        raise ValueError("Live end-to-end evaluation requires a graph scenario")
    application_settings = load_settings()
    _tag_target_run(
        scenario,
        target=EvaluationTargetKind.GRAPH_LIVE,
        prompt_versions=_GRAPH_PROMPT_VERSIONS,
        model_providers=("openai", "nebius"),
        environment=application_settings.environment.value,
        completed=False,
    )
    settings = EvaluationSettings()
    if not settings.run_live_e2e_evals:
        raise RuntimeError(
            "Live end-to-end evaluation is disabled. Set "
            "SCHOLARPATH_RUN_LIVE_E2E_EVALS=true to opt in."
        )
    fixtures = replace(
        build_walking_skeleton_fixtures(),
        candidate_profile=_candidate_profile(scenario),
    )
    output = run_scholarpath_graph(
        GraphFixtureConfig(fixtures=fixtures),
        thread_id=f"m12-live-{scenario.scenario_id}",
        candidate_review_responses=(),
        application_settings=application_settings,
    )
    state = _graph_state(output)
    _tag_target_run(
        scenario,
        target=EvaluationTargetKind.GRAPH_LIVE,
        prompt_versions=_GRAPH_PROMPT_VERSIONS,
        model_providers=("openai", "nebius"),
        environment=application_settings.environment.value,
        fallback_search_used=state["fallback_search_used"],
        candidate_review_outcome=_candidate_review_outcome(output),
    )
    return _project_graph_output(
        scenario,
        output,
        target_kind=EvaluationTargetKind.GRAPH_LIVE,
    )


__all__ = [
    "EvaluationTarget",
    "evidence_verification_target",
    "fake_end_to_end_target",
    "live_end_to_end_target",
    "make_evidence_verification_target",
    "make_research_fit_target",
    "make_search_planning_target",
    "research_fit_target",
    "search_planning_target",
]
