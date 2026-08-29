"""Recording fake for deterministic offline Research Fit evaluation."""

from collections.abc import Mapping, Sequence

from scholarpath.agents.research_fit import (
    ResearchFitInput,
    StructuredResearchFitComponent,
    StructuredResearchFitResult,
)
from scholarpath.domain import EvidenceClaimType, EvidenceConfidence, ResearchFitRubric

type ResearchFitModelOutcome = StructuredResearchFitResult | Exception

_SCORE_PROFILES: dict[str, tuple[int, int, int, int, int]] = {
    "Dr Amara Ndlovu": (38, 19, 15, 15, 0),
    "Professor Elias Hart": (36, 18, 14, 14, 0),
    "Dr Noor van Dijk": (31, 16, 12, 13, 0),
    "Professor Sofia Mensah": (33, 16, 13, 13, 0),
    "Dr Theo Laurent": (30, 14, 12, 12, 0),
    "Professor Lina Okafor": (28, 13, 11, 12, 0),
    "Dr Ravi Solberg": (26, 12, 10, 11, 0),
    "Professor Maya Chen": (24, 11, 9, 10, 0),
}


def _component(
    score: int,
    evidence_id: str | None,
    rationale: str,
    *,
    evidence_gap: str | None = None,
) -> StructuredResearchFitComponent:
    return StructuredResearchFitComponent(
        score=score,
        rationale=rationale,
        supporting_evidence_ids=[] if evidence_id is None else [evidence_id],
        confidence=(EvidenceConfidence.LOW if evidence_id is None else EvidenceConfidence.HIGH),
        evidence_gap=(
            None
            if evidence_id is not None
            else evidence_gap or "No directly supported evidence was retrieved."
        ),
    )


def _evidence_id(
    fit_input: ResearchFitInput,
    claim_type: EvidenceClaimType,
) -> str:
    """Return one fixture evidence ID for the requested typed claim."""
    try:
        return next(
            evidence.evidence_id
            for evidence in fit_input.evidence
            if evidence.claim_type is claim_type
        )
    except StopIteration as error:
        raise ValueError(f"Research Fit scenario requires {claim_type.value} evidence") from error


def make_strong_research_fit_response(
    fit_input: ResearchFitInput,
) -> StructuredResearchFitResult:
    """Return a strong fit grounded in the supplied Supervisor evidence IDs."""
    research_id = _evidence_id(fit_input, EvidenceClaimType.RESEARCH_INTEREST)
    methodology_id = _evidence_id(fit_input, EvidenceClaimType.METHODOLOGY)
    publication_id = _evidence_id(fit_input, EvidenceClaimType.PUBLICATION)
    return StructuredResearchFitResult(
        topic_alignment=_component(
            36,
            research_id,
            "Direct research-interest evidence supports strong topic alignment.",
        ),
        methodological_alignment=_component(
            17,
            methodology_id,
            "Direct methodology evidence supports strong methodological alignment.",
        ),
        research_orientation_alignment=_component(
            12,
            research_id,
            "Direct research evidence supports the Candidate's applied orientation.",
        ),
        recent_research_alignment=_component(
            13,
            publication_id,
            "Direct publication evidence supports strong recent-research alignment.",
        ),
        practical_constraint_alignment=_component(
            0,
            None,
            "The evidence does not state a preferred region or study mode.",
            evidence_gap="No directly supported region or study-mode evidence was retrieved.",
        ),
        overall_rationale="The cited evidence shows substantial alignment across dimensions.",
        concerns=["Direct region and study-mode evidence is missing."],
    )


def make_weak_research_fit_response() -> StructuredResearchFitResult:
    """Return a weak fit that awards no points where evidence is absent."""

    def missing_component(dimension: str) -> StructuredResearchFitComponent:
        return _component(
            0,
            None,
            f"No direct evidence establishes {dimension}.",
            evidence_gap=f"No directly supported evidence is available for {dimension}.",
        )

    return StructuredResearchFitResult(
        topic_alignment=missing_component("topic alignment"),
        methodological_alignment=missing_component("methodological alignment"),
        research_orientation_alignment=missing_component("research orientation alignment"),
        recent_research_alignment=missing_component("recent research alignment"),
        practical_constraint_alignment=missing_component("practical constraint alignment"),
        overall_rationale="The supplied evidence does not establish Research Fit.",
        concerns=["All five components need stronger supporting evidence."],
    )


def make_superficial_keyword_research_fit_response(
    fit_input: ResearchFitInput,
) -> StructuredResearchFitResult:
    """Return an intentionally invalid result that scores a superficial identity keyword."""
    strong = make_strong_research_fit_response(fit_input)
    return strong.model_copy(
        update={
            "topic_alignment": _component(
                30,
                _evidence_id(fit_input, EvidenceClaimType.IDENTITY),
                "A name string contains a superficial topic keyword.",
            )
        }
    )


def make_graph_research_fit_response(
    fit_input: ResearchFitInput,
) -> StructuredResearchFitResult:
    """Build one evidence-cited response with a stable name-based score profile."""
    evidence_by_type: dict[EvidenceClaimType, str] = {}
    for evidence in fit_input.evidence:
        evidence_by_type.setdefault(evidence.claim_type, evidence.evidence_id)

    research_id = evidence_by_type.get(EvidenceClaimType.RESEARCH_INTEREST)
    publication_id = evidence_by_type.get(EvidenceClaimType.PUBLICATION)
    methodology_id = evidence_by_type.get(EvidenceClaimType.METHODOLOGY) or research_id
    scores = _SCORE_PROFILES.get(fit_input.supervisor_name, (20, 10, 8, 8, 0))
    return StructuredResearchFitResult(
        topic_alignment=_component(
            scores[0] if research_id is not None else 0,
            research_id,
            (
                "The cited research-interest claim supports topic alignment."
                if research_id is not None
                else "No directly supported research-topic evidence was retrieved."
            ),
        ),
        methodological_alignment=_component(
            scores[1] if methodology_id is not None else 0,
            methodology_id,
            (
                "The cited evidence supports methodological or disciplinary alignment."
                if methodology_id is not None
                else "No directly supported methodology or disciplinary evidence was retrieved."
            ),
        ),
        research_orientation_alignment=_component(
            scores[2] if research_id is not None else 0,
            research_id,
            (
                "The cited research claim supports research-orientation alignment."
                if research_id is not None
                else "No directly supported research-orientation evidence was retrieved."
            ),
        ),
        recent_research_alignment=_component(
            scores[3] if publication_id is not None else 0,
            publication_id,
            (
                "The cited publication claim supports recent research alignment."
                if publication_id is not None
                else "No directly supported recent publication or project was retrieved."
            ),
        ),
        practical_constraint_alignment=_component(
            0,
            None,
            "Direct region and study-mode evidence is missing, so no points are awarded.",
            evidence_gap="No directly supported region or study-mode evidence was retrieved.",
        ),
        overall_rationale=(
            "The component scores reflect only cited, directly supported Supervisor evidence."
        ),
        concerns=["Direct region and study-mode evidence is missing."],
    )


class FakeResearchFitModel:
    """Return structured fit responses without a model or network call."""

    def __init__(
        self,
        outcomes: Mapping[str, Sequence[ResearchFitModelOutcome]] | None = None,
    ) -> None:
        self._outcomes = {
            supervisor_id: list(items) for supervisor_id, items in (outcomes or {}).items()
        }
        self.inputs: list[ResearchFitInput] = []
        self.rubrics: list[ResearchFitRubric] = []

    @property
    def call_count(self) -> int:
        """Return the number of structured evaluation calls."""
        return len(self.inputs)

    def evaluate(
        self,
        fit_input: ResearchFitInput,
        rubric: ResearchFitRubric,
    ) -> StructuredResearchFitResult:
        """Record the call, then return a scripted or generated typed response."""
        self.inputs.append(fit_input)
        self.rubrics.append(rubric)
        scripted = self._outcomes.get(fit_input.supervisor_id)
        outcome = scripted.pop(0) if scripted else make_graph_research_fit_response(fit_input)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
