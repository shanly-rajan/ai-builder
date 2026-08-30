"""Pure form, progress, and graph-to-view transformations for Streamlit."""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from langgraph.types import StateSnapshot
from pydantic import HttpUrl, ValidationError

from ..domain import (
    CandidatePreferenceRevision,
    EvidenceClaimType,
    EvidenceConfidence,
    ProposedSupervisorRecommendation,
    ReconciledResearchFitAssessment,
    ResearchFitAssessment,
    SearchResultRejectionCounts,
    SupervisorLifecycleStatus,
    VerificationEvidenceStandard,
    VerificationStatus,
    VerifiedSupervisor,
    evidence_claim_is_grounded_for_supervisor,
    missing_verification_evidence,
)
from ..graph import (
    CANONICAL_NODE_NAMES,
    AlternateSourceRejectionCounts,
    AlternateSourceSelectionOutcome,
    CandidateRequestMoreResponse,
    CandidateReviewInterruptPayload,
    ReviewStatus,
    ScholarPathState,
    ToolErrorRecord,
)
from ..tools import ContentExtractionErrorCategory, SearchProvider
from .models import (
    AlternateSourceDiagnosticsView,
    CandidateResearchProfileSubmission,
    DiscoveryAttemptView,
    DiscoveryDiagnosticsView,
    EvidenceClaimTypeCountsView,
    EvidenceExtractionFailureCountsView,
    EvidenceSourceView,
    EvidenceVerificationDiagnosticsView,
    GraphProgressEvent,
    MissingRequiredEvidenceCountsView,
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
    fit_evidence_ids: tuple[str, ...] | None = None
    if recommendation is not None:
        score = recommendation.effective_score
        explanation = recommendation.effective_rationale
        evidence_confidence = recommendation.evidence_confidence
        concerns = recommendation.concerns
        fit_evidence_ids = (
            recommendation.independent_review.effective_supporting_evidence_ids
            if recommendation.independent_review is not None
            else recommendation.assessment.supporting_evidence_ids
        )
    elif review is not None:
        score = review.effective_score
        explanation = review.effective_rationale
        evidence_confidence = review.effective_confidence
        concerns = assessment.concerns if assessment is not None else ()
        fit_evidence_ids = review.effective_supporting_evidence_ids
    elif assessment is not None:
        score = assessment.overall_score
        explanation = assessment.rationale
        evidence_confidence = assessment.confidence
        concerns = assessment.concerns
        fit_evidence_ids = assessment.supporting_evidence_ids
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
        verification_evidence_standard=supervisor.verification_evidence_standard,
        research_fit_score=score,
        research_fit_evidence_limited=(fit_evidence_ids is not None and not fit_evidence_ids),
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


def _alternate_source_diagnostics(
    state: ScholarPathState,
) -> AlternateSourceDiagnosticsView | None:
    """Aggregate current-round selector outcomes without exposing source or Candidate data."""
    current_attempts = tuple(
        attempt
        for attempt in state.get("alternate_source_attempts", [])
        if attempt.discovery_round == state["discovery_round"]
    )
    if not current_attempts:
        return None
    rejection_counts = AlternateSourceRejectionCounts()
    for attempt in current_attempts:
        rejection_counts = rejection_counts.combine(attempt.rejection_counts)
    return AlternateSourceDiagnosticsView(
        attempted_supervisor_count=len(current_attempts),
        result_count=sum(attempt.result_count for attempt in current_attempts),
        eligible_result_count=sum(attempt.eligible_result_count for attempt in current_attempts),
        selected_source_count=sum(
            attempt.outcome is AlternateSourceSelectionOutcome.SELECTED
            for attempt in current_attempts
        ),
        no_results_count=sum(
            attempt.outcome is AlternateSourceSelectionOutcome.NO_RESULTS
            for attempt in current_attempts
        ),
        rejected_all_count=sum(
            attempt.outcome is AlternateSourceSelectionOutcome.REJECTED_ALL
            for attempt in current_attempts
        ),
        provider_error_count=sum(
            attempt.outcome is AlternateSourceSelectionOutcome.PROVIDER_ERROR
            for attempt in current_attempts
        ),
        not_configured_count=sum(
            attempt.outcome is AlternateSourceSelectionOutcome.NOT_CONFIGURED
            for attempt in current_attempts
        ),
        rejection_counts=rejection_counts,
    )


def _evidence_verification_diagnostics(
    state: ScholarPathState,
) -> EvidenceVerificationDiagnosticsView | None:
    """Aggregate current-round verification facts without identities or source content."""
    current_attempts = tuple(
        attempt
        for attempt in state.get("evidence_extraction_attempts", [])
        if attempt.discovery_round == state["discovery_round"]
    )
    records = tuple(state.get("verification_records", []))
    if not current_attempts and not records:
        return None
    standards = {record.verification_evidence_standard for record in records}
    if len(standards) > 1:
        raise ValueError("A graph run cannot mix verification evidence standards")
    standard = next(iter(standards), VerificationEvidenceStandard.STRICT)

    primary_attempts = tuple(
        attempt for attempt in current_attempts if not attempt.alternate_source
    )
    alternate_attempts = tuple(attempt for attempt in current_attempts if attempt.alternate_source)
    failure_values = {
        category.value: sum(attempt.error_category is category for attempt in current_attempts)
        for category in ContentExtractionErrorCategory
    }
    retained_values = {
        claim_type.value: sum(
            claim.claim_type is claim_type for record in records for claim in record.evidence
        )
        for claim_type in EvidenceClaimType
    }
    grounded_values = {
        claim_type.value: sum(
            claim.claim_type is claim_type
            and evidence_claim_is_grounded_for_supervisor(
                claim,
                record.prospective_supervisor,
                record.evidence,
            )
            for record in records
            for claim in record.evidence
        )
        for claim_type in EvidenceClaimType
    }
    missing_values = {
        missing_category: sum(
            missing_category in record.missing_required_evidence for record in records
        )
        for missing_category in (
            EvidenceClaimType.IDENTITY.value,
            EvidenceClaimType.CURRENT_AFFILIATION.value,
            "research_interest_or_publication",
        )
    }
    deferred_values = {
        EvidenceClaimType.IDENTITY.value: 0,
        EvidenceClaimType.CURRENT_AFFILIATION.value: sum(
            EvidenceClaimType.CURRENT_AFFILIATION.value
            in missing_verification_evidence(
                record.evidence,
                record.prospective_supervisor,
                VerificationEvidenceStandard.STRICT,
            )
            and EvidenceClaimType.CURRENT_AFFILIATION.value not in record.missing_required_evidence
            for record in records
        ),
        "research_interest_or_publication": sum(
            "research_interest_or_publication"
            in missing_verification_evidence(
                record.evidence,
                record.prospective_supervisor,
                VerificationEvidenceStandard.STRICT,
            )
            and "research_interest_or_publication" not in record.missing_required_evidence
            for record in records
        ),
    }
    return EvidenceVerificationDiagnosticsView(
        primary_retrieval_attempt_count=len(primary_attempts),
        primary_retrieval_success_count=sum(attempt.successful for attempt in primary_attempts),
        primary_retrieval_failure_count=sum(not attempt.successful for attempt in primary_attempts),
        alternate_retrieval_attempt_count=len(alternate_attempts),
        alternate_retrieval_success_count=sum(attempt.successful for attempt in alternate_attempts),
        alternate_retrieval_failure_count=sum(
            not attempt.successful for attempt in alternate_attempts
        ),
        extraction_failure_counts=EvidenceExtractionFailureCountsView.model_validate(
            failure_values
        ),
        verification_evidence_standard=standard,
        verification_record_count=len(records),
        completed_verification_record_count=sum(
            record.verification_status
            in {
                VerificationStatus.VERIFIED,
                VerificationStatus.VERIFIED_WITH_CONCERNS,
            }
            for record in records
        ),
        partial_verification_record_count=sum(
            record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
            for record in records
        ),
        retained_claim_counts=EvidenceClaimTypeCountsView.model_validate(retained_values),
        directly_grounded_claim_counts=EvidenceClaimTypeCountsView.model_validate(grounded_values),
        missing_required_evidence_counts=MissingRequiredEvidenceCountsView.model_validate(
            missing_values
        ),
        deferred_evidence_gap_counts=MissingRequiredEvidenceCountsView.model_validate(
            deferred_values
        ),
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
    errors = _group_ui_errors(state["tool_errors"])

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
        alternate_source_diagnostics=_alternate_source_diagnostics(state),
        evidence_verification_diagnostics=_evidence_verification_diagnostics(state),
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


def _group_ui_errors(errors: Iterable[ToolErrorRecord]) -> tuple[RecoverableUiError, ...]:
    """Group exact Candidate-facing duplicates while preserving graph audit records."""
    grouped: list[RecoverableUiError] = []
    positions: dict[tuple[str, str, bool], int] = {}
    for error in errors:
        key = (error.code, error.message, error.recoverable)
        position = positions.get(key)
        if position is None:
            positions[key] = len(grouped)
            grouped.append(
                RecoverableUiError(
                    code=error.code,
                    message=error.message,
                    recoverable=error.recoverable,
                )
            )
            continue
        current = grouped[position]
        grouped[position] = current.model_copy(
            update={"occurrence_count": current.occurrence_count + 1}
        )
    return tuple(grouped)
