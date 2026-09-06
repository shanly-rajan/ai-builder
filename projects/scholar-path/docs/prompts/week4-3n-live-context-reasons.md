# Week 4 step 3n: one live observation of precise context failures

## User prompt

> ok lets move to next

Context: step 3m added precise reasons to the existing context checks and passed
the full offline suite without changing verification decisions. The next boundary
is one separately approved live canary, not an automatic retry loop or new repair.

## Bounded interpretation

- Inspect the repository; preserve prior uncommitted work. No commit or push.
- Recheck formatting, lint, mypy, and the complete non-live suite.
- Check credential presence without displaying or changing values; request network
  approval for exactly one potentially billable invocation of the existing canary.
- Use the same public target, synthetic Candidate input, configured models, strict
  policy, provider timeouts, nine-logical-call ceiling, and disabled tracing.
- Record actual test status, elapsed time, provider counts, stages, missing gates,
  and retained/grounded/rejected counts with the new fixed reason codes.
- Do not retain raw pages/model responses, excerpts, names, evidence IDs, credentials,
  or exception text in diagnostic output. Keep the public target in the existing
  command only; do not relabel historical failures from a new stochastic result.
- No runtime/test edit, model/prompt tuning, weakened gate, alternate target,
  additional invocation, Mem0, persistent shortlist write, outreach, or trace upload.
- Save results in the runbook, build journal, triage, and README. Recommend the
  smallest evidence-supported next step, but do not implement it in this turn.
