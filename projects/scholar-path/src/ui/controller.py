"""Pure form, progress, and graph-to-view transformations for Streamlit."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from langgraph.types import StateSnapshot
from pydantic import HttpUrl, ValidationError

from ..domain import (
    CandidatePreferenceRevision,
    EvidenceConfidence,
    ProposedSupervisorRecommendation,
    ReconciledResearchFitAssessment,
    ResearchFitAssessment,
    SearchResultRejectionCounts,
    SupervisorLifecycleStatus,
    VerifiedSupervisor,
)
from ..graph import (
    CANONICAL_NODE_NAMES,
    CandidateRequestMoreResponse,
    CandidateReviewInterruptPayload,
    ReviewStatus,
    ScholarPathState,
)
from ..tools import SearchProvider
from .models import (
    CandidateResearchProfileSubmission,
    DiscoveryAttemptView,
    DiscoveryDiagnosticsView,
    EvidenceSourceView,
    GraphProgressEvent,
    ProspectiveSupervisorView,
    RecoverableUiError,
    UiDiscoveryRoute,
    UiRunSnapshot,
    UiStage,
    VerifiedSupervisorView,
)

_MULTI_VALUE_SEPARATOR = re.compile(r"[,;\n]+")
_CANONICAL_NODE_NAME_SET = frozenset(CANONICAL_NODE_NAMES)
_CONFIDENCE_RANK = {
    EvidenceConfidence.LOW: 1,
    EvidenceConfidence.MEDIUM: 2,
    EvidenceConfidence.HIGH: 3,
}


def normalize_multi_value_input(value: str | Iterable[str]) -> tuple[str, ...]:
    """Parse and case-insensitively deduplicate Candidate-entered list values."""
    raw_values = _MULTI_VALUE_SEPARATOR.split(value) if isinstance(value, str) else value
    unique: dict[str, str] = {}
    for raw_value in raw_values:
        normalized_value = " ".join(raw_value.strip().split())
        if normalized_value:
            unique.setdefault(normalized_value.casefold(), normalized_value)
    return tuple(unique.values())


def build_candidate_submission(
    *,
    proposed_research_statement: str,
    research_topics: str,
    preferred_regions: str,
    study_modes: Iterable[str],
    research_orientation: str | None,
    methodological_interests: str,
    exclusions: str,
) -> CandidateResearchProfileSubmission:
    """Validate one complete form submission before a graph thread is created."""
    normalized_orientation = (research_orientation or "").strip()
    if normalized_orientation.casefold() in {"", "no preference"}:
        normalized_orientation = ""
    return CandidateResearchProfileSubmission(
        proposed_research_statement=proposed_research_statement,
        research_topics=normalize_multi_value_input(research_topics),
        preferred_regions=normalize_multi_value_input(preferred_regions),
        study_modes=normalize_multi_value_input(study_modes),
        research_orientation=normalized_orientation or None,
        methodological_interests=normalize_multi_value_input(methodological_interests),
        exclusions=normalize_multi_value_input(exclusions),
    )


def build_request_more_response(
    *,
    research_topics: str,
    preferred_regions: str,
    study_modes: Iterable[str],
    research_orientation: str | None,
    methodological_interests: str,
    constraints: str,
    exclusions: str,
) -> CandidateRequestMoreResponse:
    """Build a typed revision containing only fields the Candidate changed."""
    normalized_orientation = (research_orientation or "").strip()
    if normalized_orientation.casefold() in {"", "no change"}:
        normalized_orientation = ""
    values: dict[str, object] = {}
    field_values: tuple[tuple[str, tuple[str, ...]], ...] = (
        ("research_topics", normalize_multi_value_input(research_topics)),
        ("preferred_regions", normalize_multi_value_input(preferred_regions)),
        ("preferred_study_modes", normalize_multi_value_input(study_modes)),
        ("methodological_interests", normalize_multi_value_input(methodological_interests)),
        ("constraints", normalize_multi_value_input(constraints)),
        ("exclusions", normalize_multi_value_input(exclusions)),
    )
    for field_name, field_value in field_values:
        if field_value:
            values[field_name] = field_value
    if normalized_orientation:
        values["preferred_research_orientation"] = normalized_orientation
    revision = CandidatePreferenceRevision.model_validate(values)
    return CandidateRequestMoreResponse(action="request_more", revised_preferences=revision)


def canonical_node_names_from_stream_part(part: object) -> tuple[str, ...]:
    """Discard raw state updates and retain only allowlisted v2 progress node names."""
    if not isinstance(part, Mapping) or part.get("type") != "updates":
        return ()
    data = part.get("data")
    if not isinstance(data, Mapping):
        return ()
    return tuple(
        node_name
        for node_name in data
        if isinstance(node_name, str) and node_name in _CANONICAL_NODE_NAME_SET
    )


def progress_events_from_execution_log(
    execution_log: Iterable[str],
) -> tuple[GraphProgressEvent, ...]:
    """Rebuild safe progress history from canonical graph execution records."""
    return tuple(
        GraphProgressEvent(sequence=sequence, node_name=node_name)
        for sequence, node_name in enumerate(
            (item for item in execution_log if item in _CANONICAL_NODE_NAME_SET),
            start=1,
        )
    )


def candidate_review_payload_from_snapshot(
    snapshot: StateSnapshot,
) -> CandidateReviewInterruptPayload | None:
    """Restore the current typed Candidate review payload without advancing the graph."""
    for task in snapshot.tasks:
        for interrupt_record in task.interrupts:
            try:
                return CandidateReviewInterruptPayload.model_validate(interrupt_record.value)
            except ValidationError:
                continue
    return None


def checkpoint_token_from_snapshot(snapshot: StateSnapshot) -> str:
    """Return the opaque checkpoint identifier used to reject stale review actions."""
    configurable = snapshot.config.get("configurable", {})
    checkpoint_id = configurable.get("checkpoint_id")
    if not isinstance(checkpoint_id, str) or not checkpoint_id.strip():
        raise ValueError("ScholarPath checkpoint does not expose a valid checkpoint identifier")
    return checkpoint_id


def _ordered_unique(values: Iterable[str]) -> tuple[str, ...]:
    unique: dict[str, str] = {}
    for value in values:
        unique.setdefault(" ".join(value.casefold().split()), value)
    return tuple(unique.values())


def _source_links(supervisor: VerifiedSupervisor) -> tuple[HttpUrl, ...]:
    links: list[HttpUrl] = [supervisor.profile_url]
    seen = {str(supervisor.profile_url)}
    for evidence in supervisor.evidence:
        if str(evidence.source_url) not in seen:
            links.append(evidence.source_url)
            seen.add(str(evidence.source_url))
    return tuple(links)


def _verified_supervisor_view(
    supervisor: VerifiedSupervisor,
    assessment: ResearchFitAssessment | None,
    review: ReconciledResearchFitAssessment | None,
    recommendation: ProposedSupervisorRecommendation | None = None,
) -> VerifiedSupervisorView:
    if recommendation is not None:
        score = recommendation.effective_score
        explanation = recommendation.effective_rationale
        evidence_confidence = recommendation.evidence_confidence
        concerns = recommendation.concerns
    elif review is not None:
        score = review.effective_score
        explanation = review.effective_rationale
        evidence_confidence = review.effective_confidence
        concerns = assessment.concerns if assessment is not None else ()
    elif assessment is not None:
        score = assessment.overall_score
        explanation = assessment.rationale
        evidence_confidence = assessment.confidence
        concerns = assessment.concerns
    else:
        score = None
        explanation = None
        evidence_confidence = min(
            (claim.confidence for claim in supervisor.evidence),
            key=_CONFIDENCE_RANK.__getitem__,
        )
        concerns = ()

    review_status = review.review_status.value if review is not None else "not_reviewed"
    requires_attention = review.requires_candidate_attention if review is not None else False
    evidence_sources = tuple(
        EvidenceSourceView(
            evidence_id=claim.evidence_id,
            claim=claim.claim,
            source_url=claim.source_url,
            source_kind=claim.source_kind,
            confidence=claim.confidence,
            directly_supported=claim.directly_supported,
        )
        for claim in supervisor.evidence
    )
    return VerifiedSupervisorView(
        supervisor_id=supervisor.supervisor_id,
        full_name=supervisor.full_name,
        institution=supervisor.institution,
        department=supervisor.department,
        profile_url=supervisor.profile_url,
        verification_status=supervisor.verification_status,
        research_fit_score=score,
        fit_explanation=explanation,
        evidence_confidence=evidence_confidence,
        evidence_sources=evidence_sources,
        source_links=_source_links(supervisor),
        availability_status=supervisor.availability_status,
        concerns=_ordered_unique((*supervisor.verification_concerns, *concerns)),
        independent_review_status=review_status,
        requires_candidate_attention=requires_attention,
    )


def _discovery_route(state: ScholarPathState) -> UiDiscoveryRoute:
    """Derive one privacy-safe current-round route from persisted workflow facts."""
    if state["review_status"] is ReviewStatus.DISCOVERY_INCOMPLETE:
        return UiDiscoveryRoute.STOPPED_RECOVERABLY
    if any(error.code == "supervisor_discovery_stopped" for error in state["tool_errors"]):
        return UiDiscoveryRoute.STOPPED
    downstream_nodes = {
        "deduplicate_supervisors",
        "extract_supervisor_evidence",
        "supervisor_evidence_sufficient",
        "retry_alternate_evidence_source",
        "evaluate_research_fit",
        "review_fit_assessments",
        "synthesize_supervisor_shortlist",
        "candidate_review_gate",
    }
    if downstream_nodes.intersection(state["execution_log"]):
        return UiDiscoveryRoute.DOWNSTREAM
    if state["fallback_search_round"] == state["discovery_round"]:
        return UiDiscoveryRoute.FALLBACK
    return UiDiscoveryRoute.PRIMARY


def _discovery_diagnostics(state: ScholarPathState) -> DiscoveryDiagnosticsView | None:
    """Project current-round attempt counts while dropping queries and result content."""
    current_attempts = tuple(
        attempt
        for attempt in state["search_attempts"]
        if attempt.discovery_round == state["discovery_round"]
    )
    if not current_attempts:
        return None
    attempts = tuple(
        DiscoveryAttemptView(
            provider=attempt.provider_used,
            attempt_number=attempt.attempt_number,
            raw_result_count=attempt.result_count,
            plausible_supervisor_count=attempt.plausible_supervisor_count,
            rejection_counts=attempt.rejection_counts,
            error_category=attempt.error_category,
            route=(
                UiDiscoveryRoute.FALLBACK
                if attempt.provider_used is SearchProvider.TAVILY
                else UiDiscoveryRoute.PRIMARY
            ),
        )
        for attempt in current_attempts
    )
    successful_attempts = tuple(attempt for attempt in attempts if attempt.error_category is None)
    rejection_counts: SearchResultRejectionCounts | None = None
    if successful_attempts and all(
        attempt.rejection_counts is not None for attempt in successful_attempts
    ):
        rejection_counts = SearchResultRejectionCounts()
        for attempt in successful_attempts:
            if attempt.rejection_counts is not None:
                rejection_counts = rejection_counts.combine(attempt.rejection_counts)
    return DiscoveryDiagnosticsView(
        attempts=attempts,
        raw_result_count=sum(item.raw_result_count for item in attempts),
        plausible_supervisor_count=sum(item.plausible_supervisor_count for item in attempts),
        retained_prospective_supervisor_count=len(state["prospective_supervisors"]),
        rejection_counts=rejection_counts,
        fallback_search_used=any(item.route is UiDiscoveryRoute.FALLBACK for item in attempts),
        route=_discovery_route(state),
    )


def project_graph_state_to_ui(
    state: ScholarPathState,
    *,
    checkpoint_token: str,
    review_payload: CandidateReviewInterruptPayload | None,
) -> UiRunSnapshot:
    """Project persisted graph state into the finite Candidate-facing view contract."""
    assessments = {item.supervisor_id: item for item in state["research_fit_assessments"]}
    reviews = {item.supervisor_id: item for item in state["research_fit_review_records"]}
    recommendations = (
        {
            item.supervisor.supervisor_id: item
            for item in state["proposed_shortlist"].recommendations
        }
        if state["proposed_shortlist"] is not None
        else {}
    )

    prospective_views = tuple(
        ProspectiveSupervisorView(
            supervisor_id=supervisor.supervisor_id,
            full_name=supervisor.full_name,
            institution=supervisor.institution,
            department=supervisor.department,
            profile_url=supervisor.profile_url,
            status=SupervisorLifecycleStatus.PROSPECTIVE,
        )
        for supervisor in state["prospective_supervisors"]
    )
    verified_views = tuple(
        _verified_supervisor_view(
            supervisor,
            assessments.get(supervisor.supervisor_id),
            reviews.get(supervisor.supervisor_id),
        )
        for supervisor in state["verified_supervisors"]
    )
    review_views = tuple(
        _verified_supervisor_view(
            recommendation.supervisor,
            recommendation.assessment,
            recommendation.independent_review,
            recommendation,
        )
        for recommendation in (
            state["proposed_shortlist"].recommendations
            if state["proposed_shortlist"] is not None
            else ()
        )
    )
    shortlist_views = tuple(
        _verified_supervisor_view(
            supervisor,
            assessments.get(supervisor.supervisor_id),
            reviews.get(supervisor.supervisor_id),
            recommendations.get(supervisor.supervisor_id),
        )
        for supervisor in state["shortlisted_supervisors"]
    )
    errors = tuple(
        RecoverableUiError(
            code=error.code,
            message=error.message,
            recoverable=error.recoverable,
        )
        for error in state["tool_errors"]
    )

    if state["supervisor_shortlist"] is not None:
        stage = UiStage.SUPERVISOR_SHORTLIST
    elif review_payload is not None and state["review_status"] is ReviewStatus.PROPOSED:
        stage = UiStage.REVIEW_SUPERVISORS
    elif state["review_status"] in {
        ReviewStatus.RETRY_EXHAUSTED,
        ReviewStatus.DISCOVERY_INCOMPLETE,
        ReviewStatus.EVIDENCE_INCOMPLETE,
    }:
        stage = UiStage.STOPPED
    elif verified_views:
        stage = UiStage.VERIFIED_SUPERVISORS
    elif prospective_views:
        stage = UiStage.PROSPECTIVE_SUPERVISORS
    else:
        stage = UiStage.SEARCH_PROGRESS

    return UiRunSnapshot(
        stage=stage,
        checkpoint_token=checkpoint_token,
        progress_events=progress_events_from_execution_log(state["execution_log"]),
        discovery_diagnostics=_discovery_diagnostics(state),
        prospective_supervisors=prospective_views,
        verified_supervisors=verified_views,
        review_supervisors=review_views if review_payload is not None else (),
        shortlisted_supervisors=shortlist_views,
        review_iteration=(review_payload.review_iteration if review_payload is not None else None),
        maximum_review_iterations=(
            review_payload.maximum_review_iterations if review_payload is not None else None
        ),
        shortlist_briefing=state["shortlist_briefing"],
        errors=errors,
    )
