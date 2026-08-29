# Milestone M3 Prompt: OpenAI Research Planning Agent and LangSmith Observability

Implement ScholarPath Milestone M3: OpenAI Research Planning Agent and baseline
LangSmith observability.

Replace only the fixture implementation of `plan_supervisor_searches`.

Create:

- `PlanningModelPort`
- `OpenAIPlanningModelAdapter`
- `ResearchPlanningAgent`
- A versioned planning system prompt
- A structured `SearchPlan` response schema

The Research Planning Agent receives:

- `CandidateProfile`
- remembered Candidate preferences
- target regions
- exclusions

It returns:

- expanded research concepts
- four to eight distinct search queries
- the purpose of each query
- target source types
- concise rationale

Queries should deliberately cover:

- Official university profiles.
- Department or research-group pages.
- Recent publication evidence.
- Explicit doctoral supervision information where available.

Do not allow the planner to search the web itself.
It plans searches. A later tool executes them.

Use the current supported LangChain structured-output mechanism for the pinned
model integration. Do not manually parse JSON from prose.

Add LangSmith configuration:

- `LANGSMITH_TRACING`
- `LANGSMITH_API_KEY`
- `LANGSMITH_PROJECT`
- environment and graph-version tags

Trace the graph run and planning node. Do not include Candidate names, email
addresses, API keys, or full research statements in trace metadata.
LangSmith tracing must be optional and disabled cleanly during tests.

Use dependency injection so graph tests can supply `FakePlanningModel`.

Add tests for:

1. `CandidateProfile` correctly mapped into the planning input.
2. Valid structured `SearchPlan` accepted.
3. Empty query list rejected.
4. Duplicate queries rejected or normalized.
5. Malformed model output handled through one bounded retry.
6. Model failure recorded in `tool_errors` without an unhandled crash.
7. `FakePlanningModel` used in default tests.
8. Live OpenAI smoke test skipped unless explicitly enabled.
9. Trace metadata redacts sensitive Candidate information.
10. Existing deterministic graph routes still pass.

Do not replace any other fixture-backed node.
