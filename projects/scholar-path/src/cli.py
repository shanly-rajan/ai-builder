"""Command-line demonstration for the ScholarPath graph."""

from .agents import PlanningModelPort
from .config import ProviderConfigurationError
from .graph import ReviewStatus, run_scholarpath_graph


def main(planning_model: PlanningModelPort | None = None) -> int:
    """Run the graph and print five Shortlisted Supervisors."""
    try:
        if planning_model is None:
            final_state = run_scholarpath_graph()
        else:
            final_state = run_scholarpath_graph(planning_model=planning_model)
    except ProviderConfigurationError as error:
        print(f"ScholarPath provider configuration error: {error}")
        return 2
    shortlist = final_state["supervisor_shortlist"]
    if shortlist is None or final_state["review_status"] is not ReviewStatus.COMPLETED:
        print("ScholarPath did not produce a completed Supervisor shortlist.")
        return 1

    scores = {
        assessment.supervisor_id: assessment.overall_score
        for assessment in final_state["research_fit_assessments"]
    }
    print(f"ScholarPath Shortlist: {len(shortlist.shortlisted_supervisors)} Supervisors")
    for position, supervisor in enumerate(shortlist.shortlisted_supervisors, start=1):
        score = scores[supervisor.supervisor_id]
        print(f"{position}. {supervisor.full_name} — {supervisor.institution} — {score}/100")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
