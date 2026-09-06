# Week 4 step 3c: privacy-safe canary stage diagnostics

## User prompt

> Lets proceed to Next

Context: the preceding one-profile live diagnostic failed after four logical calls.
Call counts alone did not confirm verification completion or distinguish evidence
failure from local Research Fit input validation before its model invocation.

## Bounded interpretation

- Preserve all uncommitted step 3b work and its failed live result.
- Add fixed stage statuses and allowlisted failure categories to the existing
  canary summary around evidence extraction, strict verification, Research Fit
  input construction, and Research Fit evaluation.
- Classify known exceptions by type and execution stage, not raw error text.
  Record a missing-evidence outcome only when the verification result lacks a
  Verified Supervisor. Do not infer completion from call counts.
- Keep raw exceptions, validation inputs, personal information, source content,
  evidence IDs, URLs, and credentials out of the diagnostic JSON.
- Exercise successful and failing paths with fixed fixtures and fake ports.
  Preserve provider call ceilings, existing retries, and production behavior.
- No live provider calls, trace uploads, `.env` edits, persistent shortlist writes,
  commits, or pushes. Another live invocation is a separate approval boundary.
- Run formatting, lint, types, and the complete offline regression suite; record
  results without claiming that the historical live failure is now diagnosed or fixed.
