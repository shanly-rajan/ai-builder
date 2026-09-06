"""Fixed linked-profile examples preserve grounding outcomes and failure order."""

from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest
from pydantic import HttpUrl

from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaim,
    EvidenceClaimType,
    GroundingFailureReason,
    SourceKind,
    evidence_claim_grounding_failure,
    evidence_claim_is_grounded_for_supervisor,
)
from scholarpath.domain import models as domain_models
from tests.unit.domain.test_grounding_failure_reasons import _claim, _supervisor


@dataclass(frozen=True)
class _ContextCase:
    label: str
    expected_grounded: bool
    reason: str | None
    claim_updates: dict[str, object] = field(default_factory=dict)
    identity_updates: dict[str, object] = field(default_factory=dict)
    include_identity: bool = True


_LINK_FAILURE_CASES = (
    _ContextCase("missing-identity", False, "context_identity_not_found", include_identity=False),
    _ContextCase(
        "wrong-identity-type",
        False,
        "context_identity_type_mismatch",
        identity_updates={"claim_type": EvidenceClaimType.RESEARCH_INTEREST},
    ),
    _ContextCase(
        "indirect-identity",
        False,
        "context_identity_not_directly_supported",
        identity_updates={"directly_supported": False},
    ),
    _ContextCase(
        "different-supervisor",
        False,
        "context_supervisor_id_mismatch",
        identity_updates={"supervisor_id": "another-supervisor"},
    ),
    _ContextCase(
        "different-source-kind",
        False,
        "context_source_kind_mismatch",
        identity_updates={"source_kind": SourceKind.INSTITUTIONAL_DIRECTORY},
    ),
    _ContextCase(
        "different-page",
        False,
        "context_source_url_mismatch",
        identity_updates={"source_url": HttpUrl("https://example.edu/people/other-person")},
    ),
    _ContextCase(
        "different-retrieval",
        False,
        "context_retrieval_time_mismatch",
        identity_updates={"retrieved_at": datetime(2026, 8, 2, tzinfo=UTC)},
    ),
    _ContextCase(
        "chained-identity",
        False,
        "context_identity_reference_chained",
        identity_updates={"subject_identity_evidence_id": "further-identity"},
    ),
    _ContextCase(
        "identity-name-missing",
        False,
        "context_identity_name_missing",
        identity_updates={"asserted_name": None},
    ),
    _ContextCase(
        "identity-excerpt-missing",
        False,
        "context_identity_excerpt_missing",
        identity_updates={"supporting_excerpt": None},
    ),
    _ContextCase(
        "identity-name-absent-from-excerpt",
        False,
        "context_identity_name_not_in_excerpt",
        identity_updates={"supporting_excerpt": "An official research profile."},
    ),
    _ContextCase(
        "identity-name-differs",
        False,
        "context_identity_name_mismatch",
        identity_updates={
            "asserted_name": "Dr Different Person",
            "supporting_excerpt": "Dr Different Person",
        },
    ),
    _ContextCase(
        "identity-does-not-match-supervisor-through-alias",
        False,
        "context_identity_not_grounded",
        claim_updates={"asserted_name": "Dr Alexander (Alex) Morgan"},
        identity_updates={
            "asserted_name": "Dr Alexander Morgan",
            "supporting_excerpt": "Dr Alexander Morgan",
        },
    ),
    _ContextCase(
        "ineligible-context-source",
        False,
        "profile_source_ineligible",
        claim_updates={"source_kind": SourceKind.OTHER},
    ),
    _ContextCase(
        "ineligible-context-route",
        False,
        "profile_route_ineligible",
        claim_updates={"source_url": HttpUrl("https://example.edu/people")},
    ),
)

_CONTEXT_CASES = (
    *_LINK_FAILURE_CASES,
    _ContextCase("research-section", True, None),
    _ContextCase(
        "institutional-directory",
        True,
        None,
        claim_updates={"source_kind": SourceKind.INSTITUTIONAL_DIRECTORY},
        identity_updates={"source_kind": SourceKind.INSTITUTIONAL_DIRECTORY},
    ),
    _ContextCase(
        "title-equivalent-identity",
        True,
        None,
        identity_updates={
            "asserted_name": "Professor Alex Morgan",
            "supporting_excerpt": "Professor Alex Morgan",
        },
    ),
    _ContextCase(
        "first-person-research",
        True,
        None,
        claim_updates={"supporting_excerpt": "I research secure systems."},
    ),
    _ContextCase(
        "pronoun-with-presentation-markup",
        True,
        None,
        claim_updates={"supporting_excerpt": " > ** She researches secure systems."},
    ),
    _ContextCase(
        "methodology-section",
        True,
        None,
        claim_updates={
            "claim_type": EvidenceClaimType.METHODOLOGY,
            "supporting_excerpt": "Methods: formal verification.",
        },
    ),
    _ContextCase(
        "publication-section",
        True,
        None,
        claim_updates={
            "claim_type": EvidenceClaimType.PUBLICATION,
            "supporting_excerpt": "Selected publications: Secure Systems.",
        },
    ),
    _ContextCase(
        "project-section",
        True,
        None,
        claim_updates={
            "claim_type": EvidenceClaimType.PROJECT,
            "supporting_excerpt": "Current projects: Secure Systems.",
        },
    ),
    _ContextCase(
        "affiliation-does-not-require-subject-prefix",
        True,
        None,
        claim_updates={
            "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
            "supporting_excerpt": "Professor, Department of Computing, Example University.",
            "asserted_institution": "Example University",
            "asserted_department": "Department of Computing",
        },
    ),
    _ContextCase(
        "contextual-availability",
        True,
        None,
        claim_updates={
            "claim_type": EvidenceClaimType.AVAILABILITY,
            "supporting_excerpt": "I am accepting new postgraduate research students.",
            "availability_status": AvailabilityStatus.CONFIRMED_ACCEPTING,
        },
    ),
    _ContextCase(
        "titled-person-conflict",
        False,
        "context_conflicting_person",
        claim_updates={"supporting_excerpt": "Research interests: Dr Jane Smith studies safety."},
    ),
    _ContextCase(
        "untitled-person-conflict",
        False,
        "context_conflicting_person",
        claim_updates={"supporting_excerpt": "Research interests of Jane Smith: secure systems."},
    ),
    _ContextCase(
        "subject-pattern-missing",
        False,
        "context_subject_pattern_missing",
        claim_updates={"supporting_excerpt": "Secure systems are a research topic."},
    ),
    _ContextCase(
        "wrong-section-for-claim-type",
        False,
        "context_subject_pattern_missing",
        claim_updates={"supporting_excerpt": "Methods: formal verification."},
    ),
    _ContextCase(
        "direct-subject-with-valid-link-still-requires-context-pattern",
        False,
        "context_subject_pattern_missing",
        claim_updates={"supporting_excerpt": "Dr Alex Morgan researches secure systems."},
    ),
    _ContextCase(
        "direct-subject-without-link",
        True,
        None,
        claim_updates={
            "subject_identity_evidence_id": None,
            "supporting_excerpt": "Dr Alex Morgan researches secure systems.",
        },
    ),
    _ContextCase(
        "section-without-link",
        False,
        "subject_not_established",
        claim_updates={"subject_identity_evidence_id": None},
    ),
)


def _context(case: _ContextCase) -> tuple[EvidenceClaim, tuple[EvidenceClaim, ...]]:
    identity = _claim(**case.identity_updates)
    updates: dict[str, object] = {
        "evidence_id": "contextual-evidence",
        "claim_type": EvidenceClaimType.RESEARCH_INTEREST,
        "supporting_excerpt": "Research interests: secure systems.",
        "subject_identity_evidence_id": identity.evidence_id,
        **case.claim_updates,
    }
    claim = _claim(**updates)
    return claim, (identity, claim) if case.include_identity else (claim,)


@pytest.mark.parametrize("case", _CONTEXT_CASES, ids=lambda case: case.label)
def test_fixed_context_boolean_baseline_and_no_mutation(case: _ContextCase) -> None:
    """Expected booleans were fixed independently of the newly exposed reasons."""
    claim, evidence = _context(case)
    supervisor = _supervisor()
    before = (claim.model_dump(), supervisor.model_dump(), [item.model_dump() for item in evidence])

    assert evidence_claim_is_grounded_for_supervisor(claim, supervisor, evidence) is (
        case.expected_grounded
    )
    assert (
        claim.model_dump(),
        supervisor.model_dump(),
        [item.model_dump() for item in evidence],
    ) == before


@pytest.mark.parametrize("case", _CONTEXT_CASES, ids=lambda case: case.label)
def test_context_failures_return_precise_enum_members(case: _ContextCase) -> None:
    claim, evidence = _context(case)
    before = (claim.model_dump(), [item.model_dump() for item in evidence])
    expected = None if case.reason is None else GroundingFailureReason(case.reason)

    assert evidence_claim_grounding_failure(claim, _supervisor(), evidence) is expected
    assert (claim.model_dump(), [item.model_dump() for item in evidence]) == before


@pytest.mark.parametrize("case", _LINK_FAILURE_CASES, ids=lambda case: case.label)
def test_direct_subject_does_not_bypass_an_invalid_explicit_link(case: _ContextCase) -> None:
    assert case.reason is not None
    claim, evidence = _context(case)
    claim = _claim(
        **{
            **claim.model_dump(mode="python"),
            "supporting_excerpt": f"{claim.asserted_name} researches secure systems.",
        }
    )
    without_link = _claim(
        **{**claim.model_dump(mode="python"), "subject_identity_evidence_id": None}
    )
    assert evidence_claim_is_grounded_for_supervisor(without_link, _supervisor(), evidence) is True
    assert evidence_claim_grounding_failure(claim, _supervisor(), evidence) is (
        GroundingFailureReason(case.reason)
    )
    assert evidence_claim_is_grounded_for_supervisor(claim, _supervisor(), evidence) is False


@pytest.mark.parametrize(
    "case",
    [
        _ContextCase(
            "source-before-route-and-lookup",
            False,
            "profile_source_ineligible",
            claim_updates={
                "source_kind": SourceKind.OTHER,
                "source_url": HttpUrl("https://example.edu/people"),
            },
            include_identity=False,
        ),
        _ContextCase(
            "route-before-lookup",
            False,
            "profile_route_ineligible",
            claim_updates={"source_url": HttpUrl("https://example.edu/people")},
            include_identity=False,
        ),
        _ContextCase(
            "type-before-direct-support",
            False,
            "context_identity_type_mismatch",
            identity_updates={
                "claim_type": EvidenceClaimType.RESEARCH_INTEREST,
                "directly_supported": False,
            },
        ),
        _ContextCase(
            "direct-support-before-supervisor",
            False,
            "context_identity_not_directly_supported",
            identity_updates={"directly_supported": False, "supervisor_id": "another-supervisor"},
        ),
        _ContextCase(
            "supervisor-before-source-kind",
            False,
            "context_supervisor_id_mismatch",
            identity_updates={
                "supervisor_id": "another-supervisor",
                "source_kind": SourceKind.OTHER,
            },
        ),
        _ContextCase(
            "source-kind-before-source-url",
            False,
            "context_source_kind_mismatch",
            identity_updates={
                "source_kind": SourceKind.OTHER,
                "source_url": HttpUrl("https://example.edu/people/other-person"),
            },
        ),
        _ContextCase(
            "source-url-before-retrieval-time",
            False,
            "context_source_url_mismatch",
            identity_updates={
                "source_url": HttpUrl("https://example.edu/people/other-person"),
                "retrieved_at": datetime(2026, 8, 2, tzinfo=UTC),
            },
        ),
        _ContextCase(
            "retrieval-time-before-chain",
            False,
            "context_retrieval_time_mismatch",
            identity_updates={
                "retrieved_at": datetime(2026, 8, 2, tzinfo=UTC),
                "subject_identity_evidence_id": "further-identity",
            },
        ),
        _ContextCase(
            "chain-before-identity-name",
            False,
            "context_identity_reference_chained",
            identity_updates={
                "subject_identity_evidence_id": "further-identity",
                "asserted_name": None,
            },
        ),
        _ContextCase(
            "identity-name-before-identity-excerpt",
            False,
            "context_identity_name_missing",
            identity_updates={"asserted_name": None, "supporting_excerpt": None},
        ),
        _ContextCase(
            "exact-name-in-excerpt-before-linked-name-equivalence",
            False,
            "context_identity_name_not_in_excerpt",
            identity_updates={
                "asserted_name": "Dr Different Person",
                "supporting_excerpt": "An official research profile.",
            },
        ),
        _ContextCase(
            "identity-grounding-before-context-conflict",
            False,
            "context_identity_not_grounded",
            claim_updates={
                "asserted_name": "Dr Alexander (Alex) Morgan",
                "supporting_excerpt": "Research interests: Dr Jane Smith studies safety.",
            },
            identity_updates={
                "asserted_name": "Dr Alexander Morgan",
                "supporting_excerpt": "Dr Alexander Morgan",
            },
        ),
        _ContextCase(
            "conflicting-person-before-subject-pattern",
            False,
            "context_conflicting_person",
            claim_updates={"supporting_excerpt": "Dr Jane Smith researches secure systems."},
        ),
        _ContextCase(
            "context-conflict-before-affiliation-fields",
            False,
            "context_conflicting_person",
            claim_updates={
                "claim_type": EvidenceClaimType.CURRENT_AFFILIATION,
                "supporting_excerpt": "Dr Jane Smith is a professor.",
            },
        ),
        _ContextCase(
            "context-pattern-before-availability-polarity",
            False,
            "context_subject_pattern_missing",
            claim_updates={
                "claim_type": EvidenceClaimType.AVAILABILITY,
                "availability_status": AvailabilityStatus.CONFIRMED_ACCEPTING,
                "supporting_excerpt": "Supervision status: not stated.",
            },
        ),
        _ContextCase(
            "public-name-guard-before-link-failures",
            False,
            "asserted_name_missing",
            claim_updates={"asserted_name": None},
            include_identity=False,
        ),
    ],
    ids=lambda case: case.label,
)
def test_context_reports_the_first_failure_when_multiple_checks_fail(case: _ContextCase) -> None:
    assert case.reason is not None
    claim, evidence = _context(case)

    assert evidence_claim_grounding_failure(claim, _supervisor(), evidence) is (
        GroundingFailureReason(case.reason)
    )
    assert evidence_claim_is_grounded_for_supervisor(claim, _supervisor(), evidence) is False


@pytest.mark.parametrize(
    "case",
    [
        _ContextCase(
            "missing-reference",
            False,
            "context_identity_reference_missing",
            claim_updates={"subject_identity_evidence_id": None},
        ),
        _ContextCase(
            "missing-reference-before-ineligible-source",
            False,
            "context_identity_reference_missing",
            claim_updates={"subject_identity_evidence_id": None, "source_kind": SourceKind.OTHER},
        ),
        _ContextCase(
            "missing-claim-name",
            False,
            "context_claim_name_missing",
            claim_updates={"asserted_name": None},
        ),
        _ContextCase(
            "identity-excerpt-before-claim-name",
            False,
            "context_identity_excerpt_missing",
            claim_updates={"asserted_name": None},
            identity_updates={"supporting_excerpt": None},
        ),
        _ContextCase(
            "claim-name-before-identity-name-in-excerpt",
            False,
            "context_claim_name_missing",
            claim_updates={"asserted_name": None},
            identity_updates={"supporting_excerpt": "An official research profile."},
        ),
    ],
    ids=lambda case: case.label,
)
def test_reference_failures_hidden_by_public_guards(case: _ContextCase) -> None:
    """Only the internal resolver can report these before the public claim guards."""
    assert case.reason is not None
    claim, evidence = _context(case)
    evidence_by_id = {item.evidence_id: item for item in evidence}
    before = (claim.model_dump(), {key: item.model_dump() for key, item in evidence_by_id.items()})

    assert domain_models._subject_identity_reference_failure(claim, evidence_by_id) is (
        GroundingFailureReason(case.reason)
    )
    assert domain_models._subject_identity_reference_resolves(claim, evidence_by_id) is False
    assert (
        claim.model_dump(),
        {key: item.model_dump() for key, item in evidence_by_id.items()},
    ) == before
