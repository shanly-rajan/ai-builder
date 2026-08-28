# Milestone M2 prompt: Deterministic LangGraph walking skeleton

Implement ScholarPath Milestone M2: a deterministic LangGraph walking skeleton.

Add LangGraph and only the minimum LangChain core dependency needed.

Create a typed ScholarPathState containing:

- candidate_profile
- candidate_preferences
- search_plan
- raw_search_results
- prospective_supervisors
- verified_supervisors
- research_fit_assessments
- proposed_shortlist
- shortlisted_supervisors
- rejected_supervisors
- candidate_feedback
- tool_errors
- retry_counts
- review_status
- execution_log

Use reducers where concurrent or repeated nodes append to list-valued state.

Build the complete graph using deterministic fixture-backed nodes:

1. load_candidate_preferences
2. plan_supervisor_searches
3. discover_prospective_supervisors
4. enough_supervisors_found
5. fallback_supervisor_search
6. deduplicate_supervisors
7. extract_supervisor_evidence
8. supervisor_evidence_sufficient
9. retry_alternate_evidence_source
10. evaluate_research_fit
11. review_fit_assessments
12. synthesize_supervisor_shortlist
13. candidate_review_gate_stub
14. save_shortlisted_supervisors
15. generate_shortlist_briefing

Use conditional edges for:

- Insufficient Supervisor discovery results.
- Insufficient evidence.
- Candidate approval, rejection, or request_more.

Use strict retry limits so no path can loop indefinitely.

For now:

- All nodes use fixtures.
- The review gate automatically uses a configured fixture decision.
- No model or external API is called.
- Each node appends its canonical name to execution_log.

Add a small CLI demonstration that executes the graph from START to END and
prints the final five Shortlisted Supervisors.

Generate a Mermaid representation and save it under docs/.

Add graph tests for:

1. Normal happy-path node sequence.
2. Insufficient results routing to fallback search.
3. Insufficient evidence routing to alternate evidence retrieval.
4. Candidate approval reaching END.
5. Candidate rejection following the feedback path.
6. request_more returning to search planning.
7. Retry exhaustion stopping cleanly.
8. No graph path using the word candidate for a Supervisor.
9. The final state satisfying SupervisorShortlist validation.

Do not add any live integrations.
