# Milestone M9 Prompt: Candidate Review Interrupt and Durable Graph Persistence

Implement ScholarPath Milestone M9: Candidate review interrupt and durable graph
persistence.

Replace `candidate_review_gate_stub` with a real LangGraph interrupt.

The interrupt payload must present:

- proposed Supervisor shortlist
- Research Fit Scores
- evidence confidence
- source links
- availability status
- concerns
- independent review outcome

The Candidate may resume with:

1. approve

   - Explicit list of Supervisor IDs to shortlist.

2. reject

   - Supervisor IDs and a reason for each rejection.

3. request_more

   - Revised regions, research interests, constraints, or exclusions.

Graph behaviour:

- approve routes to `save_shortlisted_supervisors`.
- reject records feedback and routes to shortlist reconsideration or search.
- request_more updates Candidate preferences and routes to search planning.
- No Supervisor is saved as shortlisted before approval.
- No outreach draft is generated before approval.
- All loops have a configured maximum iteration count.

Add a LangGraph checkpointer:

- InMemorySaver for unit and graph tests.
- A currently supported SQLite-backed checkpointer for local development.
- Thread IDs must separate Candidate research runs.

Use the current documented interrupt and resume mechanism for the pinned
LangGraph version.

Add tests for:

1. Graph pausing at Candidate review.
2. Persisted state being inspectable while paused.
3. Resuming with approve.
4. Resuming with reject.
5. Resuming with request_more.
6. Separate thread IDs not sharing state.
7. Restarting the application and resuming a persisted local thread.
8. No shortlist save before approval.
9. Invalid Supervisor IDs being rejected.
10. Loop limit reached after repeated request_more actions.
11. Node idempotency when execution resumes.

Do not add Mem0 yet. Candidate feedback remains in graph state for now.
