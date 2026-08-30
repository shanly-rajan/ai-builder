# M13.7 prompt: MVP identity-only evidence standard

## Prompt used

> Lets only focus on 1 evidence gate, so that we can carve a MVP out

The accompanying live-run diagnostics showed seven verification records, five directly grounded
identity claims, one directly grounded current-affiliation claim, no directly grounded research
claims, and all seven records remaining partially verified under the strict three-gate standard.

## Bounded interpretation

- Add an explicit, opt-in `identity_only_mvp` verification standard.
- Keep `strict` as the default and retain its identity, affiliation, and research gates.
- Keep directly grounded identity mandatory in both standards.
- Keep the five-Supervisor cohort minimum, one alternate-source retry, availability rules,
  provenance, Candidate approval, and shortlist persistence rules unchanged.
- Surface deferred affiliation and research evidence as concerns, and award no unsupported
  Research Fit points.
