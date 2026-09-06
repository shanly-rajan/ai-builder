"""Synthetic named specialisation is contextual evidence, never an identity shortcut."""

from dataclasses import replace

import pytest

from scholarpath.domain import (
    EvidenceClaimType,
    GroundingFailureReason,
    evidence_claim_grounding_failure,
)
from scholarpath.domain.models import profile_context_excerpt_failure
from scholarpath.evaluation.grounding_replay import (
    RejectedExcerptCapture,
    replay_details,
    replay_snapshot,
)
from tests.unit.domain.test_grounding_failure_reasons import _claim, _supervisor
from tests.unit.domain.test_profile_context_failure_reasons import (
    _LINK_FAILURE_CASES,
    _context,
    _ContextCase,
)

RELATION = "is an engineer and academic specialising in secure systems."
EXCERPT = f"Alex Morgan {RELATION}"


@pytest.mark.parametrize("title", ["", "Dr ", "Dr. ", "Professor ", "Prof. "])
@pytest.mark.parametrize("spelling", ["specialising", "specializing"])
def test_explicit_specialisation_accepts_complete_owner_with_or_without_title(
    title: str, spelling: str
) -> None:
    identity = _claim()
    excerpt = f"{title}Alex Morgan {RELATION}".replace("specialising", spelling)
    claim = _claim(
        evidence_id="research-specialisation",
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        supporting_excerpt=excerpt,
        subject_identity_evidence_id=identity.evidence_id,
    )
    before = claim.model_dump_json()
    assert evidence_claim_grounding_failure(claim, _supervisor(), (identity,)) is None
    assert claim.model_dump_json() == before


@pytest.mark.parametrize("wrapper", ["", "Research Overview:\n", "## Research Overview\n"])
def test_presentation_normalization_preserves_the_exact_excerpt(wrapper: str) -> None:
    excerpt = wrapper + EXCERPT.replace(" ", "\t").upper()
    assert (
        profile_context_excerpt_failure(
            EvidenceClaimType.RESEARCH_INTEREST, "Dr Alex Morgan", excerpt
        )
        is None
    )


@pytest.mark.parametrize(
    "excerpt",
    [
        f"Alice Taylor {RELATION}",
        f"Alex Morganstown {RELATION}",
        f"Alex Morgan Smith {RELATION}",
        f"Alexander Morgan {RELATION}",
        f"Morgan {RELATION}",
        f"Alex {RELATION}",
        f"An account of Alex Morgan {RELATION}",
        f'"Alex Morgan {RELATION}"',
        "Alex Morgan is an engineer and academic at Example University.",
        "Alex Morgan is an engineer and academic not specialising in secure systems.",
        "Alex Morgan was an engineer and academic specialising in secure systems.",
        "Alex Morgan may be an engineer and academic specialising in secure systems.",
        "Alex Morgan is not an engineer and academic specialising in secure systems.",
        "Alex Morgan is researching secure systems.",
        "Alex Morgan is an engineer and academic specialising in",
        "Alex Morgan is an engineer and academic specialising in .",
        "Alex Morgan is an engineer and academic specialising instead in secure systems.",
        "Alex Morgan is an engineer and academic specialising in? Secure systems.",
        "Alex Morgan is an engineer and academic specialising in: secure systems.",
    ],
)
def test_new_relation_does_not_accept_wrong_owner_or_unsupported_sentence(excerpt: str) -> None:
    assert (
        profile_context_excerpt_failure(
            EvidenceClaimType.RESEARCH_INTEREST, "Dr Alex Morgan", excerpt
        )
        is not None
    )


@pytest.mark.parametrize("position", ["before", "after"])
def test_actual_titled_other_person_still_takes_failure_precedence(position: str) -> None:
    other = "Professor Alice Taylor researches secure systems."
    excerpt = f"{other} {EXCERPT}" if position == "before" else f"{EXCERPT} {other}"
    assert (
        profile_context_excerpt_failure(
            EvidenceClaimType.RESEARCH_INTEREST, "Dr Alex Morgan", excerpt
        )
        is GroundingFailureReason.CONTEXT_CONFLICTING_PERSON
    )


@pytest.mark.parametrize("case", _LINK_FAILURE_CASES, ids=lambda case: case.label)
def test_new_sentence_retains_every_identity_reference_failure(case: _ContextCase) -> None:
    updated = replace(case, claim_updates={**case.claim_updates, "supporting_excerpt": EXCERPT})
    claim, evidence = _context(updated)
    reason = evidence_claim_grounding_failure(claim, _supervisor(), evidence)
    assert reason is not None
    assert reason.value == case.reason


@pytest.mark.parametrize("name", ["Dr Alex Morgan", "Alex Morgan"])
def test_exact_named_sentence_cannot_bypass_the_identity_link(name: str) -> None:
    claim = _claim(
        evidence_id="unlinked-specialisation",
        claim_type=EvidenceClaimType.RESEARCH_INTEREST,
        supporting_excerpt=f"{name} {RELATION}",
        subject_identity_evidence_id=None,
    )
    assert evidence_claim_grounding_failure(claim, _supervisor(), (_claim(),)) is (
        GroundingFailureReason.SUBJECT_NOT_ESTABLISHED
    )


@pytest.mark.parametrize(
    "kind",
    [
        EvidenceClaimType.METHODOLOGY,
        EvidenceClaimType.PUBLICATION,
        EvidenceClaimType.PROJECT,
        EvidenceClaimType.AVAILABILITY,
    ],
)
def test_specialisation_does_not_establish_other_evidence_types(kind: EvidenceClaimType) -> None:
    assert profile_context_excerpt_failure(kind, "Dr Alex Morgan", EXCERPT) is (
        GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING
    )


def test_synthetic_replay_details_and_summary_use_the_same_named_research_rule() -> None:
    capture = RejectedExcerptCapture()
    capture.observe(
        expected_name=_supervisor().full_name,
        claim=_claim(claim_type=EvidenceClaimType.RESEARCH_INTEREST, supporting_excerpt=EXCERPT),
        failure=GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING,
    )
    snapshot = capture.snapshot()
    before = snapshot.model_dump_json()
    detail = replay_details(snapshot)[0]
    assert detail.current_reason is None
    assert detail.prefix_recognized
    assert detail.matcher_family is None
    assert replay_snapshot(snapshot).changed_count == 1
    assert snapshot.model_dump_json() == before
