# Week 4 step 3z — review-ready thirty-case synthetic draft

## User prompt

> lets move to next

## Agreed next boundary

After the explicit checkpoint of steps 3v–3y, resume original Week 4 triage
priority 3: prepare a separately versioned, review-ready 30-case synthetic
evaluation draft. Preserve the existing eleven scenarios and historical baseline;
add nineteen distinct executable variations with expected outcomes and provenance.
Use the planned 15 happy / 9 edge / 4 known-failure / 2 adversarial mix.

The five previously acknowledged starting outcomes are a subset of the eleven,
not extra cases or approval of this entire draft. Mark all detailed labels as
pending human review. Do not claim reviewed ground truth or a frozen baseline.

## Implementation constraints

- Reuse real graph/domain behavior with fake model and tool inputs only.
- Add bounded synthetic target handlers, not new production features or policy changes.
- Keep labels separate from target inputs. Do not derive labels from target results.
- Preserve legitimate failing cases and report them rather than tune fixtures to pass.
- Provide an offline inspection/check command and a human-review inventory.
- No live calls, uploads, LLM judges, credentials/private capture inspection, commits,
  pushes, or baseline overwrites. Human review, freeze, upload, and comparison follow later.

## Observed clarification

The heading-bound research case exposes an existing subject-binding false negative.
Retain its intended grounded-research expectation and report the evaluation failure.
Default tests verify that the harness captures this gap; a green software suite does
not mean every draft evaluation passed. Two initial labels were corrected against
existing explicit policy: negative availability surfaces a concern, and missing
grounded identity prevents the other claims from being directly supported.

## Follow-up checkpoint authorization

> lets commit and move to next

Commit the completed step 3z draft after offline checks and a scoped audit. This
explicit instruction supersedes the earlier no-automatic-commit boundary for this
checkpoint only; it does not authorize a push, live execution, upload, or label approval.

After the checkpoint, begin human label review in conversation with five cases:
`draft-evidence-heading-bound-research`, `draft-evidence-confirmed-not-accepting`,
`draft-evidence-missing-identity`, `draft-evidence-availability-without-statement`,
and `draft-graph-reject-then-approve`. Present their intended outcomes for an explicit
human decision. Keep all labels pending until that decision; do not auto-freeze or
self-approve the dataset.
