# Week 4 step 3ai: measure first review and full scripted interaction separately

## User prompt

> lets commit and move to next step

## Scope clarification

Question: For the next performance target, should ScholarPath track first-result
effort and the full Candidate interaction separately? I recommend both; the existing
40-call whole-case result would remain visible.

User answer: **Track both separately (recommended)**.

## Bounded implementation

- Commit the completed step 3ah after quality checks, without pushing.
- Add a count-only snapshot after each actual initial graph invocation and each
  Candidate resume. Do not infer phases by dividing totals or subtracting independent
  scenarios.
- Report effort to the first Candidate-review pause and total effort through the
  end of each frozen scripted case. A paused case is not a finished shortlist.
- Keep the original 40-call whole-case bar, reports, expected outcomes, fixtures,
  verification rules, and routing unchanged. New numeric limits are not approved;
  show them as unset, not as a passing budget.
- Exercise the twelve frozen fake graph cases with an offline CLI; use existing
  expected-behavior checks, preserve source dataset hashes, and emit only counts
  and controlled scenario/status labels.
- Add regression tests for actual invocation boundaries, counts, output parity,
  privacy, missing observations, and saved-result consistency.
- Save the observed result, explain the metric boundaries, and update the journal.
- Do not introduce caching, live calls, uploads, new dependencies, new production
  policies, or an automatic commit of this increment.

## Concept

First-result effort measures what happens before the Candidate can review.
Interaction effort also counts their subsequent actions. Observe both boundaries
in the same run; do not relabel a larger total as satisfying the old limit.
