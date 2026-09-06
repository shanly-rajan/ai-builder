# Week 4 human label-review ledger

This append-only ledger records explicit human decisions separately from the
unchanged [thirty-case draft snapshot](week4-evaluation-draft.md).

**Progress:** all 30 expected behaviors approved: five individually and 25 through
explicit batch approval. No cases remain pending for expected-behavior approval.
This does not claim individual inspection of every technical field or fixture,
an implementation repair, or a successful live outcome. The subsequent local
reviewed manifest and baseline are documented [separately](week4-reviewed-baseline.md).

## Decision 001 — heading-bound research

- **Review date:** 2026-09-06.
- **Reviewer:** project owner, through an explicit user response in this conversation.
- **Scenario:** `draft-evidence-heading-bound-research` (inventory row 18;
  case 1 in the conversational review batch).
- **Dataset:** `scholarpath-week4-30case-draft-v1`.
- **Version:** `week4-30case-draft-v1`.
- **Draft SHA-256:** `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.
- **Decision:** approved expected behavior, with explicit source-provenance requirements.

### Exact user response

> yes ScholarPath should accept the claim and It should retain the source URL and exact supporting text.

### Approved behavior and boundary

When retrieved text is unambiguously tied to one Supervisor by that person's
profile heading and section context, ScholarPath should accept the stated
research-interest claim without requiring the name in every sentence. Retain
the source URL and exact supporting text, including the heading context needed
to explain that linkage. Do not invent facts or attribute a multi-person page's
research interests to one person without clear source support.

The approval concerns this expected behavior and provenance, not every typed
label field or every fixture variant. It does not independently establish
current affiliation, availability, Research Fit, or permission to shortlist.
The Candidate approval gate and other strict verification requirements remain.

### Implementation and evaluation status

The heading-bound research false negative remains open. The recorded draft check
is still **29/30**, and the 76/40 fake-call budget overrun remains separate.
Human agreement with the expected behavior does not turn either into a pass.

The versioned draft, digest, generated inventory, and CLI JSON remain an unchanged
snapshot from before human review, so they still show `pending` metadata. This
ledger is the current record of scoped human decisions. A later explicitly scoped
step must reconcile completed reviews into a new reviewed manifest before freeze
or upload; neither occurs here.

### Remaining review batch at decision 001

The next four proposed outcomes from the first batch are still pending:
`draft-evidence-confirmed-not-accepting`, `draft-evidence-missing-identity`,
`draft-evidence-availability-without-statement`, and
`draft-graph-reject-then-approve`. No approval is inferred for them.

## Decision 002 — explicitly not accepting supervision

- **Review date:** 2026-09-06.
- **Reviewer:** project owner, through an explicit user response in this conversation.
- **Scenario:** `draft-evidence-confirmed-not-accepting` (inventory row 13;
  case 2 in the conversational review batch).
- **Dataset:** `scholarpath-week4-30case-draft-v1`.
- **Version:** `week4-30case-draft-v1`.
- **Draft SHA-256:** `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.
- **Decision:** approved expected behavior for degree-scoped negative availability.

### Exact user response and context

> yes approved

This response approved the immediately preceding case 2 proposal: identity,
affiliation, and research are verified, but the profile explicitly says,
"I am not accepting new doctoral students."

### Approved behavior and boundary

Keep the verified facts. Record `confirmed_not_accepting` for the explicitly
stated doctoral scope and show `verified_with_concerns`, with the availability
warning clearly visible. Do not generalize this statement to Master's or all
postgraduate supervision, infer permanent unavailability, or automatically reject
or shortlist the Supervisor. Candidate approval remains a separate decision.

This approves the intended behavior, not every fixture/typed field, any live
Supervisor fact, or a production release. The pre-review manifest and digest are
unchanged. The known heading-grounding failure, 29/30 recorded correctness result,
and separate fake-call budget overrun remain open. No implementation, live call,
dataset freeze/upload, or commit is authorized by this review response.

### Remaining review batch at decision 002

`draft-evidence-missing-identity`, `draft-evidence-availability-without-statement`,
and `draft-graph-reject-then-approve` are still pending in the first batch.
The other 25 cases outside this batch are also pending: 28 cases remain in total.

## Decision 003 — missing identity evidence

- **Review date:** 2026-09-06.
- **Reviewer:** project owner, through an explicit user response in this conversation.
- **Scenario:** `draft-evidence-missing-identity` (inventory row 19;
  case 3 in the conversational review batch).
- **Dataset:** `scholarpath-week4-30case-draft-v1`.
- **Version:** `week4-30case-draft-v1`.
- **Draft SHA-256:** `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.
- **Decision:** approved expected behavior for the missing-identity safeguard.

### Exact user response and context

> yes approved

This response approved the immediately preceding case 3 proposal: a page describes
an institution and research interests, but does not establish that this information
belongs to the Supervisor. Retain the record as partially verified, preserve sources,
and do not promote it to Verified Supervisor until identity is grounded.

### Approved behavior and boundary

Institution and research information cannot substitute for a grounded identity.
Preserve the partial record and its source provenance, but do not treat these
claims as directly supported for this person until the source establishes that
linkage. Do not promote the record to Verified Supervisor or infer availability,
Research Fit, or permission to shortlist from the remaining information.

This approval concerns the intended behavior, not every technical field, fixture,
or live Supervisor fact. No new production policy, implementation repair, or
approval of another case is implied. The versioned draft, digest, generated
inventory, and CLI metadata remain the original pre-review snapshot; this ledger
records the scoped decision separately.

The known heading-grounding failure, recorded 29/30 correctness result, and separate
76/40 fake-call budget overrun remain open. No live calls, dataset freeze/upload,
commits, or pushes occur in this step.

### Remaining review batch at decision 003

`draft-evidence-availability-without-statement` and `draft-graph-reject-then-approve`
remain pending in the first batch. The other 25 cases outside this batch are also
pending: 27 cases remain in total.

## Decision 004 — unsupported availability assertion

- **Review date:** 2026-09-06.
- **Reviewer:** project owner, through an explicit user response in this conversation.
- **Scenario:** `draft-evidence-availability-without-statement` (inventory row 23;
  case 4 in the conversational review batch).
- **Dataset:** `scholarpath-week4-30case-draft-v1`.
- **Version:** `week4-30case-draft-v1`.
- **Draft SHA-256:** `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.
- **Decision:** approved expected behavior for unsupported availability.

### Exact user response and context

> approve

This response approved the immediately preceding case 4 proposal: the model says
a Supervisor is accepting students, but the source never states this. Reject the
unsupported assertion and keep availability as `not_stated`, not "not accepting."
Verification may still succeed if identity, affiliation, and research evidence
meet requirements.

### Approved behavior and boundary

A model's confidence or assertion of direct support cannot replace a direct
source statement. Do not accept the unsupported availability claim as evidence
of acceptance or rejection. Keep `not_stated`; missing availability alone must
not block otherwise complete verification. This does not waive other verification
gates, infer availability for another degree, or authorize shortlisting.

This approves the intended behavior, not every typed field, fixture, or live fact.
The original draft manifest, digest, generated inventory, and CLI remain the
pre-review snapshot; this ledger records the scoped decision separately.
The known heading-grounding failure, recorded 29/30 result, and separate 76/40
fake-call overrun remain open. No production changes, live calls, dataset
freeze/upload, commits, or pushes occur in this step.

### Remaining review batch at decision 004

`draft-graph-reject-then-approve` is the only pending case in the first batch.
The other 25 cases outside this batch are also pending: 26 cases remain in total.

## Decision 005 — reject, then approve

- **Review date:** 2026-09-06.
- **Reviewer:** project owner, through an explicit user response in this conversation.
- **Scenario:** `draft-graph-reject-then-approve` (inventory row 28;
  case 5 in the conversational review batch).
- **Dataset/version:** `scholarpath-week4-30case-draft-v1` / `week4-30case-draft-v1`.
- **Draft SHA-256:** `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.
- **Decision:** individual approval of the proposed expected behavior.

### Exact user response

> approve case 5 and lets also approve the remaineder of the batches and move to next step

### Approved behavior and boundary

The Candidate rejects Supervisor A with a reason, then explicitly approves B and C.
Retain A's rejection and reason, exclude A from this run's revised proposal and
approval choices, and save only B and C after approval. Display their final shortlist
and briefing. This is scoped to the Candidate's research run, not global deletion
or rejection for other Candidates.

## Decision 006 — remaining 25 expected behaviors, explicit batch approval

- **Review date:** 2026-09-06.
- **Reviewer:** project owner, through the same explicit user response as decision 005.
- **Review method:** batch approval, not 25 separate individual reviews.
- **Approval scope:** existing proposed expected behaviors; no corrections requested.
- **Dataset/version:** `scholarpath-week4-30case-draft-v1` / `week4-30case-draft-v1`.
- **Draft SHA-256:** `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.

### Exact user response

> approve case 5 and lets also approve the remaineder of the batches and move to next step

### Explicitly covered scenario IDs

- `strong-research-alignment`
- `superficial-keyword-poor-fit`
- `availability-not-stated`
- `conflicting-institutional-affiliation`
- `duplicate-supervisor-multiple-queries`
- `you-timeout-tavily-fallback`
- `evidence-extraction-failure`
- `independent-reviewer-disagreement`
- `candidate-rejects-highly-theoretical`
- `approval-required-before-persistence`
- `planning-source-coverage`
- `draft-evidence-confirmed-accepting`
- `draft-evidence-markdown-identity`
- `draft-evidence-honorific-identity`
- `draft-evidence-line-wrapped-affiliation`
- `draft-evidence-publication-only`
- `draft-evidence-missing-affiliation`
- `draft-evidence-missing-research`
- `draft-evidence-publication-year-not-stated`
- `draft-evidence-off-page-excerpt`
- `draft-graph-approve-one`
- `draft-graph-approve-subset`
- `draft-graph-request-more`
- `draft-graph-review-timeout`
- `draft-graph-review-malformed`

### Next-step boundary

All 30 expected behaviors now have explicit approval provenance. "Move to next step"
is implemented as local reviewed-manifest reconciliation/freeze and a fake-provider
baseline, preserving unchanged inputs and expectations. Original draft records keep
their historical pending metadata; the new wrapper records these decisions.

No individual technical-field inspection is invented. Approval does not change the
known heading-grounding failure or waive the fake-call budget. Uploading to LangSmith,
live provider calls, production repairs, release approval, commits, and pushes remain
separate actions. See the [local freeze and baseline](week4-reviewed-baseline.md).
