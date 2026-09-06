"""Fake-only canary coverage for refined context reasons after strict verification stops."""

import json

import pytest

from scholarpath.agents.evidence_verification import StructuredEvidenceExtractionResult
from scholarpath.domain import EvidenceClaimType, GroundingFailureReason, SourceKind
from scholarpath.tools.content_extraction import ExtractedContent
from tests.fakes import FakeContentExtraction, FakeEvidenceVerificationModel, FakeResearchFitModel
from tests.fixtures import FIXED_EVIDENCE_RETRIEVED_AT, make_candidate_profile
from tests.integration import test_m13_live_canary as canary
from tests.unit.agents.test_official_profile_evidence_context import (
    AFFILIATION_EXCERPT,
    PAGE_NAME,
    PROFILE_URL,
    _affiliation_draft,
    _identity_draft,
    _supervisor,
)
from tests.unit.agents.test_profile_context_diagnostics import (
    CONFLICTING_EXCERPT,
    PRIVATE,
    UNBOUND_EXCERPT,
    _context_draft,
)


@pytest.mark.parametrize(
    ("excerpt", "reason"),
    [
        (CONFLICTING_EXCERPT, GroundingFailureReason.CONTEXT_CONFLICTING_PERSON),
        (UNBOUND_EXCERPT, GroundingFailureReason.CONTEXT_SUBJECT_PATTERN_MISSING),
    ],
)
def test_offline_canary_preserves_precise_context_summary_without_fit_calls(
    excerpt: str,
    reason: GroundingFailureReason,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response = StructuredEvidenceExtractionResult(
        claims=[_identity_draft(), _affiliation_draft(), _context_draft(excerpt)]
    )
    evidence_model = FakeEvidenceVerificationModel({PROFILE_URL: response})
    fit_model = FakeResearchFitModel()
    content = ExtractedContent.model_validate(
        {
            "source_url": PROFILE_URL,
            "content": f"# {PAGE_NAME}\n{AFFILIATION_EXCERPT}\n{excerpt}\n{PRIVATE}",
            "retrieved_at": FIXED_EVIDENCE_RETRIEVED_AT,
        }
    )
    extractor = FakeContentExtraction({PROFILE_URL: content})
    monkeypatch.setattr(
        canary,
        "classify_evidence_source_kind",
        lambda *args, **kwargs: SourceKind.UNIVERSITY_PROFILE,
    )

    with (
        pytest.raises(canary._MissingRequiredEvidenceError),
        canary._summarized_call_budget() as budget,
    ):
        canary._verify_and_evaluate(
            profile=make_candidate_profile(),
            prospective=_supervisor(),
            extracted_content=extractor.extract(PROFILE_URL),
            evidence_model=canary._BudgetedEvidenceModel(evidence_model, budget),
            research_fit_model=canary._BudgetedResearchFitModel(fit_model, budget),
            budget=budget,
        )

    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    grounding = summary["grounding_diagnostics"]
    assert set(grounding) == {"retained_claim_counts", "grounded_claim_counts", "rejection_counts"}
    assert grounding["rejection_counts"]["research_interest"] == {reason.value: 1}
    assert grounding["retained_claim_counts"]["research_interest"] == 1
    assert grounding["grounded_claim_counts"]["research_interest"] == 0
    for claim_type in EvidenceClaimType:
        key = claim_type.value
        rejections = grounding["rejection_counts"][key]
        assert set(rejections) <= {failure.value for failure in GroundingFailureReason}
        assert all(type(count) is int and count > 0 for count in rejections.values())
        assert grounding["retained_claim_counts"][key] == (
            grounding["grounded_claim_counts"][key] + sum(rejections.values())
        )
    assert summary["verification_diagnostics"]["missing_required_evidence"] == [
        "research_interest_or_publication"
    ]
    assert summary["stage_outcomes"]["evidence_verification"]["failure_category"] == (
        "missing_required_evidence"
    )
    assert summary["total_provider_calls"] == evidence_model.call_count == 1
    assert summary["provider_calls"]["openai_evidence"] == 1
    assert summary["provider_calls"]["openai_research_fit"] == fit_model.call_count == 0
    assert extractor.calls == [PROFILE_URL]
    serialized = captured.out + captured.err
    for private_value in (
        PRIVATE,
        PAGE_NAME,
        PROFILE_URL,
        _supervisor().supervisor_id,
        AFFILIATION_EXCERPT,
        excerpt,
        *(draft.claim for draft in response.claims),
    ):
        assert private_value not in serialized
    assert GroundingFailureReason.PROFILE_IDENTITY_CONTEXT_INVALID.value not in serialized
