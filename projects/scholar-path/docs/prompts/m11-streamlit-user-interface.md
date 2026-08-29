# ScholarPath Milestone M11 Prompt

Implement ScholarPath Milestone M11: Streamlit user interface.

Build a focused single-application Streamlit interface with these stages:

1. Your Doctoral Research Profile
2. Supervisor Search Progress
3. Prospective Supervisors
4. Verified Supervisors
5. Review Supervisors
6. Your Supervisor Shortlist

Use canonical terminology everywhere.

The Candidate profile form must capture:

- proposed research statement
- research topics
- preferred regions
- study mode
- research orientation
- methodological interests
- exclusions

The results interface must show:

- Supervisor name and institution
- verification status
- Research Fit Score
- fit explanation
- evidence confidence
- evidence source links
- availability status
- concerns
- independent review status

The review interface must allow:

- Approve selected Supervisors.
- Reject a Supervisor with a reason.
- Request more research with revised preferences.

Use Streamlit Session State only for interface state and the LangGraph thread ID.
Do not duplicate the complete LangGraph state in Session State.

Use graph streaming or the current supported event mechanism to show meaningful
progress by canonical node name. Do not expose hidden reasoning or raw model
chain-of-thought.

Keep graph construction and business logic outside the Streamlit module.

Add AppTest and unit tests for:

1. Candidate form rendering.
2. Required-field validation.
3. Canonical terminology labels.
4. Starting a research run.
5. Showing progress state.
6. Rendering Verified Supervisor evidence.
7. Approving selected Supervisors.
8. Rejecting with a required reason.
9. Requesting more research.
10. Resuming the correct graph thread.
11. API failure displayed as recoverable rather than a stack trace.
12. No secrets rendered.
13. No Candidate data leaking between sessions.

Add exact README instructions for running the app locally.
