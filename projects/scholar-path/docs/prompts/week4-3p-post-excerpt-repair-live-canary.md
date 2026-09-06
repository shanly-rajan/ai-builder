# Week 4 step 3p: one post-excerpt-repair live canary

## User prompt

> lets move to next

Context: step 3o fixed two offline-reproduced excerpt/name matching defects and
passed the complete non-live suite. The offered next step was one separately
approved bounded live observation, not weaker verification or automatic reruns.

## Bounded interpretation

- Inspect current code, runbook, and existing changes. Preserve uncommitted work.
- Run formatting, lint, mypy, and the complete non-live suite before the live call.
- Check configured credential presence without printing or changing secret values.
- Invoke the existing M13 live canary exactly once with the unchanged public
  Alan Woodward / University of Surrey target and synthetic Candidate input.
- Preserve strict verification, provider/model settings, per-call timeouts,
  nine-logical-call ceiling, disabled SDK retries, and safe count-only reporting.
- Disable tracing; suppress raw tracebacks/captured logs. Do not capture source
  content, model payloads, or Candidate data in new artifacts.
- No Mem0, persisted graph/shortlist write, outreach, commit, push, or runtime fix.
- Record exact outcomes, actual call counts, and unmet gates. A failed or skipped
  live test is not a pass; offline fixes do not prove historical live causality.
- Stop after this single observation. Further investigation or payload capture
  requires a separately bounded step.
