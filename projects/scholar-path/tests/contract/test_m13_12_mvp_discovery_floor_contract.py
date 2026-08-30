"""Repository contract for the M13.12 MVP discovery-floor alignment."""

from pathlib import Path

from scholarpath.domain import VerificationEvidenceStandard
from scholarpath.graph import DiscoveryPolicy, GraphFixtureConfig
from scholarpath.ui.app import MVP_IDENTITY_ONLY_BANNER

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_implicit_standard_policies_align_but_strict_default_remains_five() -> None:
    strict = GraphFixtureConfig.for_verification_standard(VerificationEvidenceStandard.STRICT)
    mvp = GraphFixtureConfig.for_verification_standard(
        VerificationEvidenceStandard.IDENTITY_ONLY_MVP
    )

    assert (
        strict.discovery_policy.minimum_unique_supervisors
        == strict.verification_policy.minimum_verified_supervisors
        == 5
    )
    assert (
        mvp.discovery_policy.minimum_unique_supervisors
        == mvp.verification_policy.minimum_verified_supervisors
        == 2
    )
    assert DiscoveryPolicy().minimum_unique_supervisors == 5
    assert "at least 2 Prospective Supervisors" in MVP_IDENTITY_ONLY_BANNER
    assert "at least 2 Verified Supervisors" in MVP_IDENTITY_ONLY_BANNER


def test_prompt_and_docs_record_the_bounded_repair() -> None:
    prompt = (
        PROJECT_ROOT / "docs" / "prompts" / "m13-12-mvp-discovery-floor-alignment.md"
    ).read_text(encoding="utf-8")
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs" / "architecture.md").read_text(encoding="utf-8")

    assert "Not seeing the prospective supervisors proceed" in prompt
    assert "M13.12" in readme
    assert "M13.12 MVP discovery-floor alignment" in architecture
