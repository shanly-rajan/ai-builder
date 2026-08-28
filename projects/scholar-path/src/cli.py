"""Command-line demonstration for the deterministic ScholarPath graph."""

from .graph import ReviewStatus, run_scholarpath_graph


def main() -> int:
    """Run the happy-path fixture graph and print five Shortlisted Supervisors."""
    final_state = run_scholarpath_graph()
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
