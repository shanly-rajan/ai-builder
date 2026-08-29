"""Repository contract for the bounded M12.2 live evidence resilience repair."""

from pathlib import Path
from typing import get_args

from scholarpath.agents import (
    EVIDENCE_VERIFICATION_PROMPT_VERSION,
    StructuredEvidenceClaim,
    StructuredEvidenceClaimDraft,
    StructuredEvidenceExtractionResult,
)
from scholarpath.domain import supervisor_names_are_title_equivalent
from scholarpath.evaluation import LOCAL_BASELINE_NAME
from scholarpath.graph import VerificationPolicy
from scholarpath.observability import GRAPH_VERSION

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def test_m12_2_prompt_diagram_readme_architecture_and_journal_are_recorded() -> None:
    prompt = PROJECT_ROOT / "docs/prompts/m12-2-live-evidence-resilience-repair.md"
    diagram = PROJECT_ROOT / "docs/m12-2-live-evidence-resilience-repair.mmd"
    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    architecture = (PROJECT_ROOT / "docs/architecture.md").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs/build-journal.md").read_text(encoding="utf-8")

    assert prompt.is_file()
    assert diagram.is_file()
    assert "M12.2 Live discovery and evidence resilience repair" in prompt.read_text(
        encoding="utf-8"
    )
    assert "flowchart" in diagram.read_text(encoding="utf-8")
    assert "M12.2 live discovery and evidence resilience repair" in readme
    assert "M12.2 live discovery and evidence resilience boundary" in architecture
    assert "## M12.2 Repair: Live discovery and evidence resilience" in journal


def test_m12_2_versions_the_changed_graph_and_evidence_prompt() -> None:
    assert GRAPH_VERSION == "m12.2"
    assert EVIDENCE_VERIFICATION_PROMPT_VERSION == "evidence-verification-v2"
    assert LOCAL_BASELINE_NAME == "scholarpath-m12-2-fake-baseline-2026-08-29"


def test_m12_2_preserves_the_single_alternate_source_retry() -> None:
    policy = VerificationPolicy()

    assert policy.maximum_alternate_source_retries == 1


def test_m12_2_keeps_native_structured_output_and_per_claim_semantics() -> None:
    openai_source = (PROJECT_ROOT / "src/agents/openai_evidence.py").read_text(encoding="utf-8")
    verification_source = (PROJECT_ROOT / "src/agents/evidence_verification.py").read_text(
        encoding="utf-8"
    )

    claims_annotation = StructuredEvidenceExtractionResult.model_fields["claims"].annotation
    assert get_args(claims_annotation)[0] is StructuredEvidenceClaimDraft
    assert issubclass(StructuredEvidenceClaim, StructuredEvidenceClaimDraft)
    assert "EVIDENCE_VERIFICATION_SYSTEM_PROMPT_V2" in openai_source
    assert 'method="json_schema"' in openai_source
    assert "strict=True" in openai_source
    assert "max_retries=0" in openai_source
    assert "json.loads" not in openai_source
    assert "for draft in admitted_drafts" in verification_source


def test_m12_2_name_grounding_ignores_titles_but_not_substantive_name_tokens() -> None:
    assert supervisor_names_are_title_equivalent(
        "Prof. Margaret A Boden",
        "Professor Margaret A Boden",
    )
    assert not supervisor_names_are_title_equivalent(
        "Professor Margaret Boden",
        "Professor Margaret A Boden",
    )
    assert not supervisor_names_are_title_equivalent(
        "Professor Margaret A Boden",
        "Professor Margaret A Borden",
    )
