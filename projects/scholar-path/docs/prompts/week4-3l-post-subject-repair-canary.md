# Week 4 step 3l: one post-subject-repair live canary

## User prompt

> Lets move to next

Context: step 3k repaired two fixed-fixture subject-binding false positives and
passed the offline suite. The next agreed boundary is one approved live observation
with the same public target and diagnostics, not repeated attempts until success.

## Bounded interpretation

- Preserve all uncommitted work; do not commit or push.
- Recheck formatting, lint, mypy, and the complete non-live suite before execution.
- Check credential presence without displaying/changing values. Request network
  approval for exactly one potentially billable run of the existing canary command.
- Keep the same public profile, synthetic Candidate input, configured providers,
  strict verification, timeouts, nine-logical-call ceiling, and disabled tracing.
- Record actual test result, elapsed time, provider calls, stage statuses, missing
  evidence gates, retained/grounded counts, and final grounding reasons.
- Keep raw model/page content, excerpts, evidence IDs, personal data, credentials,
  and provider exceptions out of the record. Do not infer historical causality.
- No runtime/test modification, model/prompt tuning, credential edit, relaxed gate,
  Mem0 call, persistent graph/shortlist write, outreach, or LangSmith upload.
- Stop after this single execution and document it in the runbook, journal, triage,
  and README. Any next repair is separately scoped offline work.
