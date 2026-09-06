# Week 4 step 3v: checkpoint and offline post-fit diagnostics

## User prompt

> good that we have gone past previous blocker, lets commit and then move to next step

## Bounded interpretation

- Review and validate the accumulated steps 3q–3u, then commit that checkpoint
  before starting the next change. Exclude secrets/private artifacts; do not push.
- Extend only the existing live canary's privacy-safe diagnostics and offline tests.
  Do not modify production agents, prompts, provider configuration, or graph gates.
- Distinguish review input, model invocation/return, agent reconciliation, completed
  review requirement, shortlist synthesis, proposal checks, synthetic in-memory
  approval, and final assertions.
- Emit only fixed statuses/failure categories, allowlisted review enums, and counts.
  Never log names, evidence IDs, URLs, critique, model output, or exception text.
- Preserve call ceilings, retries, original exceptions and assertion order. Handle
  pytest's explicit failure outcome without swallowing process interrupts.
- Add fake-based regressions for accepted/revised review, invocation/output/reference
  failure, invalid local input, downstream failures, privacy, and budget limits.
- No live model/search/memory call, private capture/artifact access, tracing, or
  persistent shortlist write. Keep the new step separate from the checkpoint commit.
- Run formatting, lint, type checks, and the full non-live suite; document exact
  results and next action without retroactively diagnosing the earlier live failure.
