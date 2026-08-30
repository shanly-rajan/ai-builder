# ScholarPath Milestone M13 Prompt

Implement ScholarPath Milestone M13: reliability hardening and submission-ready
release.

Do not add Pinecone, Fireworks, LlamaIndex, or unrelated features.

Perform a final architecture and reliability review.

Add or verify:

1. Explicit timeouts for every external service.
2. Bounded retries.
3. Typed provider errors.
4. Partial-result preservation.
5. Graph recursion and loop limits.
6. Idempotent resume behaviour.
7. Candidate approval before every persistent shortlist write.
8. Candidate approval before any outreach draft.
9. Secret redaction in logs and traces.
10. Candidate-data isolation by user ID and thread ID.
11. Maximum search-query and Supervisor limits.
12. Clear UI messages for recoverable and terminal failures.
13. Reproducible dependency installation.
14. CI running lint, type checks, deterministic tests, and coverage.
15. Failure-injection controls for the demonstration.

Create one fake-provider end-to-end test covering:

Candidate profile
→ SearchPlan
→ You.com failure
→ Tavily fallback
→ Prospective Supervisors
→ evidence verification
→ Research Fit evaluation
→ independent review
→ Candidate rejection
→ Candidate preference capture
→ refined search
→ Candidate approval
→ Shortlisted Supervisors
→ final briefing

Create one optional live canary test that uses a tightly limited number of
provider calls and is skipped by default.

Produce:

- Complete README
- Project overview
- Canonical one-liner
- Agent framework table
- Architecture diagram
- LangGraph node and edge diagram
- Technology decisions
- Dataset and source description
- Prompt and iteration log
- Test strategy
- LangSmith evaluation summary
- Known limitations
- Future roadmap
- Sample output
- Five-minute demonstration script

The demonstration script must visibly show:

1. Candidate enters research preferences.
2. ScholarPath plans searches.
3. A You.com failure is deliberately triggered.
4. LangGraph routes to Tavily.
5. Supervisor evidence and Research Fit Scores appear.
6. The Candidate rejects one Supervisor.
7. The rejection is recorded as a preference.
8. The Candidate approves the final shortlist.
9. A LangSmith trace displays the executed route.

Run the complete non-live suite and provide exact results.
Create a release checklist and suggest the tag v0.1.0.
