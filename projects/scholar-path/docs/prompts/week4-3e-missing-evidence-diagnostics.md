# Week 4 step 3e: expose missing evidence safely

## User prompt

> ok lets proceed to next

Context: step 3d's single live canary completed evidence extraction and stopped
at strict verification with `missing_required_evidence`. It did not reveal which
required category was missing. The next agreed step is offline diagnostic work,
not another paid invocation or a weaker verification policy.

## Bounded interpretation

- Preserve all existing uncommitted work and historical live results.
- Extend only the canary summary using the existing verification record: standard,
  fixed missing-category names, and counts of retained versus grounded claims.
- Allow only `identity`, `current_affiliation`, and `research_interest_or_publication`.
  Emit an unknown-entry count rather than raw text for unrecognized categories.
- Derive grounded counts with the same domain function and full evidence context
  used by verification. Do not equate `directly_supported` alone with grounding.
- Distinguish an unavailable record (`null`) from a record with no missing gates.
  Preserve the summary before failing the existing strict gate.
- Add fixed-fixture tests for missing/complete evidence, contextual grounding,
  privacy, early failures, and unchanged provider-call budgets.
- No model calls, search, Mem0, trace upload, persistent shortlist write, `.env`
  changes, new dependency, production behavior change, commit, or push.
- Record test results without retroactively assigning a missing category or
  cause to the historical live attempts. Further live execution needs approval.
