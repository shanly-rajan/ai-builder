"""Repository contract for the bounded M13.7 identity-only MVP standard."""

from pathlib import Path

from scholarpath.config import ApplicationSettings
from scholarpath.domain import VerificationEvidenceStandard
from scholarpath.graph import VerificationPolicy

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_mvp_standard_is_explicit_while_strict_safety_defaults_remain() -> None:
    settings_default = ApplicationSettings.model_fields["verification_evidence_standard"].default
    policy = VerificationPolicy()

    assert settings_default is VerificationEvidenceStandard.STRICT
    assert policy.verification_evidence_standard is VerificationEvidenceStandard.STRICT
    assert policy.minimum_verified_supervisors == 5
    assert policy.maximum_alternate_source_retries == 1


def test_environment_docs_and_milestone_records_expose_the_bounded_opt_in() -> None:
    environment_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    terminology = (PROJECT_ROOT / "docs" / "terminology.md").read_text(encoding="utf-8")
    prompt = (
        PROJECT_ROOT / "docs" / "prompts" / "m13-7-mvp-identity-evidence-standard.md"
    ).read_text(encoding="utf-8")

    assert "SCHOLARPATH_VERIFICATION_EVIDENCE_STANDARD=strict" in environment_example
    assert "SCHOLARPATH_VERIFICATION_EVIDENCE_STANDARD=identity_only_mvp" in readme
    assert "Research Fit: not established" in readme
    assert "identity_only_mvp" in terminology
    assert "Lets only focus on 1 evidence gate" in prompt
