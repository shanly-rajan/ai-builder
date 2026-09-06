# Week 4 step 3ae — batch approval and local reviewed baseline

## Exact user request

> approve case 5 and lets also approve the remaineder of the batches and move to next step

## Context and bounded implementation

Case 5 is `draft-graph-reject-then-approve`: retain the Candidate's rejection and
reason, exclude that Supervisor from this run's revised proposal/approval choices,
and persist only the subsequently approved Supervisors with their final briefing.
Record it as decision 005. Record the remaining 25 expected behaviors as one
explicit batch approval (decision 006), not invented individual inspections.

The documented next step is a separately identified local reviewed-manifest freeze
and fake-only baseline. Pin the existing draft digest and unchanged 30 executable
recipes/expectations; preserve the old draft and eleven-case defaults. Include exact
approval coverage, reviewer role, date, scope, and ledger references. Fail closed on
draft drift and keep approval separate from observed correctness/runtime results.

Run existing offline evaluators with tracing disabled. Save actual local baseline
identity, metric and per-case observations, failures, and runtime measurements.
Retain the known heading-grounding failure and provisional 76/40 fake-call overrun.
Do not weaken labels, implement production repairs, upload data, call live providers,
commit, or push. Add appropriate tests, run all quality checks, and update the journal.
