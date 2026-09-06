# Week 4 step 3d: one live canary with stage diagnostics

## User prompt

> lets proceed to next

Context: step 3c's privacy-safe stage diagnostics passed the full offline suite.
The agreed next boundary is one separately approved live canary invocation to
capture the current failure stage/category, without rerunning until green.

## Bounded interpretation

- Preserve all uncommitted work from steps 3b and 3c.
- Recheck readiness, then run the existing canary exactly once using the same
  public target, synthetic research profile, configured models, strict verification,
  call ceilings, timeout limits, and trace-suppression options.
- Use existing credentials without displaying or editing them. Obtain network
  approval for the single potentially billable run.
- Record safe aggregate counts, stage statuses, failure category, elapsed time,
  and actual pytest result. Leave unknown details and uncalled services explicit.
- No production/test implementation changes, relaxed gates, automatic rerun,
  new target, Mem0 call, persistent shortlist write, outreach, or LangSmith upload.
- Inspect relevant local code read-only if needed to interpret the result. Do not
  claim the new run establishes the exact cause of the earlier uninstrumented run.
- Save the result in the runbook/journal and hand off the next bounded repair.
  No commit or push.
