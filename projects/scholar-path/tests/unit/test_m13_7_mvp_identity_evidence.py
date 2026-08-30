"""Focused contracts for the opt-in M13.7 identity-only MVP standard."""

from __future__ import annotations

from pathlib import Path

import pytest

from scholarpath.agents import (
    EvidenceVerificationAgent,
    ResearchFitEvaluationAgent,
    ResearchFitInput,
    StructuredResearchFitResult,
)
from scholarpath.config import ApplicationSettings, load_settings
from scholarpath.domain import (
    EvidenceConfidence,
    ResearchFitAssessment,
    ResearchFitRubric,
    SupervisorVerificationError,
    VerificationEvidenceStandard,
    VerificationStatus,
    VerifiedSupervisor,
    missing_verification_evidence,
    verify_supervisor,
)
from scholarpath.graph import VerificationPolicy, create_initial_state
from scholarpath.ui import controller as ui_controller
from scholarpath.ui.controller import project_graph_state_to_ui
from tests.fakes import FakeEvidenceVerificationModel
from tests.fixtures import (
    make_candidate_profile,
    make_evidence_claims,
    make_prospective_supervisor,
)


class FailIfCalledResearchFitModel:
    """Prove that evidence-limited MVP scoring does not invoke a model."""

    def __init__(self) -> None:
        self.call_count = 0

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        self.call_count += 1
        raise AssertionError(
            "An identity-only Verified Supervisor must use deterministic zero scoring."
        )


def _identity_only_verified_supervisor() -> VerifiedSupervisor:
    prospective = make_prospective_supervisor(1)
    identity = make_evidence_claims(1)[0]
    agent = EvidenceVerificationAgent(
        FakeEvidenceVerificationModel(),
        verification_evidence_standard=(VerificationEvidenceStandard.IDENTITY_ONLY_MVP),
    )
    record = agent.build_verification_record(prospective, (identity,))
    if record.verified_supervisor is None:
        raise AssertionError("Grounded identity must pass the identity-only MVP standard.")
    return record.verified_supervisor


def _component_scores(assessment: ResearchFitAssessment) -> tuple[int, ...]:
    breakdown = assessment.breakdown
    return (
        breakdown.topic_alignment.score,
        breakdown.methodological_alignment.score,
        breakdown.research_orientation_alignment.score,
        breakdown.recent_research_alignment.score,
        breakdown.practical_constraint_alignment.score,
    )


def test_strict_verification_remains_the_default() -> None:
    prospective = make_prospective_supervisor(1)
    identity = make_evidence_claims(1)[0]

    assert VerificationPolicy().verification_evidence_standard is (
        VerificationEvidenceStandard.STRICT
    )
    assert (
        ApplicationSettings.model_fields["verification_evidence_standard"].default
        is VerificationEvidenceStandard.STRICT
    )
    assert missing_verification_evidence((identity,), prospective) == (
        "current_affiliation",
        "research_interest_or_publication",
    )

    with pytest.raises(SupervisorVerificationError, match="missing evidence"):
        verify_supervisor(prospective, (identity,))


def test_identity_only_standard_verifies_grounded_identity_with_visible_concerns() -> None:
    supervisor = _identity_only_verified_supervisor()

    assert supervisor.verification_evidence_standard is (
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )
    assert supervisor.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS
    assert (
        missing_verification_evidence(
            supervisor.evidence,
            supervisor,
            standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
        )
        == ()
    )

    concerns = " ".join(supervisor.verification_concerns).casefold()
    assert "identity" in concerns
    assert "affiliation" in concerns
    assert "research" in concerns

    direct = verify_supervisor(
        make_prospective_supervisor(1),
        (make_evidence_claims(1)[0],),
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    )
    assert direct.verification_status is VerificationStatus.VERIFIED_WITH_CONCERNS
    assert direct.verification_concerns


def test_identity_only_standard_keeps_missing_identity_partial() -> None:
    prospective = make_prospective_supervisor(1)
    standard = VerificationEvidenceStandard.IDENTITY_ONLY_MVP

    assert missing_verification_evidence((), prospective, standard=standard) == ("identity",)

    record = EvidenceVerificationAgent(
        FakeEvidenceVerificationModel(),
        verification_evidence_standard=standard,
    ).build_verification_record(prospective, ())

    assert record.verification_status is VerificationStatus.PARTIALLY_VERIFIED
    assert record.verified_supervisor is None
    assert record.missing_required_evidence == ("identity",)


def test_identity_only_fit_is_deterministic_zero_low_and_skips_the_model() -> None:
    supervisor = _identity_only_verified_supervisor()
    model = FailIfCalledResearchFitModel()

    assessment = ResearchFitEvaluationAgent(model).evaluate(
        make_candidate_profile(),
        supervisor,
    )

    assert model.call_count == 0
    assert assessment.overall_score == 0
    assert _component_scores(assessment) == (0, 0, 0, 0, 0)
    assert assessment.supporting_evidence_ids == ()
    assert assessment.confidence is EvidenceConfidence.LOW
    assert all(
        component.evidence_gap is not None
        for component in (
            assessment.breakdown.topic_alignment,
            assessment.breakdown.methodological_alignment,
            assessment.breakdown.research_orientation_alignment,
            assessment.breakdown.recent_research_alignment,
            assessment.breakdown.practical_constraint_alignment,
        )
    )


def test_identity_only_standard_loads_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "SCHOLARPATH_VERIFICATION_EVIDENCE_STANDARD",
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP.value,
    )

    settings = load_settings()

    assert settings.verification_evidence_standard is (
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )


def test_ui_projection_marks_identity_only_fit_as_evidence_limited() -> None:
    supervisor = _identity_only_verified_supervisor()
    model = FailIfCalledResearchFitModel()
    assessment = ResearchFitEvaluationAgent(model).evaluate(
        make_candidate_profile(),
        supervisor,
    )

    view = ui_controller._verified_supervisor_view(  # noqa: SLF001
        supervisor,
        assessment,
        None,
    )

    assert view.verification_evidence_standard is (VerificationEvidenceStandard.IDENTITY_ONLY_MVP)
    assert view.research_fit_evidence_limited is True
    assert view.research_fit_score == 0


def test_mvp_diagnostics_separate_required_identity_from_deferred_gaps() -> None:
    prospective = make_prospective_supervisor(1)
    identity = make_evidence_claims(1)[0]
    record = EvidenceVerificationAgent(
        FakeEvidenceVerificationModel(),
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP,
    ).build_verification_record(prospective, (identity,))
    restored = record.__class__.model_validate_json(record.model_dump_json())
    assert restored == record
    assert restored.verification_evidence_standard is (
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )
    state = create_initial_state(make_candidate_profile())
    state["discovery_round"] = 1
    state["verification_records"] = [record]
    if record.verified_supervisor is None:
        raise AssertionError("The MVP record must contain an identity-verified Supervisor.")
    state["verified_supervisors"] = [record.verified_supervisor]

    snapshot = project_graph_state_to_ui(
        state,
        checkpoint_token="m13-7-diagnostics",
        review_payload=None,
    )

    diagnostics = snapshot.evidence_verification_diagnostics
    assert diagnostics is not None
    assert diagnostics.verification_evidence_standard is (
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )
    assert diagnostics.completed_verification_record_count == 1
    assert diagnostics.partial_verification_record_count == 0
    assert diagnostics.missing_required_evidence_counts.total == 0
    assert diagnostics.deferred_evidence_gap_counts.identity == 0
    assert diagnostics.deferred_evidence_gap_counts.current_affiliation == 1
    assert diagnostics.deferred_evidence_gap_counts.research_interest_or_publication == 1
