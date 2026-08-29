"""Pure functions governing valid Supervisor lifecycle transitions."""

from collections.abc import Sequence
from datetime import datetime

from pydantic import ValidationError

from .enums import (
    AvailabilityStatus,
    CandidateReviewAction,
    SupervisorLifecycleStatus,
    VerificationStatus,
)
from .models import (
    CandidateReviewDecision,
    EvidenceClaim,
    ProspectiveSupervisor,
    SupervisorShortlist,
    VerifiedSupervisor,
    derive_availability_status,
    missing_verification_evidence,
)

_STRUCTURAL_TRANSITIONS: dict[SupervisorLifecycleStatus, frozenset[SupervisorLifecycleStatus]] = {
    SupervisorLifecycleStatus.PROSPECTIVE: frozenset({SupervisorLifecycleStatus.VERIFIED}),
    SupervisorLifecycleStatus.VERIFIED: frozenset(
        {
            SupervisorLifecycleStatus.SHORTLISTED,
            SupervisorLifecycleStatus.REJECTED,
        }
    ),
    SupervisorLifecycleStatus.SHORTLISTED: frozenset(),
    SupervisorLifecycleStatus.REJECTED: frozenset(),
}


class InvalidSupervisorTransitionError(ValueError):
    """Raised when a requested lifecycle transition is not allowed."""


class SupervisorVerificationError(ValueError):
    """Raised when evidence cannot establish a Verified Supervisor."""


class CandidateReviewScopeError(ValueError):
    """Raised when a Candidate decision does not address a supplied Supervisor."""


class CandidateApprovalRequiredError(ValueError):
    """Raised when shortlist creation lacks explicit Candidate approval."""


def structurally_allowed_transitions(
    current_status: SupervisorLifecycleStatus,
) -> frozenset[SupervisorLifecycleStatus]:
    """Return topologically possible statuses without authorizing a transition."""
    return _STRUCTURAL_TRANSITIONS[current_status]


def is_structural_transition_allowed(
    current_status: SupervisorLifecycleStatus,
    target_status: SupervisorLifecycleStatus,
) -> bool:
    """Report whether two statuses are adjacent in the canonical lifecycle."""
    return target_status in structurally_allowed_transitions(current_status)


def validate_structural_transition(
    current_status: SupervisorLifecycleStatus,
    target_status: SupervisorLifecycleStatus,
) -> None:
    """Reject invalid topology; operation helpers enforce evidence and approval."""
    if not is_structural_transition_allowed(current_status, target_status):
        raise InvalidSupervisorTransitionError(
            f"Cannot move a Supervisor from {current_status.value} to {target_status.value}."
        )


def verify_supervisor(
    supervisor: ProspectiveSupervisor,
    evidence: Sequence[EvidenceClaim],
    *,
    availability_status: AvailabilityStatus | None = None,
    verification_concerns: Sequence[str] = (),
) -> VerifiedSupervisor:
    """Create a Verified Supervisor after deterministic evidence checks."""
    validate_structural_transition(supervisor.status, SupervisorLifecycleStatus.VERIFIED)
    evidence_tuple = tuple(evidence)
    missing = missing_verification_evidence(evidence_tuple, supervisor)
    if missing:
        raise SupervisorVerificationError(
            f"Cannot verify Supervisor; missing evidence: {', '.join(missing)}."
        )

    concerns_tuple = tuple(verification_concerns)
    resolved_availability_status = availability_status or derive_availability_status(
        evidence_tuple, supervisor.supervisor_id
    )
    verification_status = (
        VerificationStatus.VERIFIED_WITH_CONCERNS if concerns_tuple else VerificationStatus.VERIFIED
    )
    supervisor_data = supervisor.model_dump(mode="python", exclude={"status"})
    try:
        return VerifiedSupervisor.model_validate(
            {
                **supervisor_data,
                "evidence": evidence_tuple,
                "status": SupervisorLifecycleStatus.VERIFIED,
                "verification_status": verification_status,
                "availability_status": resolved_availability_status,
                "verification_concerns": concerns_tuple,
            }
        )
    except ValidationError as error:
        raise SupervisorVerificationError(
            "Cannot verify Supervisor because the evidence collection is inconsistent."
        ) from error


def apply_candidate_review(
    supervisor: VerifiedSupervisor,
    decision: CandidateReviewDecision,
) -> VerifiedSupervisor:
    """Apply a scoped Candidate decision without bypassing the approval gate."""
    if supervisor.supervisor_id not in decision.supervisor_ids:
        raise CandidateReviewScopeError(
            "Candidate decision does not address the supplied Supervisor."
        )
    if supervisor.status is not SupervisorLifecycleStatus.VERIFIED:
        raise InvalidSupervisorTransitionError(
            "Candidate review can only be applied to a Verified Supervisor."
        )
    if decision.action is CandidateReviewAction.REQUEST_MORE:
        target_status = SupervisorLifecycleStatus.VERIFIED
    else:
        target_status = (
            SupervisorLifecycleStatus.SHORTLISTED
            if decision.action is CandidateReviewAction.APPROVE
            else SupervisorLifecycleStatus.REJECTED
        )
        validate_structural_transition(supervisor.status, target_status)
    supervisor_data = supervisor.model_dump(mode="python")
    return VerifiedSupervisor.model_validate(
        {
            **supervisor_data,
            "status": target_status,
            "candidate_review_decision": decision,
        }
    )


def create_supervisor_shortlist(
    candidate_id: str,
    supervisors: Sequence[VerifiedSupervisor],
    decision: CandidateReviewDecision,
    *,
    generated_at: datetime,
    briefing: str,
) -> SupervisorShortlist:
    """Build a shortlist only from Supervisors explicitly approved by the Candidate."""
    if decision.action is not CandidateReviewAction.APPROVE:
        raise CandidateApprovalRequiredError(
            "Explicit Candidate approval is required to create a shortlist."
        )

    input_ids = [supervisor.supervisor_id for supervisor in supervisors]
    if len(input_ids) != len(set(input_ids)):
        raise CandidateReviewScopeError("Supervisor input identifiers must be unique.")
    supervisors_by_id = {supervisor.supervisor_id: supervisor for supervisor in supervisors}
    missing_ids = [
        supervisor_id
        for supervisor_id in decision.supervisor_ids
        if supervisor_id not in supervisors_by_id
    ]
    if missing_ids:
        joined_ids = ", ".join(missing_ids)
        raise CandidateReviewScopeError(
            f"Candidate decision references unknown Supervisor identifiers: {joined_ids}."
        )

    shortlisted = tuple(
        apply_candidate_review(supervisors_by_id[supervisor_id], decision)
        for supervisor_id in decision.supervisor_ids
    )
    return SupervisorShortlist(
        candidate_id=candidate_id,
        shortlisted_supervisors=shortlisted,
        generated_at=generated_at,
        briefing=briefing,
    )
