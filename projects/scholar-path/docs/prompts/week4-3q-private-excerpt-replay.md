# Week 4 step 3q: checkpoint and private excerpt-replay preparation

## User prompt

> lets commit what we did so far and then move to next

## Bounded interpretation

- Verify and commit the existing Week 4 steps 3g–3p work first. Do not push.
- Prepare a default-off, canary-only local diagnostic for the two remaining
  affiliation/research excerpt failure reasons. Do not change matching rules.
- Capture at most one exact excerpt per relevant claim type, expected/asserted
  Supervisor name, clean official source URL/kind, and observed reason.
- Exclude full pages, Candidate inputs, complete model responses, claim prose,
  credentials, unrelated claim types, and successful evidence. Reject suspicious
  or oversized fields; do not truncate/rewrite source excerpts to make them fit.
- Use a typed bounded schema and new private files under the existing ignored
  artifacts directory, with restrictive permissions and no overwrite/symlink use.
- Replay only the excerpt-subject gate using the same deterministic rules. Keep
  derived matcher detail local; default CLI/stdout reports counts only.
- Require an extra explicit capture opt-in in addition to both existing live flags.
  No live execution or real payload capture in this preparation step.
- Test privacy, file handling, observer failure, unchanged evidence/decisions,
  disabled-by-default behavior, and unchanged fake/provider call budgets.
- Run formatting, lint, mypy, complete non-live tests, and document exact results.
- Keep new work separate from the earlier checkpoint. No automatic live rerun,
  weaker verification, new integration, or speculative matcher repair.
