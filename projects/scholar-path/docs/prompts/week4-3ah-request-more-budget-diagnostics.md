# Week 4 step 3ah: request-more call-budget diagnostics

## User prompt

> lets commit and then move to next step

## Established next step and bounded interpretation

First commit the completed reviewed LangSmith baseline and heading-grounding
repair separately, preserving the working files and validating the checkpoints.
Then inspect the outstanding 76/40 request-more fake-call finding. The previous
step explicitly deferred a budget change until its multi-round scope was understood.

- Preserve frozen case recipes, approved labels, manifests, historical reports,
  verification rules, routing, retries, and the 40-call complete-graph-case bar.
- Add typed count-only attribution at the existing fake evaluation target's ten
  port counters. Keep its default returned schema and total unchanged.
- Compare the frozen initial-review and request-more cases offline. Describe the
  delta as two independent cases, not measured phase timings or billed API calls.
- Provide a small diagnostic CLI and tests for arithmetic, failed-attempt counts,
  observer parity, privacy, disabled tracing, and clear budget-failure reporting.
- Use the existing deterministic expected-behavior evaluator. Do not add labels
  or silently divide by rounds to obtain a pass.
- Archive the actual diagnostic result and document conclusions and remaining work.
- No live provider calls, LangSmith upload, environment changes, caching refactor,
  new production behavior, or automatic commit of this new increment.

## Concept

A whole-case budget includes work after Candidate review. Two bounded research
passes can exceed a budget without an infinite loop. Count where the work occurs
before deciding whether to reduce it or explicitly revise the performance target.
