"""Repository contracts for M6 Supervisor evidence extraction and verification."""

import inspect
from pathlib import Path
from typing import Annotated, get_args, get_origin, get_type_hints

from pydantic import BaseModel

from scholarpath.agents import (
    EvidenceVerificationAgent,
    EvidenceVerificationModelPort,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
)
from scholarpath.graph import (
    EvidenceExtractionAttempt,
    ScholarPathState,
    VerificationPolicy,
    render_scholarpath_mermaid,
    route_after_evidence_sufficiency,
)
from scholarpath.graph.workflow import DeterministicScholarPathNodes
from scholarpath.tools import ContentExtractionPort, TavilyExtractionAdapter

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"


def test_m6_exposes_typed_provider_and_model_ports() -> None:
    assert getattr(ContentExtractionPort, "_is_protocol", False) is True
    assert getattr(EvidenceVerificationModelPort, "_is_protocol", False) is True
    assert issubclass(TavilyExtractionAdapter, ContentExtractionPort)
    assert inspect.signature(ContentExtractionPort.extract).parameters.keys() == {
        "self",
        "source_url",
    }
    assert inspect.signature(EvidenceVerificationModelPort.extract).parameters.keys() == {
        "self",
        "extraction_input",
    }
    assert inspect.signature(EvidenceVerificationAgent.extract_claims).parameters.keys() == {
        "self",
        "supervisor",
        "extracted_content",
        "source_kind",
    }


def test_m6_uses_official_tavily_extract_without_community_or_private_imports() -> None:
    source = (SOURCE_ROOT / "tools" / "tavily_extraction.py").read_text(encoding="utf-8")

    assert "from langchain_tavily import TavilyExtract" in source
    assert "langchain_community" not in source
    assert "langchain_tavily._" not in source


def test_m6_evidence_model_uses_validated_native_structured_output() -> None:
    adapter_source = (SOURCE_ROOT / "agents" / "openai_evidence.py").read_text(encoding="utf-8")
    result_schema = StructuredEvidenceExtractionResult.model_json_schema()["properties"]
    claim_schema = StructuredEvidenceClaim.model_json_schema()["properties"]

    assert issubclass(StructuredEvidenceExtractionResult, BaseModel)
    assert issubclass(StructuredEvidenceClaim, BaseModel)
    assert "claims" in result_schema
    assert {
        "claim_type",
        "claim",
        "supporting_excerpt",
        "confidence",
        "directly_supported",
        "asserted_name",
        "availability_status",
    } <= claim_schema.keys()
    assert ".with_structured_output(" in adapter_source
    assert "StructuredEvidenceExtractionResult" in adapter_source
    assert 'method="json_schema"' in adapter_source
    assert "json.loads" not in adapter_source


def test_m6_replaces_fixture_evidence_with_injected_extraction_and_agent_boundaries() -> None:
    source = inspect.getsource(DeterministicScholarPathNodes.extract_supervisor_evidence)

    assert "self.config.fixtures.verified_supervisors" not in source
    assert "self.content_extractor.extract(" in source
    assert "self.evidence_agent.extract_claims(" in source
    assert "EvidenceClaim(" not in source


def test_m6_state_retains_verification_outcomes_and_append_only_extraction_attempts() -> None:
    assert {
        "verification_records",
        "evidence_extraction_attempts",
        "alternate_evidence_sources",
    } <= ScholarPathState.__required_keys__

    annotations = get_type_hints(ScholarPathState, include_extras=True)
    attempt_annotation = annotations["evidence_extraction_attempts"]
    assert get_origin(attempt_annotation) is Annotated
    assert len(get_args(attempt_annotation)) == 2
    assert issubclass(EvidenceExtractionAttempt, BaseModel)


def test_m6_uses_a_typed_policy_and_pure_evidence_routing_function() -> None:
    assert issubclass(VerificationPolicy, BaseModel)
    parameters = inspect.signature(route_after_evidence_sufficiency).parameters

    assert "state" not in parameters
    assert set(parameters) == {
        "policy",
        "verification_records",
        "alternate_retry_count",
    }
    assert VerificationPolicy().maximum_alternate_source_retries == 1


def test_m6_live_test_is_guarded_by_explicit_opt_in_and_tavily_key() -> None:
    live_test = (
        PROJECT_ROOT / "tests" / "integration" / "test_tavily_extraction_live.py"
    ).read_text(encoding="utf-8")

    assert "@pytest.mark.live" in live_test
    assert "SCHOLARPATH_RUN_LIVE_TESTS" in live_test
    assert "TAVILY_API_KEY" in live_test
    assert "skipif" in live_test


def test_m6_prompt_environment_diagram_and_journal_are_recorded() -> None:
    env_example = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    journal = (PROJECT_ROOT / "docs" / "build-journal.md").read_text(encoding="utf-8")
    prompt = PROJECT_ROOT / "docs" / "prompts" / "m6-supervisor-evidence-verification.md"
    diagram = PROJECT_ROOT / "docs" / "m6-evidence-verification-graph.mmd"

    assert prompt.is_file()
    assert "## Milestone M6:" in journal
    assert "m6-supervisor-evidence-verification.md" in journal
    for setting in (
        "OPENAI_EVIDENCE_MODEL=gpt-5.4-mini",
        "OPENAI_EVIDENCE_TIMEOUT_SECONDS=60",
        "TAVILY_EXTRACT_PROVIDER_TIMEOUT_SECONDS=20",
        "TAVILY_EXTRACT_REQUEST_TIMEOUT_SECONDS=25",
        "TAVILY_EXTRACT_DEPTH=advanced",
        "TAVILY_EXTRACT_MAX_CONTENT_CHARACTERS=50000",
    ):
        assert setting in env_example
    assert diagram.read_text(encoding="utf-8").strip() == render_scholarpath_mermaid().strip()
