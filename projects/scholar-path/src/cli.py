"""Command-line demonstration for the ScholarPath graph."""

from collections.abc import Sequence
from typing import Any, cast
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver

from .agents import EvidenceVerificationModelPort, PlanningModelPort, ResearchFitModelPort
from .agents.independent_review import IndependentReviewModelPort
from .config import ProviderConfigurationError, load_settings
from .graph import (
    CandidateReviewResponse,
    ReviewStatus,
    ScholarPathState,
    candidate_review_payload_from_graph_output,
    open_local_sqlite_checkpointer,
    run_scholarpath_graph,
)
from .tools import ContentExtractionPort, SupervisorSearchPort


def main(
    planning_model: PlanningModelPort | None = None,
    supervisor_search: SupervisorSearchPort | None = None,
    tavily_search: SupervisorSearchPort | None = None,
    content_extractor: ContentExtractionPort | None = None,
    evidence_model: EvidenceVerificationModelPort | None = None,
    research_fit_model: ResearchFitModelPort | None = None,
    independent_review_model: IndependentReviewModelPort | None = None,
    alternate_evidence_search: SupervisorSearchPort | None = None,
    *,
    thread_id: str | None = None,
    candidate_review_responses: Sequence[CandidateReviewResponse] = (),
    checkpointer: BaseCheckpointSaver[Any] | None = None,
) -> int:
    """Run until Candidate review, or print the explicitly approved shortlist."""
    resolved_thread_id = thread_id or f"candidate-research-{uuid4().hex}"

    def invoke_graph(
        resolved_checkpointer: BaseCheckpointSaver[Any],
    ) -> ScholarPathState | dict[str, object]:
        return run_scholarpath_graph(
            thread_id=resolved_thread_id,
            candidate_review_responses=candidate_review_responses,
            checkpointer=resolved_checkpointer,
            planning_model=planning_model,
            supervisor_search=supervisor_search,
            tavily_search=tavily_search,
            content_extractor=content_extractor,
            evidence_model=evidence_model,
            research_fit_model=research_fit_model,
            independent_review_model=independent_review_model,
            alternate_evidence_search=alternate_evidence_search,
        )

    try:
        if checkpointer is not None:
            output = invoke_graph(checkpointer)
        else:
            database_path = load_settings().checkpoint_database_path
            with open_local_sqlite_checkpointer(database_path) as local_checkpointer:
                output = invoke_graph(local_checkpointer)
    except ProviderConfigurationError as error:
        print(f"ScholarPath provider configuration error: {error}")
        return 2

    review_payload = candidate_review_payload_from_graph_output(output)
    if review_payload is not None:
        print("ScholarPath paused for Candidate review.")
        print(f"Thread ID: {resolved_thread_id}")
        print(review_payload.model_dump_json(indent=2))
        return 0

    final_state = cast(ScholarPathState, output)
    shortlist = final_state["supervisor_shortlist"]
    if shortlist is None or final_state["review_status"] is not ReviewStatus.COMPLETED:
        print("ScholarPath did not produce a completed Supervisor shortlist.")
        return 1

    scores = {
        assessment.supervisor_id: assessment.overall_score
        for assessment in final_state["research_fit_assessments"]
    }
    scores.update(
        {
            review.supervisor_id: review.effective_score
            for review in final_state["research_fit_review_records"]
        }
    )
    print(f"ScholarPath Shortlist: {len(shortlist.shortlisted_supervisors)} Supervisors")
    for position, supervisor in enumerate(shortlist.shortlisted_supervisors, start=1):
        score = scores[supervisor.supervisor_id]
        print(f"{position}. {supervisor.full_name} — {supervisor.institution} — {score}/100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
