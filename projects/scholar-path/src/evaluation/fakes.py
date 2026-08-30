"""Small deterministic ports used by ScholarPath evaluation targets.

These fakes live with the evaluation runtime rather than under ``tests`` so the
evaluation scripts work from an installed ScholarPath package.  They never
construct a provider client or perform network access.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from pydantic import HttpUrl

from ..agents import (
    EvidenceExtractionInput,
    IndependentReviewInput,
    IndependentReviewResult,
    PlanningInput,
    PlanningSearchQueryResponse,
    ResearchFitInput,
    StructuredEvidenceClaim,
    StructuredEvidenceExtractionResult,
    StructuredResearchFitComponent,
    StructuredResearchFitResult,
    StructuredSearchPlanResponse,
)
from ..domain import (
    CandidateProfile,
    EvidenceClaimType,
    EvidenceConfidence,
    IndependentReviewDecision,
    ResearchFitRubric,
    SearchResult,
    SearchSourceType,
)
from ..graph.fixtures import WalkingSkeletonFixtures, build_walking_skeleton_fixtures
from ..memory import CandidateMemoryRecord, deduplicate_candidate_memories
from ..tools import ExtractedContent

type PlanningOutcome = StructuredSearchPlanResponse | Exception
type SearchOutcome = tuple[SearchResult, ...] | Exception
type ExtractionOutcome = ExtractedContent | Exception
type EvidenceOutcome = StructuredEvidenceExtractionResult | Exception
type ResearchFitOutcome = StructuredResearchFitResult | Exception
type IndependentReviewOutcome = IndependentReviewResult | Exception

EVALUATION_RETRIEVED_AT = datetime(2026, 8, 29, 9, 0, tzinfo=UTC)


def make_evaluation_planning_response() -> StructuredSearchPlanResponse:
    """Return a source-complete, provider-portable synthetic planning response."""
    return StructuredSearchPlanResponse(
        expanded_research_concepts=[
            "enterprise design",
            "AI assurance",
            "sociotechnical transformation",
        ],
        search_queries=[
            PlanningSearchQueryResponse(
                query="enterprise architecture responsible AI university profile",
                purpose="Find official identity, affiliation, and research interests.",
                target_source_types=[SearchSourceType.OFFICIAL_UNIVERSITY_PROFILE],
            ),
            PlanningSearchQueryResponse(
                query="digital transformation organisational resilience research group",
                purpose="Find aligned departments and research groups.",
                target_source_types=[SearchSourceType.DEPARTMENT_OR_RESEARCH_GROUP],
            ),
            PlanningSearchQueryResponse(
                query="responsible AI governance enterprise architecture publications",
                purpose="Find recent publication evidence for Research Fit.",
                target_source_types=[SearchSourceType.RECENT_PUBLICATION],
            ),
            PlanningSearchQueryResponse(
                query="research degree supervision enterprise systems responsible AI",
                purpose="Find explicit institutional research-degree supervision information.",
                target_source_types=[SearchSourceType.RESEARCH_DEGREE_SUPERVISION_INFORMATION],
            ),
        ],
        rationale=(
            "Cover institutional identity, research alignment, recent work, and explicit "
            "research-degree supervision information without executing a search."
        ),
    )


class StaticPlanningModel:
    """Return scripted structured planning outcomes and record identity-free inputs."""

    def __init__(self, outcomes: Sequence[PlanningOutcome] | None = None) -> None:
        self._outcomes = tuple(
            (make_evaluation_planning_response(),) if outcomes is None else outcomes
        )
        if not self._outcomes:
            raise ValueError("StaticPlanningModel requires at least one outcome")
        self.inputs: list[PlanningInput] = []

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        """Return the next outcome, repeating the last bounded fixture when necessary."""
        self.inputs.append(planning_input)
        outcome = self._outcomes[min(len(self.inputs) - 1, len(self._outcomes) - 1)]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def make_evaluation_search_outcomes(
    fixtures: WalkingSkeletonFixtures | None = None,
) -> dict[str, tuple[SearchResult, ...]]:
    """Map the default plan to eight invented academic profile results."""
    resolved = fixtures or build_walking_skeleton_fixtures()
    queries = tuple(item.query for item in make_evaluation_planning_response().search_queries)
    outcomes: dict[str, list[SearchResult]] = {query: [] for query in queries}
    for index, raw in enumerate(resolved.raw_search_results):
        query = queries[min(index // 2, len(queries) - 1)]
        outcomes[query].append(
            SearchResult(
                url=raw.profile_url,
                title=f"{raw.full_name} | {raw.department} | {raw.institution}",
                description=f"{raw.full_name} is an academic researcher at {raw.institution}.",
                originating_query=query,
            )
        )
    return {query: tuple(items) for query, items in outcomes.items()}


class ScriptedSupervisorSearch:
    """Return normalized synthetic search batches without an HTTP client."""

    def __init__(
        self,
        outcomes: Mapping[str, SearchOutcome] | None = None,
        *,
        scripts: Mapping[str, Sequence[SearchOutcome]] | None = None,
    ) -> None:
        self._outcomes = dict(make_evaluation_search_outcomes() if outcomes is None else outcomes)
        self._scripts = {query: list(values) for query, values in (scripts or {}).items()}
        self.calls: list[str] = []

    def search(self, query: str) -> tuple[SearchResult, ...]:
        """Record an exact query and return its deterministic outcome."""
        self.calls.append(query)
        scripted = self._scripts.get(query)
        outcome = scripted.pop(0) if scripted else self._outcomes.get(query, ())
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def _profile_page_and_response(
    *,
    full_name: str,
    institution: str,
    department: str,
    source_url: str | HttpUrl,
    research_statement: str = (
        "current research interests include enterprise architecture, responsible AI "
        "governance, and resilient digital transformation"
    ),
) -> tuple[ExtractedContent, StructuredEvidenceExtractionResult]:
    """Build matching page content and structured claims for one synthetic profile."""
    identity_excerpt = f"The official profile names {full_name}."
    affiliation_excerpt = f"{full_name} is Professor in {department} at {institution}."
    research_excerpt = f"{full_name}'s {research_statement}."
    methodology_excerpt = (
        f"{full_name}'s methods include design science and comparative case studies."
    )
    publication_excerpt = (
        f"{full_name}'s 2025 publication record examines architecture controls for "
        "responsible AI adoption."
    )
    content = ExtractedContent.model_validate(
        {
            "source_url": source_url,
            "content": "\n".join(
                (
                    identity_excerpt,
                    affiliation_excerpt,
                    research_excerpt,
                    methodology_excerpt,
                    publication_excerpt,
                )
            ),
            "retrieved_at": EVALUATION_RETRIEVED_AT,
        }
    )
    response = StructuredEvidenceExtractionResult(
        claims=[
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.IDENTITY,
                claim=f"The official profile identifies {full_name}.",
                supporting_excerpt=identity_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=full_name,
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.CURRENT_AFFILIATION,
                claim=f"The official profile lists a current role at {institution}.",
                supporting_excerpt=affiliation_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=full_name,
                asserted_institution=institution,
                asserted_department=department,
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.RESEARCH_INTEREST,
                claim=research_statement.capitalize() + ".",
                supporting_excerpt=research_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=full_name,
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.METHODOLOGY,
                claim="The profile states design science and comparative case studies.",
                supporting_excerpt=methodology_excerpt,
                confidence=EvidenceConfidence.MEDIUM,
                directly_supported=True,
                asserted_name=full_name,
            ),
            StructuredEvidenceClaim(
                claim_type=EvidenceClaimType.PUBLICATION,
                claim=(
                    "A 2025 publication examines architecture controls for responsible AI adoption."
                ),
                supporting_excerpt=publication_excerpt,
                confidence=EvidenceConfidence.HIGH,
                directly_supported=True,
                asserted_name=full_name,
                activity_year=2025,
            ),
        ]
    )
    return content, response


def make_evaluation_evidence_outcomes(
    fixtures: WalkingSkeletonFixtures | None = None,
) -> tuple[
    dict[str, ExtractedContent],
    dict[str, StructuredEvidenceExtractionResult],
]:
    """Return internally grounded extraction and model outcomes for the graph cohort."""
    resolved = fixtures or build_walking_skeleton_fixtures()
    content: dict[str, ExtractedContent] = {}
    evidence: dict[str, StructuredEvidenceExtractionResult] = {}
    for raw in resolved.raw_search_results:
        page, response = _profile_page_and_response(
            full_name=raw.full_name,
            institution=raw.institution,
            department=raw.department,
            source_url=raw.profile_url,
        )
        content[str(raw.profile_url)] = page
        evidence[str(raw.profile_url)] = response
    return content, evidence


class ScriptedContentExtraction:
    """Return exact synthetic pages or typed failures for known URLs."""

    def __init__(self, outcomes: Mapping[str, ExtractionOutcome]) -> None:
        self._outcomes = dict(outcomes)
        self.calls: list[str] = []

    def extract(self, source_url: str | HttpUrl) -> ExtractedContent:
        """Record a URL and return its configured content without network access."""
        normalized = str(source_url)
        self.calls.append(normalized)
        outcome = self._outcomes.get(normalized)
        if outcome is None:
            raise AssertionError(f"No evaluation extraction outcome for {normalized}")
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedEvidenceModel:
    """Return source-keyed structured evidence drafts and record bounded inputs."""

    def __init__(self, outcomes: Mapping[str, EvidenceOutcome]) -> None:
        self._outcomes = dict(outcomes)
        self.inputs: list[EvidenceExtractionInput] = []

    def extract(
        self,
        extraction_input: EvidenceExtractionInput,
    ) -> StructuredEvidenceExtractionResult:
        """Return claims configured for the exact retrieved source URL."""
        self.inputs.append(extraction_input)
        outcome = self._outcomes.get(str(extraction_input.source_url))
        if outcome is None:
            raise AssertionError(
                f"No evaluation evidence-model outcome for {extraction_input.source_url}"
            )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


_FIT_SCORES: dict[str, tuple[int, int, int, int]] = {
    "Dr Amara Ndlovu": (38, 19, 15, 15),
    "Professor Elias Hart": (36, 18, 14, 14),
    "Dr Noor van Dijk": (31, 16, 12, 13),
    "Professor Sofia Mensah": (33, 16, 13, 13),
    "Dr Theo Laurent": (30, 14, 12, 12),
    "Professor Lina Okafor": (28, 13, 11, 12),
    "Dr Ravi Solberg": (26, 12, 10, 11),
    "Professor Maya Chen": (24, 11, 9, 10),
}


def _fit_component(
    score: int,
    evidence_id: str | None,
    rationale: str,
    *,
    evidence_gap: str = "No directly supported evidence is available for this component.",
) -> StructuredResearchFitComponent:
    return StructuredResearchFitComponent(
        score=score,
        rationale=rationale,
        supporting_evidence_ids=[] if evidence_id is None else [evidence_id],
        confidence=EvidenceConfidence.LOW if evidence_id is None else EvidenceConfidence.HIGH,
        evidence_gap=evidence_gap if evidence_id is None else None,
    )


def make_evaluation_research_fit_response(
    fit_input: ResearchFitInput,
) -> StructuredResearchFitResult:
    """Build a deterministic evidence-cited response for one Verified Supervisor."""
    evidence_by_type: dict[EvidenceClaimType, str] = {}
    for item in fit_input.evidence:
        evidence_by_type.setdefault(item.claim_type, item.evidence_id)
    research_id = evidence_by_type.get(EvidenceClaimType.RESEARCH_INTEREST)
    methodology_id = None
    if fit_input.methodological_interests:
        methodology_id = evidence_by_type.get(EvidenceClaimType.METHODOLOGY) or research_id
    orientation_id = research_id if fit_input.preferred_research_orientation is not None else None
    publication_id = evidence_by_type.get(EvidenceClaimType.PUBLICATION)
    scores = _FIT_SCORES.get(fit_input.supervisor_name, (20, 10, 8, 8))
    return StructuredResearchFitResult(
        topic_alignment=_fit_component(
            scores[0] if research_id else 0,
            research_id,
            "Direct research evidence supports topic alignment.",
        ),
        methodological_alignment=_fit_component(
            scores[1] if methodology_id else 0,
            methodology_id,
            (
                "Direct methodology evidence supports methodological alignment."
                if methodology_id
                else "The Candidate did not state a methodological preference."
            ),
            evidence_gap="The Candidate did not state a methodological preference.",
        ),
        research_orientation_alignment=_fit_component(
            scores[2] if orientation_id else 0,
            orientation_id,
            (
                "Direct research evidence supports the Candidate's stated orientation."
                if orientation_id
                else "The Candidate did not state a research-orientation preference."
            ),
            evidence_gap="The Candidate did not state a research-orientation preference.",
        ),
        recent_research_alignment=_fit_component(
            scores[3] if publication_id else 0,
            publication_id,
            "A dated publication supports recent research alignment.",
        ),
        practical_constraint_alignment=_fit_component(
            0,
            None,
            "The evidence does not establish region or study-mode compatibility.",
            evidence_gap="No directly supported region or study-mode evidence was retrieved.",
        ),
        overall_rationale=(
            "The component scores reflect only cited, directly supported Supervisor evidence."
        ),
        concerns=["Direct region and study-mode evidence is missing."],
    )


def make_weak_research_fit_response() -> StructuredResearchFitResult:
    """Return a valid zero-point response for a superficial keyword match."""

    def missing(label: str) -> StructuredResearchFitComponent:
        return StructuredResearchFitComponent(
            score=0,
            rationale=f"No direct evidence establishes {label}.",
            supporting_evidence_ids=[],
            confidence=EvidenceConfidence.LOW,
            evidence_gap=f"No directly supported evidence is available for {label}.",
        )

    return StructuredResearchFitResult(
        topic_alignment=missing("topic alignment"),
        methodological_alignment=missing("methodological alignment"),
        research_orientation_alignment=missing("research orientation alignment"),
        recent_research_alignment=missing("recent research alignment"),
        practical_constraint_alignment=missing("practical constraint alignment"),
        overall_rationale="Superficial wording does not establish Research Fit.",
        concerns=["All components require stronger directly supported evidence."],
    )


class ScriptedResearchFitModel:
    """Return per-Supervisor structured fit outcomes or the grounded default."""

    def __init__(
        self,
        outcomes: Mapping[str, Sequence[ResearchFitOutcome]] | None = None,
    ) -> None:
        self._outcomes = {
            supervisor_id: list(values) for supervisor_id, values in (outcomes or {}).items()
        }
        self.inputs: list[ResearchFitInput] = []
        self.rubrics: list[ResearchFitRubric] = []

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        """Record one request and return a scripted or generated response."""
        self.inputs.append(fit_input)
        self.rubrics.append(rubric)
        scripted = self._outcomes.get(fit_input.supervisor_id)
        outcome = scripted.pop(0) if scripted else make_evaluation_research_fit_response(fit_input)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class ScriptedIndependentReviewModel:
    """Accept assessments by default and support deterministic per-Supervisor revisions."""

    def __init__(
        self,
        outcomes: Mapping[str, Sequence[IndependentReviewOutcome]] | None = None,
    ) -> None:
        self._outcomes = {
            supervisor_id: list(values) for supervisor_id, values in (outcomes or {}).items()
        }
        self.inputs: list[IndependentReviewInput] = []

    def review(self, review_input: IndependentReviewInput) -> IndependentReviewResult:
        """Return a scripted review or preserve the initial assessment."""
        self.inputs.append(review_input)
        scripted = self._outcomes.get(review_input.initial_assessment.supervisor_id)
        outcome = (
            scripted.pop(0)
            if scripted
            else IndependentReviewResult(
                decision=IndependentReviewDecision.ACCEPT,
                recommended_score=review_input.initial_assessment.overall_score,
                unsupported_claim_ids=[],
                overlooked_evidence_ids=[],
                confidence=review_input.initial_assessment.confidence,
                critique="The assessment is supported by the supplied evidence.",
            )
        )
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class InMemoryCandidatePreferenceMemory:
    """Candidate-scoped evaluation memory with deterministic deduplication."""

    def __init__(
        self,
        seeded: Mapping[str, Sequence[CandidateMemoryRecord]] | None = None,
    ) -> None:
        self._records = {
            candidate_id: list(deduplicate_candidate_memories(records))
            for candidate_id, records in (seeded or {}).items()
        }
        self.load_calls: list[str] = []
        self.store_calls: list[tuple[str, tuple[CandidateMemoryRecord, ...]]] = []

    def load(self, candidate_id: str) -> tuple[CandidateMemoryRecord, ...]:
        """Load only the requested synthetic Candidate scope."""
        self.load_calls.append(candidate_id)
        return tuple(self._records.get(candidate_id, ()))

    def store(
        self,
        candidate_id: str,
        records: tuple[CandidateMemoryRecord, ...],
    ) -> tuple[CandidateMemoryRecord, ...]:
        """Store unseen records and return only records added by this call."""
        batch = deduplicate_candidate_memories(records)
        self.store_calls.append((candidate_id, batch))
        existing = self._records.setdefault(candidate_id, [])
        existing_ids = {record.memory_id for record in existing}
        stored: list[CandidateMemoryRecord] = []
        for record in batch:
            if record.memory_id not in existing_ids:
                existing.append(record)
                stored.append(record)
                existing_ids.add(record.memory_id)
        return tuple(stored)


class FixedEvaluationClock:
    """Return one aware UTC timestamp for reproducible evaluation results."""

    def __init__(self, timestamp: datetime = EVALUATION_RETRIEVED_AT) -> None:
        self._timestamp = timestamp

    def now(self) -> datetime:
        """Return the configured aware UTC time."""
        return self._timestamp


def synthetic_candidate_profile() -> CandidateProfile:
    """Return the graph fixture's invented, non-personal Candidate profile."""
    return build_walking_skeleton_fixtures().candidate_profile


__all__ = [
    "EVALUATION_RETRIEVED_AT",
    "FixedEvaluationClock",
    "InMemoryCandidatePreferenceMemory",
    "ScriptedContentExtraction",
    "ScriptedEvidenceModel",
    "ScriptedIndependentReviewModel",
    "ScriptedResearchFitModel",
    "ScriptedSupervisorSearch",
    "StaticPlanningModel",
    "make_evaluation_evidence_outcomes",
    "make_evaluation_planning_response",
    "make_evaluation_research_fit_response",
    "make_evaluation_search_outcomes",
    "make_weak_research_fit_response",
    "synthetic_candidate_profile",
]
