# ScholarPath Milestone M12: LangSmith evaluation and regression suite

Implement ScholarPath Milestone M12: LangSmith evaluation and regression suite.

Keep the existing pytest suite. LangSmith evaluations supplement tests and do
not replace them.

Create a ScholarPath evaluation dataset with at least ten curated scenarios:

1. Strong research alignment.
2. Superficial keyword overlap but poor actual fit.
3. Supervisor availability not stated.
4. Conflicting institutional affiliation.
5. Duplicate Supervisor discovered through multiple queries.
6. You.com timeout requiring Tavily fallback.
7. Evidence extraction failure.
8. Independent reviewer disagreement.
9. Candidate rejects highly theoretical research.
10. Candidate approval required before shortlist persistence.

Create target functions for:

- Search planning.
- Evidence verification.
- Research Fit evaluation.
- End-to-end graph execution with fake tools.
- Optional live end-to-end execution.

Create deterministic evaluators for:

- schema validity
- canonical terminology
- evidence ID validity
- source URL presence
- score range and component totals
- no unsupported availability claim
- no admission probability
- correct fallback route
- duplicate Supervisor rate
- human approval enforcement

Create carefully scoped LLM-as-judge evaluators for:

- Research Fit relevance
- explanation usefulness
- evidence-grounded rationale
- shortlist usefulness to the Candidate

Do not use an LLM judge for facts that can be checked deterministically.

Add:

- `scripts/create_eval_dataset.py`
- `scripts/run_evals.py`
- `docs/evaluation-plan.md`
- `docs/evaluation-baseline.md`

Tag traces with:

- application
- environment
- graph version
- prompt version
- model provider
- fallback used
- Candidate review outcome

Do not put personal Candidate information in trace metadata.

Add unit tests for all custom evaluator functions using fixed examples.
Live LangSmith experiments must be opt-in and excluded from the default pytest
suite.

Record a baseline experiment name, date, metric definitions, and observed
failures in `docs/evaluation-baseline.md`.
