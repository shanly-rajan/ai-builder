# Week 4 step 3a: one inspectable synthetic evaluation trace

## User prompt and agreed scope

> Ok lets proceed to next level

Context: the Candidate approved five initial expected outcomes (strong fit,
superficial overlap, extraction failure, timeout/fallback, and rejection).
Their offline preflight passed. The next agreed step was a small, evaluation-only
privacy-safe trace change and one synthetic case uploaded to LangSmith.
The user has also instructed: do not commit anything on this thread.

## Bounded implementation

- Trace only the unchanged curated `you-timeout-tavily-fallback` scenario.
- Keep all model, search, extraction, and memory ports fake.
- Show real graph node execution and safe input/output counts and statuses.
- Keep production tracing privacy and normal offline defaults unchanged.
- Test privacy, parent/child linkage, and opt-ins before uploading one experiment.
- Record the actual uploaded result and any verification limits; do not claim a
  live quality benchmark, a reviewed 30-case dataset, or Week 4 completion.
- No commits, live model/search/Mem0 calls, or unrelated product changes.

## Follow-up authorization (2026-09-06)

> lets first commit what we have done thus far

This authorizes committing the completed step after verification, superseding
the earlier no-commit restriction. It does not authorize pushing or beginning
the live-provider step.
