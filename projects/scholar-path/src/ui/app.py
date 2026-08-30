"""Thin Streamlit renderer for the typed ScholarPath application service."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import streamlit as st
from pydantic import ValidationError

from ..config import ApplicationSettings
from ..domain import VerificationEvidenceStandard
from ..graph import (
    MAX_PROPOSED_SHORTLIST_SIZE,
    CandidateApproveResponse,
    CandidateRejectionReason,
    CandidateRejectResponse,
    CandidateReviewResponse,
    default_minimum_verified_supervisors,
)
from . import dependencies
from .controller import build_candidate_submission, build_request_more_response
from .models import (
    AlternateSourceDiagnosticsView,
    DiscoveryDiagnosticsView,
    EvidenceVerificationDiagnosticsView,
    GraphProgressEvent,
    UiRunSnapshot,
    UiStage,
    VerifiedSupervisorView,
)
from .service import ScholarPathApplicationPort
from .theme import inject_theme_styles, render_appearance_controls

STAGE_LABELS = (
    "1. Your Research Degree Profile",
    "2. Supervisor Search Progress",
    "3. Prospective Supervisors",
    "4. Verified Supervisors",
    "5. Review Supervisors",
    "6. Your Supervisor Shortlist",
)
RECOVERABLE_SERVICE_MESSAGE = (
    "ScholarPath could not complete this step. Check the configured providers and try again."
)
STUDY_MODE_OPTIONS = ("full-time", "part-time", "online", "hybrid", "on-campus")
RESEARCH_ORIENTATION_OPTIONS = ("No preference", "applied", "theoretical", "mixed")
DEMO_PROFILE_TOGGLE_KEY = "use_demo_research_profile"
DEMO_PROFILE_RESEARCH_STATEMENT = (
    "Applications of machine learning and artificial intelligence in software engineering."
)
DEMO_PROFILE_RESEARCH_TOPICS = (
    "Machine Learning, Artificial Intelligence, Software Engineering, Data Science, "
    "Computer Science"
)
DEMO_PROFILE_METHODOLOGICAL_INTERESTS = (
    "Empirical studies, quantitative analysis, benchmark evaluation"
)
PAGE_ICON = "🎓"
HERO_TITLE = "🎓 ScholarPath"
HERO_SUBTITLE = "Evidence-backed supervisor discovery for postgraduate research."
APP_STYLES = """
<style>
[data-testid="stAppViewContainer"] {
    background-image: radial-gradient(
        circle at 92% 2%,
        rgba(70, 130, 255, 0.10),
        transparent 28rem
    );
}
.st-key-scholarpath_hero {
    background: linear-gradient(
        135deg,
        rgba(45, 110, 240, 0.18),
        rgba(34, 197, 160, 0.08)
    );
    border: 1px solid rgba(91, 153, 255, 0.32);
    border-radius: 1.15rem;
    box-shadow: 0 0.75rem 2.25rem rgba(8, 15, 31, 0.12);
    margin-bottom: 0.75rem;
    padding: 1.15rem 1.35rem 0.9rem;
}
.st-key-scholarpath_hero h1 {
    letter-spacing: -0.035em;
    margin-bottom: 0.15rem;
}
.st-key-scholarpath_hero p {
    font-size: 1.05rem;
    margin-bottom: 0.25rem;
    opacity: 0.84;
}
[data-testid="stExpander"],
[data-testid="stForm"] {
    border-color: rgba(91, 153, 255, 0.24);
    border-radius: 0.85rem;
}
[data-testid="stMetric"] {
    background: rgba(91, 153, 255, 0.07);
    border-radius: 0.7rem;
    padding: 0.55rem 0.7rem;
}
</style>
"""
DETERMINISTIC_DEMO_BANNER = (
    "Synthetic offline demonstration mode is active. Displayed results and workflow outcomes "
    "are invented test data, not real Supervisor information or recommendations. External "
    "providers are not called."
)
MVP_IDENTITY_ONLY_BANNER = (
    "MVP identity-only verification is active. Directly grounded identity is required; "
    "current affiliation and research evidence are deferred and shown as limitations. "
    f"Evidence verification begins with at least "
    f"{default_minimum_verified_supervisors(VerificationEvidenceStandard.IDENTITY_ONLY_MVP)} "
    f"Prospective Supervisors, and the workflow continues with at least "
    f"{default_minimum_verified_supervisors(VerificationEvidenceStandard.IDENTITY_ONLY_MVP)} "
    "Verified "
    f"Supervisors and may propose up to {MAX_PROPOSED_SHORTLIST_SIZE}."
)


@st.cache_resource(show_spinner=False)
def application_settings() -> ApplicationSettings:
    """Resolve one immutable composition snapshot for the Streamlit process."""
    return dependencies.configured_application_settings()


@st.cache_resource(show_spinner=False)
def application_service() -> ScholarPathApplicationPort:
    """Cache only shared infrastructure; Candidate data remains checkpoint-scoped."""
    return dependencies.create_application_service(application_settings())


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def _render_stage_navigation() -> None:
    st.caption("  →  ".join(STAGE_LABELS))


def _render_hero() -> None:
    """Render a static, styled research-degree introduction without dynamic HTML."""
    st.markdown(APP_STYLES, unsafe_allow_html=True)
    with st.container(key="scholarpath_hero"):
        st.title(HERO_TITLE)
        st.write(HERO_SUBTITLE)


def _render_runtime_profile_banner() -> None:
    """Keep non-strict runtime modes visibly distinct from the strict live path."""
    if dependencies.is_deterministic_demo(application_settings()):
        st.warning(DETERMINISTIC_DEMO_BANNER)
    if (
        application_settings().verification_evidence_standard
        is VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    ):
        st.warning(MVP_IDENTITY_ONLY_BANNER)


def demo_profile_widget_values() -> dict[str, str | list[str]]:
    """Return a fresh, deterministic set of editable Candidate form values."""
    return {
        "profile_research_statement": DEMO_PROFILE_RESEARCH_STATEMENT,
        "profile_research_topics": DEMO_PROFILE_RESEARCH_TOPICS,
        "profile_preferred_regions": "",
        "profile_study_modes": [],
        "profile_research_orientation": "No preference",
        "profile_methodological_interests": DEMO_PROFILE_METHODOLOGICAL_INTERESTS,
        "profile_exclusions": "",
    }


def empty_profile_widget_values() -> dict[str, str | list[str]]:
    """Return the form defaults used when unchanged demonstration values are disabled."""
    return {
        "profile_research_statement": "",
        "profile_research_topics": "",
        "profile_preferred_regions": "",
        "profile_study_modes": [],
        "profile_research_orientation": "No preference",
        "profile_methodological_interests": "",
        "profile_exclusions": "",
    }


def _synchronize_demo_profile_toggle() -> None:
    """Populate on opt-in and clear only sample values the reviewer did not edit."""
    demo_values = demo_profile_widget_values()
    if bool(st.session_state.get(DEMO_PROFILE_TOGGLE_KEY, False)):
        st.session_state.update(demo_values)
        return

    empty_values = empty_profile_widget_values()
    for key, demo_value in demo_values.items():
        if st.session_state.get(key) == demo_value:
            st.session_state[key] = empty_values[key]


def _render_profile_form() -> None:
    st.header(STAGE_LABELS[0])
    st.write(
        "Describe your postgraduate research direction and practical preferences that "
        "should guide Supervisor discovery."
    )
    st.toggle(
        "Use demo research profile",
        key=DEMO_PROFILE_TOGGLE_KEY,
        help="Populate an editable example profile without starting a Supervisor search.",
        on_change=_synchronize_demo_profile_toggle,
    )
    st.caption(
        "Demo values remain editable. Turning the control off clears unchanged sample values; "
        "search starts only when you use the form button."
    )
    with st.form("candidate_profile_form", border=True):
        research_statement = st.text_area(
            "Proposed research statement *",
            key="profile_research_statement",
            height=160,
        )
        research_topics = st.text_area(
            "Research topics *",
            key="profile_research_topics",
            help="Separate topics with commas or new lines.",
        )
        preferred_regions = st.text_input(
            "Preferred regions",
            key="profile_preferred_regions",
            help="Separate regions with commas.",
        )
        study_modes = st.multiselect(
            "Study mode",
            STUDY_MODE_OPTIONS,
            key="profile_study_modes",
        )
        research_orientation = st.selectbox(
            "Research orientation",
            RESEARCH_ORIENTATION_OPTIONS,
            key="profile_research_orientation",
        )
        methodological_interests = st.text_input(
            "Methodological interests",
            key="profile_methodological_interests",
            help="Separate methods with commas.",
        )
        exclusions = st.text_input(
            "Exclusions",
            key="profile_exclusions",
            help="Research areas or programme constraints to exclude.",
        )
        submitted = st.form_submit_button(
            "Start Supervisor Research",
            key="candidate_profile_submit",
            type="primary",
            width="stretch",
        )

    if not submitted:
        return
    try:
        submission = build_candidate_submission(
            proposed_research_statement=research_statement,
            research_topics=research_topics,
            preferred_regions=preferred_regions,
            study_modes=study_modes,
            research_orientation=research_orientation,
            methodological_interests=methodological_interests,
            exclusions=exclusions,
        )
        profile = submission.to_candidate_profile(dependencies.new_candidate_id())
    except (ValidationError, ValueError):
        st.error("Enter a proposed research statement and at least one research topic.")
        return

    thread_id = dependencies.new_thread_id()
    try:
        service = application_service()
        with st.status(
            "Starting Supervisor research",
            expanded=True,
            state="running",
        ) as status:
            service.start(
                profile,
                thread_id,
                progress_sink=lambda event: _write_progress_event(status.write, event),
            )
            status.update(label="Supervisor research checkpoint saved", state="complete")
    except Exception:
        st.error(RECOVERABLE_SERVICE_MESSAGE)
        return
    st.session_state["thread_id"] = thread_id
    st.rerun()


def _write_progress_event(
    writer: Callable[[str], object],
    event: GraphProgressEvent,
) -> None:
    writer(f"{event.sequence}. {event.node_name}")


def _render_progress(snapshot: UiRunSnapshot) -> None:
    st.header(STAGE_LABELS[1])
    is_complete = snapshot.stage in {
        UiStage.REVIEW_SUPERVISORS,
        UiStage.SUPERVISOR_SHORTLIST,
        UiStage.STOPPED,
    }
    with st.status(
        "Canonical LangGraph progress",
        expanded=not is_complete,
        state="complete" if is_complete else "running",
    ):
        if not snapshot.progress_events:
            st.write("Waiting for the first canonical workflow update.")
        for event in snapshot.progress_events:
            st.write(f"{event.sequence}. {event.node_name}")
    if snapshot.discovery_diagnostics is not None:
        _render_discovery_diagnostics(snapshot.discovery_diagnostics)


def _render_discovery_diagnostics(diagnostics: DiscoveryDiagnosticsView) -> None:
    """Render only aggregate provider-routing facts approved for Candidate display."""
    panel = st.expander("Discovery diagnostics", expanded=False)
    panel.caption(
        "Counts and routing outcomes only. Search queries, returned content, and Candidate "
        "research content are not displayed."
    )
    raw_column, plausible_column, retained_column = panel.columns(3)
    raw_column.metric("Raw provider results", diagnostics.raw_result_count)
    plausible_column.metric(
        "Plausible profiles before deduplication",
        diagnostics.plausible_supervisor_count,
    )
    retained_column.metric(
        "Retained Prospective Supervisors",
        diagnostics.retained_prospective_supervisor_count,
    )
    panel.write(f"Fallback search used: {'Yes' if diagnostics.fallback_search_used else 'No'}")
    panel.write(f"Discovery route: {_humanize(diagnostics.route.value)}")
    panel.markdown("#### Why raw results were excluded")
    if diagnostics.rejection_counts is None:
        panel.info(
            "Rejection breakdown unavailable. One or more successful attempts may be from "
            "an earlier persisted run without recorded category counts, or providers may "
            "have failed before result filtering. ScholarPath does not infer zeros."
        )
    else:
        rejection_counts = diagnostics.rejection_counts
        panel.caption(
            f"Deterministic exclusion categories account for {rejection_counts.total} "
            "raw provider results."
        )
        panel.write(f"Person not established: {rejection_counts.person_not_established}")
        panel.write(
            f"Academic context not established: {rejection_counts.academic_context_not_established}"
        )
        panel.write(f"Identity conflict: {rejection_counts.identity_conflict}")
        panel.write(f"Institution not established: {rejection_counts.institution_not_established}")
        panel.write(f"Incomplete institution: {rejection_counts.incomplete_institution}")
    panel.markdown("#### Provider attempts")
    for sequence, attempt in enumerate(diagnostics.attempts, start=1):
        error_category = (
            _humanize(attempt.error_category.value)
            if attempt.error_category is not None
            else "None"
        )
        panel.write(
            f"Attempt record {sequence}: {attempt.provider.value}; query attempt number "
            f"{attempt.attempt_number}; {attempt.raw_result_count} raw results; "
            f"{attempt.plausible_supervisor_count} plausible Supervisor profiles; "
            "rejection categories recorded: "
            f"{'Yes' if attempt.rejection_counts is not None else 'No'}; "
            f"error category: {error_category}; route: {_humanize(attempt.route.value)}."
        )


def _render_prospective_supervisors(snapshot: UiRunSnapshot) -> None:
    st.header(STAGE_LABELS[2])
    if not snapshot.prospective_supervisors:
        diagnostics = snapshot.discovery_diagnostics
        if diagnostics is not None and diagnostics.raw_result_count > 0:
            st.info(
                f"Search providers returned {diagnostics.raw_result_count} raw results, but "
                "none passed the plausible person-and-institution checks required to create "
                "a Prospective Supervisor."
            )
        elif diagnostics is not None:
            st.info(
                "Search providers returned no results, so no Prospective Supervisors were retained."
            )
        else:
            st.info("No Prospective Supervisors have been retained yet.")
        return
    for supervisor in snapshot.prospective_supervisors:
        label = f"{supervisor.full_name} — {supervisor.institution}"
        with st.expander(label, expanded=False):
            st.write(f"Institution: {supervisor.institution}")
            st.write(f"Department: {supervisor.department}")
            st.write(f"Lifecycle status: {_humanize(supervisor.status.value)}")
            st.markdown(f"[Official or discovered profile]({supervisor.profile_url})")


def _render_verified_supervisor(
    supervisor: VerifiedSupervisorView,
    *,
    show_evidence: bool,
) -> None:
    label = f"{supervisor.full_name} — {supervisor.institution}"
    if supervisor.research_fit_evidence_limited:
        label = f"{label} · Research Fit: not established"
    elif supervisor.research_fit_score is not None:
        label = f"{label} · Research Fit: {supervisor.research_fit_score}/100"
    with st.expander(label, expanded=False):
        if (
            supervisor.verification_evidence_standard
            is VerificationEvidenceStandard.IDENTITY_ONLY_MVP
        ):
            st.write(f"Discovered institution (not verified): {supervisor.institution}")
            st.write("Verification standard: MVP — identity only")
        else:
            st.write(f"Institution: {supervisor.institution}")
            st.write("Verification standard: Strict")
        st.write(f"Department: {supervisor.department}")
        st.write(f"Verification status: {_humanize(supervisor.verification_status.value)}")
        if supervisor.research_fit_evidence_limited:
            st.warning(
                "Research Fit is not established because directly supported research "
                "evidence is insufficient. No unsupported points were awarded."
            )
        elif supervisor.research_fit_score is not None:
            st.metric("Research Fit Score", f"{supervisor.research_fit_score}/100")
        if supervisor.fit_explanation is not None:
            st.write(f"Fit explanation: {supervisor.fit_explanation}")
        st.write(f"Evidence confidence: {_humanize(supervisor.evidence_confidence.value)}")
        st.write(f"Availability status: {_humanize(supervisor.availability_status.value)}")
        st.write(f"Independent review status: {_humanize(supervisor.independent_review_status)}")
        if supervisor.requires_candidate_attention:
            st.warning("The independent review marked this assessment for Candidate attention.")
        st.markdown(f"[Supervisor profile]({supervisor.profile_url})")
        if supervisor.concerns:
            st.write("Concerns:")
            for concern in supervisor.concerns:
                st.write(f"- {concern}")
        else:
            st.write("Concerns: None recorded.")
        if show_evidence:
            st.write("Evidence sources:")
            for source in supervisor.evidence_sources:
                st.markdown(
                    f"- [{_humanize(source.source_kind.value)}]({source.source_url}) — "
                    f"{source.claim} Confidence: {_humanize(source.confidence.value)}."
                )


def _render_alternate_source_diagnostics(
    diagnostics: AlternateSourceDiagnosticsView,
) -> None:
    """Render aggregate official-profile selection facts without source content."""
    panel = st.expander("Alternate-source diagnostics", expanded=False)
    panel.caption(
        "Privacy-safe alternate-source diagnostics use aggregate counts only. Search queries, "
        "result text, URLs, Supervisor identities, Candidate research content, and credentials "
        "are not displayed."
    )
    attempted_column, result_column, eligible_column, selected_column = panel.columns(4)
    attempted_column.metric(
        "Prospective Supervisors searched",
        diagnostics.attempted_supervisor_count,
    )
    result_column.metric("Alternate search results", diagnostics.result_count)
    eligible_column.metric("Eligible official profiles", diagnostics.eligible_result_count)
    selected_column.metric("Selected official sources", diagnostics.selected_source_count)
    panel.write(f"Searches with no results: {diagnostics.no_results_count}")
    panel.write(f"Searches with every result rejected: {diagnostics.rejected_all_count}")
    panel.write(f"Provider errors: {diagnostics.provider_error_count}")
    panel.write(f"Unconfigured searches: {diagnostics.not_configured_count}")
    panel.markdown("#### Why alternate results were excluded")
    counts = diagnostics.rejection_counts
    panel.caption(
        f"First-failed selector gates account for {counts.total} alternate search results."
    )
    panel.write(f"Originating-query mismatch: {counts.query_mismatch}")
    panel.write(f"Same as the discovered profile URL: {counts.same_url}")
    panel.write(f"HTTPS or hostname invalid: {counts.https_or_host_invalid}")
    panel.write(f"Exact person text missing: {counts.exact_person_text_missing}")
    panel.write(f"Exact institution text missing: {counts.exact_institution_text_missing}")
    panel.write(f"Singular person-profile route missing: {counts.singular_route_mismatch}")
    panel.write(f"Academic institution host mismatch: {counts.academic_host_mismatch}")
    panel.write(f"Official source kind unsupported: {counts.source_kind_unsupported}")


def _render_evidence_verification_diagnostics(
    diagnostics: EvidenceVerificationDiagnosticsView,
) -> None:
    """Render current-round evidence aggregates without source or Candidate content."""
    panel = st.expander("Evidence-verification diagnostics", expanded=False)
    panel.caption(
        "Privacy-safe evidence-verification diagnostics show current-round aggregate counts "
        "only. Retrieval success is not verification; verification additionally requires "
        "directly grounded claims to pass every required evidence gate. Names, URLs, excerpts, "
        "search queries, Candidate content, and credentials are not displayed."
    )
    verified_cohort_minimum = default_minimum_verified_supervisors(
        diagnostics.verification_evidence_standard
    )
    if diagnostics.verification_evidence_standard is VerificationEvidenceStandard.IDENTITY_ONLY_MVP:
        panel.warning(
            "Active required gate: directly grounded identity. Current affiliation and "
            "research evidence are deferred for this MVP run. The graph may continue with at "
            f"least {verified_cohort_minimum} Verified Supervisors under this standard; "
            f"the proposed shortlist remains capped at {MAX_PROPOSED_SHORTLIST_SIZE}."
        )
    else:
        panel.write(
            "Active required gates: identity, current affiliation, and research. The strict "
            f"path requires at least {verified_cohort_minimum} Verified Supervisors; the "
            f"proposed shortlist remains capped at {MAX_PROPOSED_SHORTLIST_SIZE}."
        )

    panel.markdown("#### Primary-source page retrieval")
    primary_attempts, primary_successes, primary_failures = panel.columns(3)
    primary_attempts.metric(
        "Primary retrieval attempts",
        diagnostics.primary_retrieval_attempt_count,
    )
    primary_successes.metric(
        "Primary pages retrieved (retrieval success, not verification)",
        diagnostics.primary_retrieval_success_count,
    )
    primary_failures.metric(
        "Primary retrieval failures",
        diagnostics.primary_retrieval_failure_count,
    )

    panel.markdown("#### Alternate-source page retrieval")
    alternate_attempts, alternate_successes, alternate_failures = panel.columns(3)
    alternate_attempts.metric(
        "Alternate retrieval attempts",
        diagnostics.alternate_retrieval_attempt_count,
    )
    alternate_successes.metric(
        "Alternate pages retrieved (retrieval success, not verification)",
        diagnostics.alternate_retrieval_success_count,
    )
    alternate_failures.metric(
        "Alternate retrieval failures",
        diagnostics.alternate_retrieval_failure_count,
    )

    failure_counts = diagnostics.extraction_failure_counts
    panel.markdown("#### Typed extraction failures")
    panel.caption(
        f"Typed categories account for {failure_counts.total} failed page retrieval attempts."
    )
    for category, count in failure_counts.model_dump(mode="python").items():
        panel.write(f"{_humanize(category)}: {count}")

    panel.markdown("#### Verification outcomes")
    records, completed, partial = panel.columns(3)
    records.metric("Verification records", diagnostics.verification_record_count)
    completed.metric(
        "Completed verification records",
        diagnostics.completed_verification_record_count,
    )
    partial.metric(
        "Partially verified records",
        diagnostics.partial_verification_record_count,
    )
    panel.caption(
        "Completed records are Verified Supervisors, including completed records with concerns."
    )

    retained_counts = diagnostics.retained_claim_counts
    grounded_counts = diagnostics.directly_grounded_claim_counts
    panel.markdown("#### Retained and directly grounded claims")
    panel.caption(
        "Retained claims are shown separately from the stricter directly grounded claims used "
        "by verification."
    )
    for claim_type, retained_count in retained_counts.model_dump(mode="python").items():
        panel.write(
            f"{_humanize(claim_type)}: {retained_count} retained; "
            f"{getattr(grounded_counts, claim_type)} directly grounded."
        )

    missing = diagnostics.missing_required_evidence_counts
    panel.markdown("#### Missing required evidence gates")
    panel.caption(
        "Counts are missing-gate occurrences across partial verification records; one record "
        "may be missing more than one required gate."
    )
    panel.write(f"Identity: {missing.identity}")
    panel.write(f"Current affiliation: {missing.current_affiliation}")
    panel.write(f"Research interest or publication: {missing.research_interest_or_publication}")
    if diagnostics.verification_evidence_standard is VerificationEvidenceStandard.IDENTITY_ONLY_MVP:
        deferred = diagnostics.deferred_evidence_gap_counts
        panel.markdown("#### Deferred evidence gaps (MVP)")
        panel.caption(
            "These gaps do not block identity-only lifecycle verification, but they remain "
            "visible and cannot support Research Fit points."
        )
        panel.write(f"Current affiliation: {deferred.current_affiliation}")
        panel.write(
            f"Research interest or publication: {deferred.research_interest_or_publication}"
        )


def _render_verified_supervisors(snapshot: UiRunSnapshot) -> None:
    st.header(STAGE_LABELS[3])
    if snapshot.alternate_source_diagnostics is not None:
        _render_alternate_source_diagnostics(snapshot.alternate_source_diagnostics)
    if snapshot.evidence_verification_diagnostics is not None:
        _render_evidence_verification_diagnostics(snapshot.evidence_verification_diagnostics)
    if not snapshot.verified_supervisors:
        st.info("No Verified Supervisors are available yet.")
        return
    for supervisor in snapshot.verified_supervisors:
        _render_verified_supervisor(supervisor, show_evidence=True)


def _resume_review(
    service: ScholarPathApplicationPort,
    thread_id: str,
    checkpoint_token: str,
    response: CandidateReviewResponse,
) -> None:
    with st.status("Applying Candidate review", expanded=True, state="running") as status:
        service.resume(
            thread_id,
            checkpoint_token,
            response,
            progress_sink=lambda event: _write_progress_event(status.write, event),
        )
        status.update(label="Candidate review checkpoint saved", state="complete")
    st.rerun()


def _supervisor_label_lookup(
    supervisors: Iterable[VerifiedSupervisorView],
) -> dict[str, str]:
    return {
        supervisor.supervisor_id: f"{supervisor.full_name} — {supervisor.institution}"
        for supervisor in supervisors
    }


def _render_approval_form(
    service: ScholarPathApplicationPort,
    thread_id: str,
    snapshot: UiRunSnapshot,
) -> None:
    labels = _supervisor_label_lookup(snapshot.review_supervisors)
    proposal_order = tuple(labels)
    with st.form("approve_supervisors_form", border=True):
        selected = st.multiselect(
            "Select Verified Supervisors to shortlist",
            proposal_order,
            format_func=labels.__getitem__,
            key="approve_supervisor_ids",
        )
        submitted = st.form_submit_button(
            "Approve selected Supervisors",
            key="approve_supervisors_submit",
            type="primary",
            width="stretch",
        )
    if not submitted:
        return
    selected_ids = set(selected)
    ordered_ids = tuple(item for item in proposal_order if item in selected_ids)
    if not ordered_ids:
        st.error("Select at least one Verified Supervisor to approve.")
        return
    try:
        _resume_review(
            service,
            thread_id,
            snapshot.checkpoint_token,
            CandidateApproveResponse(action="approve", supervisor_ids=ordered_ids),
        )
    except Exception:
        st.error(RECOVERABLE_SERVICE_MESSAGE)


def _render_rejection_form(
    service: ScholarPathApplicationPort,
    thread_id: str,
    snapshot: UiRunSnapshot,
) -> None:
    labels = _supervisor_label_lookup(snapshot.review_supervisors)
    with st.form("reject_supervisor_form", border=True):
        supervisor_id = st.selectbox(
            "Supervisor to reject",
            tuple(labels),
            format_func=labels.__getitem__,
            key="reject_supervisor_id",
        )
        reason = st.text_area(
            "Reason for rejection *",
            key="reject_supervisor_reason",
        )
        submitted = st.form_submit_button(
            "Reject this Supervisor",
            key="reject_supervisor_submit",
            width="stretch",
        )
    if not submitted:
        return
    if not reason.strip():
        st.error("Provide a reason before rejecting a Supervisor.")
        return
    try:
        response = CandidateRejectResponse(
            action="reject",
            rejections=(CandidateRejectionReason(supervisor_id=supervisor_id, reason=reason),),
        )
        _resume_review(service, thread_id, snapshot.checkpoint_token, response)
    except Exception:
        st.error(RECOVERABLE_SERVICE_MESSAGE)


def _render_request_more_form(
    service: ScholarPathApplicationPort,
    thread_id: str,
    snapshot: UiRunSnapshot,
) -> None:
    with st.form("request_more_research_form", border=True):
        topics = st.text_input(
            "Revised research interests",
            key="request_more_research_topics",
        )
        regions = st.text_input(
            "Revised preferred regions",
            key="request_more_regions",
        )
        study_modes = st.multiselect(
            "Revised study mode",
            STUDY_MODE_OPTIONS,
            key="request_more_study_modes",
        )
        orientation = st.selectbox(
            "Revised research orientation",
            ("No change", "applied", "theoretical", "mixed"),
            key="request_more_orientation",
        )
        methods = st.text_input(
            "Revised methodological interests",
            key="request_more_methods",
        )
        constraints = st.text_input(
            "Revised practical constraints",
            key="request_more_constraints",
        )
        exclusions = st.text_input(
            "Revised exclusions",
            key="request_more_exclusions",
        )
        submitted = st.form_submit_button(
            "Request more Supervisor research",
            key="request_more_submit",
            width="stretch",
        )
    if not submitted:
        return
    try:
        response = build_request_more_response(
            research_topics=topics,
            preferred_regions=regions,
            study_modes=study_modes,
            research_orientation=orientation,
            methodological_interests=methods,
            constraints=constraints,
            exclusions=exclusions,
        )
    except (ValidationError, ValueError):
        st.error("Enter at least one revised preference before requesting more research.")
        return
    try:
        _resume_review(service, thread_id, snapshot.checkpoint_token, response)
    except Exception:
        st.error(RECOVERABLE_SERVICE_MESSAGE)


def _render_candidate_review(
    service: ScholarPathApplicationPort,
    thread_id: str,
    snapshot: UiRunSnapshot,
) -> None:
    st.header(STAGE_LABELS[4])
    st.write(
        f"Review iteration {snapshot.review_iteration} of "
        f"{snapshot.maximum_review_iterations}. No Supervisor becomes shortlisted without "
        "your explicit approval."
    )
    for supervisor in snapshot.review_supervisors:
        _render_verified_supervisor(supervisor, show_evidence=True)
    approve_tab, reject_tab, request_more_tab = st.tabs(
        ["Approve", "Reject", "Request more research"]
    )
    with approve_tab:
        _render_approval_form(service, thread_id, snapshot)
    with reject_tab:
        _render_rejection_form(service, thread_id, snapshot)
    with request_more_tab:
        _render_request_more_form(service, thread_id, snapshot)


def _render_shortlist(snapshot: UiRunSnapshot) -> None:
    st.header(STAGE_LABELS[5])
    st.success("These Verified Supervisors were explicitly approved and shortlisted.")
    if snapshot.shortlist_briefing is not None:
        st.write(snapshot.shortlist_briefing)
    for supervisor in snapshot.shortlisted_supervisors:
        _render_verified_supervisor(supervisor, show_evidence=True)


def _render_errors(snapshot: UiRunSnapshot) -> None:
    for error in snapshot.errors:
        occurrence_note = (
            f" This issue was recorded {error.occurrence_count} times in the current run."
            if error.occurrence_count > 1
            else ""
        )
        diagnostics = snapshot.discovery_diagnostics
        if (
            error.code == "supervisor_discovery_incomplete"
            and diagnostics is not None
            and diagnostics.retained_prospective_supervisor_count == 0
        ):
            st.warning(
                "Supervisor discovery completed its bounded provider attempts without "
                "retaining a Prospective Supervisor. Revise the search preferences and try "
                f"again.{occurrence_note}"
            )
            continue
        if error.recoverable:
            st.warning(f"{error.message} You can revise the search and try again.{occurrence_note}")
        else:
            st.error(f"{error.message}{occurrence_note}")


def _render_existing_thread(thread_id: str) -> None:
    try:
        service = application_service()
        snapshot = service.inspect(thread_id)
    except Exception:
        st.error(RECOVERABLE_SERVICE_MESSAGE)
        return
    if snapshot is None:
        st.error("The saved research thread is unavailable. Start a new Supervisor search.")
        return

    _render_progress(snapshot)
    _render_prospective_supervisors(snapshot)
    _render_verified_supervisors(snapshot)
    _render_errors(snapshot)
    if snapshot.stage is UiStage.REVIEW_SUPERVISORS:
        _render_candidate_review(service, thread_id, snapshot)
    elif snapshot.stage is UiStage.SUPERVISOR_SHORTLIST:
        _render_shortlist(snapshot)
    elif snapshot.stage is UiStage.STOPPED:
        st.header(STAGE_LABELS[4])
        st.warning("The current research run stopped safely. Review the messages above.")

    if st.button("Start a new research run", key="start_new_research_run"):
        st.session_state.pop("thread_id", None)
        st.rerun()


def main() -> None:
    """Render the single ScholarPath application without constructing graph business logic."""
    st.set_page_config(page_title="ScholarPath", page_icon=PAGE_ICON, layout="wide")
    theme = render_appearance_controls()
    _render_hero()
    inject_theme_styles(theme)
    _render_runtime_profile_banner()
    _render_stage_navigation()
    thread_id = st.session_state.get("thread_id")
    if isinstance(thread_id, str) and thread_id.strip():
        _render_existing_thread(thread_id)
    else:
        _render_profile_form()
