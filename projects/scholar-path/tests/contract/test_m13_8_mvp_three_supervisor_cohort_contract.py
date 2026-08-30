"""Repository contract for the M13.8 three-Supervisor MVP cohort repair."""

from pathlib import Path

from scholarpath.domain import VerificationEvidenceStandard
from scholarpath.graph import MAX_PROPOSED_SHORTLIST_SIZE, VerificationPolicy
from scholarpath.ui.app import MVP_IDENTITY_ONLY_BANNER

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_standard_specific_cohort_and_proposal_capacity_are_distinct() -> None:
    strict = VerificationPolicy(verification_evidence_standard=VerificationEvidenceStandard.STRICT)
    mvp = VerificationPolicy(
        verification_evidence_standard=VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )

    assert strict.minimum_verified_supervisors == 5
    assert mvp.minimum_verified_supervisors == 2
    assert MAX_PROPOSED_SHORTLIST_SIZE == 5
    assert "at least 2 Verified Supervisors" in MVP_IDENTITY_ONLY_BANNER
    assert "may propose up to 5" in MVP_IDENTITY_ONLY_BANNER


def test_milestone_prompt_and_docs_explain_the_bounded_mvp_threshold() -> None:
    prompt = (PROJECT_ROOT / "docs" / "prompts" / "m13-8-mvp-three-supervisor-cohort.md").read_text(
        encoding="utf-8"
    )
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    terminology = (PROJECT_ROOT / "docs" / "terminology.md").read_text(encoding="utf-8")
    diagram = (PROJECT_ROOT / "docs" / "m13-8-mvp-three-supervisor-cohort.mmd").read_text(
        encoding="utf-8"
    )
    environment_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    assert "atleast 3 verified supervisors" in prompt
    assert "strict mode still requires five" in readme
    assert "three-Supervisor MVP verification cohort" in architecture
    assert "Minimum verified cohort" in terminology
    assert "At least 3 identity-verified Supervisors?" in diagram
    assert "minimum cohort of two" in environment_example
