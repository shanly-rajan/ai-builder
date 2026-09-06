# Week 4 step 3ag: heading-bound research grounding repair

## User prompt

> lets proceed to the next step

## Established next step and bounded interpretation

Step 3af measured 29/30 passing cases on the frozen, approved thirty-case cohort.
Its documented next step was to repair `draft-evidence-heading-bound-research`
without changing the approved expectation, then compare the same cases offline.

- Reproduce the failure before editing production code.
- Fix only the same-person academic-role sentence that incorrectly replaces the
  profile's subject heading. Preserve other-person and ambiguous boundaries.
- Retain the exact supporting excerpt, source URL, retrieval time, and identity
  evidence link; do not infer new factual evidence.
- Keep fixture inputs, expected labels, reviewed/draft digests, original eleven-case
  defaults, evaluator definitions, and historical reports unchanged.
- Add regression and adversarial tests. Keep current measurements distinct from
  saved historical results, including nonzero CLI failure-path coverage.
- Save a separate after-report and explain the measured delta and remaining debt.
- Leave the separate 76/40 fake-port budget finding, verification policy, routing,
  scoring, prompts, and provider integrations untouched.
- Run formatting, lint, types, and the complete non-live suite. No live provider
  calls, LangSmith upload, environment edits, staging, commit, or push in this step.

## Concept

A sentence describing the profile owner is not a new person heading. Recognizing
that narrow sentence form should preserve the previous heading's ownership, not
establish a new owner or relax the evidence checks.
