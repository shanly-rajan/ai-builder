"""A recognized wrapper heading must not change otherwise grounded research text."""

import pytest

from scholarpath.agents.evidence_verification import (
    EvidenceGroundingDiagnostics,
    EvidenceVerificationAgent,
    StructuredEvidenceExtractionResult,
)
from scholarpath.domain import (
    AvailabilityStatus,
    EvidenceClaimType,
    GroundingFailureReason,
    SourceKind,
)
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import FakeEvidenceVerificationModel
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT
from tests.unit.agents.test_official_profile_evidence_context import (
    AFFILIATION_EXCERPT,
    PAGE_NAME,
    PROFILE_URL,
    _affiliation_draft,
    _identity_draft,
    _supervisor,
)
from tests.unit.agents.test_profile_subject_binding_regressions import (
    RESEARCH_EXCERPT,
    _assert_diagnostic_equivalence,
    _research_draft,
)


@pytest.mark.parametrize(
    "wrapper",
    ["Research Overview\n", "## Research Overview\n", "Research Overview: "],
)
@pytest.mark.parametrize("body", [RESEARCH_EXCERPT, "My work studies responsible AI."])
def test_research_wrapper_inside_or_outside_excerpt_keeps_same_verification(
    wrapper: str, body: str
) -> None:
    page = f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{wrapper}{body}"
    for excerpt in (body, f"{wrapper}{body}"):
        draft = _research_draft().model_copy(update={"supporting_excerpt": excerpt})
        claims, record, diagnostics = _assert_diagnostic_equivalence(
            [_identity_draft(), _affiliation_draft(), draft], page
        )
        assert record.verified_supervisor is not None, diagnostics.summary()
        assert claims[-1].directly_supported
        assert claims[-1].subject_identity_evidence_id == claims[0].evidence_id
        assert claims[-1].supporting_excerpt == excerpt
        assert diagnostics.summary()["rejection_counts"]["research_interest"] == {}


@pytest.mark.parametrize(
    "excerpt",
    [
        "Research Overview",
        "Research Overview:",
        "Research Overview Jones: Research interests: enterprise systems.",
        "Research Overviewed: Research interests: enterprise systems.",
        "Research Overview Research interests: enterprise systems.",
        "Research Overview:\nenterprise systems are studied.",
        "Research Overview:\nAlice Example researches enterprise systems.",
        "Research Overview:\nResearch Overview:\nResearch interests: enterprise systems.",
    ],
)
def test_heading_does_not_supply_missing_subject_pattern_or_accept_unknown_labels(
    excerpt: str,
) -> None:
    draft = _research_draft().model_copy(update={"supporting_excerpt": excerpt})
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{excerpt}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING.value: 1
    }


@pytest.mark.parametrize(
    "body",
    [
        "Research interests: Professor Alice Example researches enterprise systems.",
        "Research interests of Alice Example: enterprise systems.",
        "Alice Example\nMy work studies enterprise systems.",
    ],
)
def test_other_person_inside_wrapper_still_conflicts(body: str) -> None:
    excerpt = f"## Research Overview\n{body}"
    draft = _research_draft().model_copy(update={"supporting_excerpt": excerpt})
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{excerpt}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.CONTEXT_CONFLICTING_PERSON.value: 1
    }


@pytest.mark.parametrize("repeat", [False, True])
def test_other_person_page_heading_still_blocks_wrapper(repeat: bool) -> None:
    excerpt = f"## Research Overview\n{RESEARCH_EXCERPT}"
    draft = _research_draft().model_copy(update={"supporting_excerpt": excerpt})
    own_occurrence = f"{excerpt}\n" if repeat else ""
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{own_occurrence}"
        f"## Professor Alice Example\n{excerpt}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.PROFILE_SUBJECT_MISMATCH.value: 1
    }


@pytest.mark.parametrize(
    ("source_kind", "source_url", "expected"),
    [
        (SourceKind.DEPARTMENT_PAGE, PROFILE_URL, GroundingFailureReason.PROFILE_SOURCE_INELIGIBLE),
        (
            SourceKind.UNIVERSITY_PROFILE,
            "https://example.edu/people",
            GroundingFailureReason.PROFILE_ROUTE_INELIGIBLE,
        ),
    ],
)
def test_wrapper_does_not_make_source_eligible(
    source_kind: SourceKind, source_url: str, expected: GroundingFailureReason
) -> None:
    excerpt = f"Research Overview:\n{RESEARCH_EXCERPT}"
    draft = _research_draft().model_copy(update={"supporting_excerpt": excerpt})
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{excerpt}",
        source_kind=source_kind,
        source_url=source_url,
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {expected.value: 1}


def test_wrapper_does_not_promote_model_unsupported_research() -> None:
    excerpt = f"Research Overview:\n{RESEARCH_EXCERPT}"
    draft = _research_draft().model_copy(
        update={"supporting_excerpt": excerpt, "directly_supported": False}
    )
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{excerpt}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"]["research_interest"] == {
        GroundingFailureReason.MODEL_NOT_DIRECTLY_SUPPORTED.value: 1
    }


@pytest.mark.parametrize(
    "claim_type", [EvidenceClaimType.METHODOLOGY, EvidenceClaimType.AVAILABILITY]
)
def test_research_wrapper_exception_does_not_apply_to_other_claim_types(
    claim_type: EvidenceClaimType,
) -> None:
    availability = claim_type is EvidenceClaimType.AVAILABILITY
    body = (
        "I am accepting postgraduate research students."
        if availability
        else "Methods: case studies."
    )
    excerpt = f"Research Overview:\n{body}"
    draft = _research_draft().model_copy(
        update={
            "claim_type": claim_type,
            "supporting_excerpt": excerpt,
            "availability_status": AvailabilityStatus.CONFIRMED_ACCEPTING if availability else None,
        }
    )
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{excerpt}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert diagnostics.summary()["rejection_counts"][claim_type.value] == {
        GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING.value: 1
    }


def test_nested_markdown_wrapper_does_not_create_research_support() -> None:
    excerpt = "Research Overview:\n## Research Overview\nMy work studies enterprise systems."
    draft = _research_draft().model_copy(update={"supporting_excerpt": excerpt})
    claims, record, diagnostics = _assert_diagnostic_equivalence(
        [_identity_draft(), _affiliation_draft(), draft],
        f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{excerpt}",
    )
    assert not claims[-1].directly_supported
    assert record.verified_supervisor is None
    assert sum(diagnostics.summary()["rejection_counts"]["research_interest"].values()) == 1


@pytest.mark.parametrize("other_person", [False, True])
def test_combined_repairs_preserve_strict_verification_and_diagnostic_equivalence(
    other_person: bool,
) -> None:
    owner = "Professor Alex James Morgan"
    affiliation_person = "Professor Alex James Taylor" if other_person else owner
    supervisor = _supervisor().model_copy(update={"full_name": owner})
    source_url = "https://profiles.example.edu/alex-james-morgan"
    affiliation_excerpt = (
        f"Current position: {affiliation_person} is in the "
        "School of Management, University of Bradford."
    )
    research_excerpt = "## Research Overview\nMy work studies enterprise systems."
    drafts = [
        _identity_draft(asserted_name=owner),
        _affiliation_draft(supporting_excerpt=affiliation_excerpt).model_copy(
            update={"asserted_name": owner}
        ),
        _research_draft().model_copy(
            update={"asserted_name": owner, "supporting_excerpt": research_excerpt}
        ),
    ]
    content = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": f"# {owner}\n{affiliation_excerpt}\n{research_excerpt}",
            "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
        }
    )
    diagnostics = EvidenceGroundingDiagnostics()
    outputs = []
    for collector in (None, diagnostics):
        model = FakeEvidenceVerificationModel(
            {source_url: StructuredEvidenceExtractionResult(claims=drafts)}
        )
        agent = EvidenceVerificationAgent(model)
        claims = agent.extract_claims(
            supervisor, content, SourceKind.UNIVERSITY_PROFILE, diagnostics=collector
        )
        record = agent.build_verification_record(supervisor, claims)
        assert model.call_count == 1
        assert (record.verified_supervisor is not None) is (not other_person)
        assert record.availability_status is AvailabilityStatus.NOT_STATED
        assert claims[-1].directly_supported
        assert claims[-1].subject_identity_evidence_id == claims[0].evidence_id
        for claim, draft in zip(claims, drafts, strict=True):
            assert claim.supporting_excerpt == draft.supporting_excerpt
            assert claim.claim == draft.claim
            assert claim.asserted_name == draft.asserted_name
            assert claim.asserted_institution == draft.asserted_institution
            assert claim.asserted_department == draft.asserted_department
            assert claim.confidence is draft.confidence
            assert claim.source_kind is SourceKind.UNIVERSITY_PROFILE
            assert str(claim.source_url) == source_url
            assert claim.retrieved_at == FIXED_EVIDENCE_RETRIEVED_AT
            assert claim.supervisor_id == supervisor.supervisor_id
        outputs.append(
            (tuple(claim.model_dump_json() for claim in claims), record.model_dump_json())
        )
    assert outputs[0] == outputs[1]
    summary = diagnostics.summary()
    assert summary["grounded_claim_counts"]["identity"] == 1
    assert summary["grounded_claim_counts"]["current_affiliation"] == (0 if other_person else 1)
    assert summary["grounded_claim_counts"]["research_interest"] == 1
    for kind in EvidenceClaimType:
        key = kind.value
        assert summary["retained_claim_counts"][key] == summary["grounded_claim_counts"][key] + sum(
            summary["rejection_counts"][key].values()
        )
