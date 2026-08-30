"""Repository contract for the M13.13 two-Supervisor MVP adjustment."""

from pathlib import Path

from scholarpath.domain import VerificationEvidenceStandard
from scholarpath.graph import (
    IDENTITY_ONLY_MVP_MINIMUM_VERIFIED_SUPERVISORS,
    GraphFixtureConfig,
)
from scholarpath.ui.app import MVP_IDENTITY_ONLY_BANNER, demo_profile_widget_values

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_active_mvp_composition_uses_two_while_strict_remains_five() -> None:
    mvp = GraphFixtureConfig.for_verification_standard(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )
    strict = GraphFixtureConfig.for_verification_standard(VerificationEvidenceStandard.STRICT)

    assert IDENTITY_ONLY_MVP_MINIMUM_VERIFIED_SUPERVISORS == 2
    assert mvp.discovery_policy.minimum_unique_supervisors == 2
    assert mvp.verification_policy.minimum_verified_supervisors == 2
    assert strict.discovery_policy.minimum_unique_supervisors == 5
    assert strict.verification_policy.minimum_verified_supervisors == 5
    assert "at least 2 Prospective Supervisors" in MVP_IDENTITY_ONLY_BANNER
    assert "at least 2 Verified Supervisors" in MVP_IDENTITY_ONLY_BANNER


def test_demo_profile_leaves_methodological_interests_blank() -> None:
    assert demo_profile_widget_values()["profile_methodological_interests"] == ""


def test_prompt_and_current_docs_record_the_bounded_adjustment() -> None:
    prompt = (
        PROJECT_ROOT / "docs" / "prompts" / "m13-13-two-supervisor-mvp-and-demo-methods.md"
    ).read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")
    terminology = (PROJECT_ROOT / "docs" / "terminology.md").read_text(encoding="utf-8")

    assert "lets lower the verified supervisors to be 2 instead of 3" in prompt
    assert "M13.13" in readme
    assert "M13.13 two-Supervisor MVP and blank demo methodology" in architecture
    assert "| `identity_only_mvp` | Directly grounded identity | 2 |" in terminology
