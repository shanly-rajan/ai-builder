# Week 4 step 3f: one live missing-evidence diagnostic

## User prompt

> lets move to next

Context: step 3e added offline-tested missing-category names, verification standard,
and retained/grounded counts to the existing canary. The agreed next step is one
separately approved live invocation to collect those fields.

## Bounded interpretation

- Preserve all existing uncommitted work; no commit or push.
- Recheck offline quality gates, then run the existing canary exactly once using
  the same public target, synthetic Candidate input, configured models, strict
  verification, nine-call ceiling, per-service timeouts, and trace suppression.
- Use existing credentials without displaying or editing values; request network
  approval for the single potentially billable invocation.
- Record the actual pytest result, elapsed time, attempted calls, fixed stage
  outcomes, verification standard, missing categories, and aggregate claim counts.
- Distinguish observed missing gates from their still-unconfirmed underlying cause.
  Do not retroactively assign this outcome to earlier non-deterministic runs.
- No production/test implementation change, new target, relaxed gate, whole-run
  retry, Mem0 call, persistent graph/shortlist write, outreach, or LangSmith upload.
- Read-only local inspection may clarify the result; any fix is a subsequent
  bounded step. Update the runbook, journal, README, and triage before handing off.
