"""Recording and scripted fake for the Research Planning Agent boundary."""

from collections.abc import Sequence

from scholarpath.agents import (
    PlanningInput,
    PlanningSearchQueryResponse,
    StructuredSearchPlanResponse,
)
from scholarpath.domain import SearchSourceType

type PlanningOutcome = StructuredSearchPlanResponse | Exception


def make_valid_planning_response(**overrides: object) -> StructuredSearchPlanResponse:
    """Return a realistic response covering all required search-source categories."""
    data: dict[str, object] = {
        "expanded_research_concepts": [
            "enterprise design",
            "AI assurance",
            "sociotechnical transformation",
        ],
        "search_queries": [
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
                query="doctoral supervision enterprise systems responsible AI",
                purpose="Find explicit institutional doctoral supervision information.",
                target_source_types=[SearchSourceType.DOCTORAL_SUPERVISION_INFORMATION],
            ),
        ],
        "rationale": (
            "Cover institutional identity, research alignment, recent work, and explicit "
            "doctoral supervision information without executing any search."
        ),
    }
    return StructuredSearchPlanResponse.model_validate({**data, **overrides})


class FakePlanningModel:
    """Record typed inputs and return deterministic or scripted planning outcomes."""

    def __init__(self, outcomes: Sequence[PlanningOutcome] | None = None) -> None:
        resolved_outcomes = tuple(outcomes or (make_valid_planning_response(),))
        if not resolved_outcomes:
            raise ValueError("FakePlanningModel requires at least one scripted outcome")
        self._outcomes = resolved_outcomes
        self.inputs: list[PlanningInput] = []

    @property
    def call_count(self) -> int:
        """Return the number of model-boundary calls made by the system under test."""
        return len(self.inputs)

    def generate(self, planning_input: PlanningInput) -> StructuredSearchPlanResponse:
        """Record input, then raise or return the next repeatable scripted outcome."""
        self.inputs.append(planning_input)
        outcome_index = min(self.call_count - 1, len(self._outcomes) - 1)
        outcome = self._outcomes[outcome_index]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome
