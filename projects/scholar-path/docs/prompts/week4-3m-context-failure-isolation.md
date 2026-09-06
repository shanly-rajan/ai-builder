# Week 4 step 3m: offline linked-identity/context failure isolation

## User prompt

> lets move to next step

Context: step 3l's single live canary completed extraction but failed strict
verification. Three retained claims reported the coarse linked-identity/context
failure; two reported page-subject mismatch. No exact production repair is proven.

## Bounded interpretation

- Inspect the current repository and preserve all existing uncommitted work.
- Refine only the existing linked-identity/context predicate into fixed reasons
  for its existing reference, source, identity, and excerpt-subject checks.
- Keep the same check order and boolean outcomes. Do not introduce another
  validator, new heading exceptions, weaker gates, or model/prompt changes.
- Keep the legacy coarse enum value readable for historical diagnostics; newly
  evaluated failures use precise codes in the existing count-only summary.
- Add fixed domain, fake extraction, and canary-summary regressions covering
  failure precedence, success, provenance, privacy, and unchanged call counts.
- Run formatting, lint, mypy, and the complete non-live suite. Record exact results,
  assumptions, and remaining debt in the journal, runbook, triage, and README.
- No credential reads/edits, live provider calls, trace uploads, commits, or pushes.
- Do not claim these synthetic fixtures explain the earlier live source text.
- Stop after this diagnostic preparation. A later live observation requires
  separate approval and is not part of this step.
