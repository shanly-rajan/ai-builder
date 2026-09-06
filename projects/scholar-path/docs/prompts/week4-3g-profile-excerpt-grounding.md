# Week 4 step 3g: consistent profile-excerpt grounding

## User prompt

> lets commit what we have done so far first, then proceed to next step

Context: step 3f found retained but ungrounded affiliation and research claims.
The agreed next step is an offline reproduction of normalized excerpt admission
versus raw-text profile-context positioning, not a new live canary or weaker gate.

## Bounded interpretation

- Review and commit the accumulated steps 3b–3f first. Preserve all existing work.
- Add fixed-fixture regressions that reproduce formatting-only grounding failure
  before changing production code. Keep all providers fake and default tests offline.
- If reproduced, make the smallest deterministic matching repair. Permit only
  the case/whitespace equivalence already used for excerpt admission; retain
  original source positions and check every matching occurrence for another person.
- Keep required identity/affiliation/research evidence, source restrictions, typed
  fields, explicit availability, Candidate approval, retry/call limits, and provenance.
- Preserve wrong-person, ambiguous-repeat, unsupported-claim, and invented-affiliation
  rejection. Do not change prompts, models, dependencies, or heading heuristics.
- Record red/green tests and the complete offline quality results. No live call,
  `.env` edit, push, or claim that this reproduces the historical live output.
- Keep this repair separate from the accumulated-work commit and stop after it.
