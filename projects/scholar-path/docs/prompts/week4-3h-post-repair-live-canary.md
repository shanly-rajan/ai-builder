# Week 4 step 3h: one post-repair live canary

## User prompt

> lets go to next

Context: step 3g repaired a fixed-fixture excerpt-normalization defect and passed
the offline suite. The next agreed boundary is one separately approved live canary
to observe behavior with that repair, not to keep rerunning until green.

## Bounded interpretation

- Preserve the uncommitted step 3g repair; do not commit or push.
- Recheck offline quality, then run the existing manual canary exactly once using
  the same public profile, synthetic Candidate input, configured providers, strict
  evidence gates, nine-call ceiling, timeouts, and disabled tracing.
- Use existing credentials without exposing or editing values; obtain network
  approval for the single potentially billable invocation.
- Record actual test outcome, safe stage statuses, missing gates, retained/grounded
  counts, attempted provider calls, and elapsed time. Leave unmeasured cost explicit.
- Compare observations with step 3f without asserting that a non-deterministic run
  proves the cause of the historical failure or isolates the repair's effect.
- No additional implementation, relaxed gate, model/prompt change, new target,
  Mem0 call, persistent graph/shortlist write, outreach, or LangSmith upload.
- Read-only inspection may clarify the result. Save the runbook, journal, README,
  and triage result; hand off any further repair as a separate bounded step.
