# Week 4 step 3b: first bounded live-provider canary

## User prompt

> ok lets proceed to next step

Context: the one-case synthetic LangSmith trace was verified and committed as
`4ee99d0`. The agreed next boundary was a separately authorized, tightly limited
real-provider journey. Keep this incremental and avoid major refactors.

## Bounded interpretation

- Inspect and reuse the existing one-profile live canary.
- Correct the canary's false-pass gap: an unavailable independent review must not
  count as successful Nebius integration. Keep production graceful degradation.
- Record aggregate logical call counts and elapsed time even on early failure.
- Use a synthetic Candidate research profile and one publicly documented official
  Supervisor profile; validate URL eligibility without changing domain gates.
- Run once after offline checks and explicit network approval, with existing
  nine-call budget and timeouts. Do not rerun until green or relax evidence rules.
- No Mem0 operations, persistent shortlist writes, outreach, or LangSmith upload.
- Record actual outcomes, untested stages, and unknown tokens/cost honestly.
- Do not describe this manual provider pipeline as a live LangGraph end-to-end
  test or a reviewed golden-dataset baseline. Leave changes for review, uncommitted.
