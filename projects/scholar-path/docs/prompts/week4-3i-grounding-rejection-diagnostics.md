# Week 4 step 3i: offline grounding rejection diagnostics

## User prompt

> lets move to next

Context: step 3h's single approved live canary still lacked grounded affiliation
and research evidence. Counts alone cannot explain why. The agreed next step is
offline diagnostics at existing checks, not another live attempt or relaxed gates.

## Bounded interpretation

- Preserve the uncommitted step 3g repair and step 3h results; no commit or push.
- Expose fixed typed failure reasons from the existing domain grounding predicate;
  keep the boolean API delegating to the same checks and preserve their order.
- Add an optional call-local collector for retained claims. Preserve the original
  model support flag in its reason, and count final failures only after existing
  official-profile contextual rescue has been attempted.
- Report only claim-type/reason enums and counts in the manual canary summary.
  Do not collect names, claim text, excerpts, URLs, evidence IDs, keys, raw errors,
  or page content. Distinguish unavailable diagnostics from completed empty output.
- Document that discarded drafts and pre-admission failures are outside these
  retained-claim counters; do not invent reasons for historical live results.
- Test fixed reasons, privacy, accounting, contextual rescue, and identical evidence,
  IDs, verification results, availability, and provider-call counts with diagnostics
  enabled and disabled. Keep all default tests offline.
- Run formatting, lint, type checks, and the complete non-live regression suite.
- No heuristic, verification policy, model/prompt, provider budget, UI, graph route,
  or credential change. No live network call or LangSmith upload.
- Save the result in the journal/runbook/triage/README, then stop. A future single
  live canary requires separate approval.
