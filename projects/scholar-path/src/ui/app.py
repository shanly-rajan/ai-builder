"""Thin Streamlit renderer for the typed ScholarPath application service."""

from __future__ import annotations

from collections.abc import Callable, Iterable

import streamlit as st
from pydantic import ValidationError

from ..graph import (
    CandidateApproveResponse,
    CandidateRejectionReason,
    CandidateRejectResponse,
    CandidateReviewResponse,
)
from . import dependencies
from .controller import build_candidate_submission, build_request_more_response
from .models import (
    DiscoveryDiagnosticsView,
    GraphProgressEvent,
    UiRunSnapshot,
    UiStage,
    VerifiedSupervisorView,
)
from .service import ScholarPathApplicationPort

STAGE_LABELS = (
    "1. Your Doctoral Research Profile",
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


@st.cache_resource(show_spinner=False)
def application_service() -> ScholarPathApplicationPort:
    """Cache only shared infrastructure; Candidate data remains checkpoint-scoped."""
    return dependencies.create_application_service()


def _humanize(value: str) -> str:
    return value.replace("_", " ").strip().capitalize()


def _render_stage_navigation() -> None:
    st.caption("  →  ".join(STAGE_LABELS))


def _render_profile_form() -> None:
    st.header(STAGE_LABELS[0])
    st.write(
        "Describe the doctoral research direction and practical preferences that should guide "
        "Supervisor discovery."
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
        expanded=True,
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
    st.subheader("Privacy-safe discovery diagnostics")
    st.caption(
        "Counts and routing outcomes only. Search queries, returned content, and Candidate "
        "research content are not displayed."
    )
    raw_column, plausible_column, retained_column = st.columns(3)
    raw_column.metric("Raw provider results", diagnostics.raw_result_count)
    plausible_column.metric(
        "Plausible profiles before deduplication",
        diagnostics.plausible_supervisor_count,
    )
    retained_column.metric(
        "Retained Prospective Supervisors",
        diagnostics.retained_prospective_supervisor_count,
    )
    st.write(f"Fallback search used: {'Yes' if diagnostics.fallback_search_used else 'No'}")
    st.write(f"Discovery route: {_humanize(diagnostics.route.value)}")
    with st.expander("Provider attempts", expanded=False):
        for sequence, attempt in enumerate(diagnostics.attempts, start=1):
            error_category = (
                _humanize(attempt.error_category.value)
                if attempt.error_category is not None
                else "None"
            )
            st.write(
                f"Attempt record {sequence}: {attempt.provider.value}; query attempt number "
                f"{attempt.attempt_number}; {attempt.raw_result_count} raw results; "
                f"{attempt.plausible_supervisor_count} plausible Supervisor profiles; "
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
        with st.container(border=True):
            st.subheader(supervisor.full_name)
            st.write(f"Institution: {supervisor.institution}")
            st.write(f"Department: {supervisor.department}")
            st.write(f"Lifecycle status: {_humanize(supervisor.status.value)}")
            st.markdown(f"[Official or discovered profile]({supervisor.profile_url})")


def _render_verified_supervisor(
    supervisor: VerifiedSupervisorView,
    *,
    show_evidence: bool,
) -> None:
    with st.container(border=True):
        st.subheader(supervisor.full_name)
        st.write(f"Institution: {supervisor.institution}")
        st.write(f"Department: {supervisor.department}")
        st.write(f"Verification status: {_humanize(supervisor.verification_status.value)}")
        if supervisor.research_fit_score is not None:
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


def _render_verified_supervisors(snapshot: UiRunSnapshot) -> None:
    st.header(STAGE_LABELS[3])
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
        diagnostics = snapshot.discovery_diagnostics
        if (
            error.code == "supervisor_discovery_incomplete"
            and diagnostics is not None
            and diagnostics.retained_prospective_supervisor_count == 0
        ):
            st.warning(
                "Supervisor discovery completed its bounded provider attempts without "
                "retaining a Prospective Supervisor. Revise the search preferences and try "
                "again."
            )
            continue
        if error.recoverable:
            st.warning(f"{error.message} You can revise the search and try again.")
        else:
            st.error(error.message)


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
    st.set_page_config(page_title="ScholarPath", page_icon="🎓", layout="wide")
    st.title("ScholarPath")
    st.write(
        "Discover, verify, evaluate, and review research-aligned Supervisors with "
        "evidence-backed Research Fit assessments."
    )
    _render_stage_navigation()
    thread_id = st.session_state.get("thread_id")
    if isinstance(thread_id, str) and thread_id.strip():
        _render_existing_thread(thread_id)
    else:
        _render_profile_form()
