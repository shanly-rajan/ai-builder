# Week 4 submission evidence scorecard

Reviewed **2026-09-06**, after checkpoint **`15cf752`**. **Submission incomplete.**
This is the current evidence index; older step reports remain historical records.
The supplied Week 4 handout's **own Week 3 agent / LangSmith track** applies to
ScholarPath. Customer-support and social-post examples are not extra product requirements.

## Bottom line

- The reviewed dataset and LangSmith **before** experiment exist.
- One same-dataset repair improved correctness from **29/30 to 30/30** locally.
- The **after** experiment, remaining measured-improvement evidence, and Week 4
  report/recording are still outstanding.
- The approved 40/80 policy did not save calls. The original **76/40** failure remains.
- Real provider calls have occurred, but live relevance, token usage, monetary cost,
  and successful repeatable live end-to-end completion are not established.

## Evaluation one-liner

Measure ScholarPath's expected outcomes, evidence integrity, Candidate approval,
target latency, and application-port effort on **30 reviewed synthetic cases**
covering happy, edge, known-failure, and adversarial scenarios, using deterministic
evaluators and human-approved expected behaviors; require **100% applicable
correctness**, fake-target **p95 ≤5 seconds**, and the recorded **2/component,
40/whole-graph-case** call bars, reporting the separately approved **40/80** policy
without replacing the original baseline; compare LangSmith before and after runs
on the same frozen version, with the after upload still pending.

## Requirement cross-check

| Requirement | Evidence / present status | Remaining work |
| --- | --- | --- |
| Agent and user outcome | ScholarPath helps a Candidate find research-aligned Supervisors with sources and explicit shortlist approval. | Real Candidate ratings are needed to establish the product target of four relevant recommendations out of five within 15 minutes. |
| 3–5 metrics, judges, numeric bars | [Five headline metrics](week4-metrics.md); eleven deterministic checks remain active. Human approval covers expected behaviors, not observed live quality. | No optional LLM judge has been calibrated or used for this cohort. Live tokens/cost remain unknown. |
| 30–50 labeled, versioned cases | [Frozen manifest](evaluation/week4-30case-reviewed-v1.json): 30 cases, 15 happy / 9 edge / 4 known failure / 2 adversarial. [Approval ledger](week4-label-review.md): five individual approvals, 25 explicitly batch-approved. | Synthetic, informed by reported failures; not 30 real-user journeys or independent expert annotations. |
| LangSmith dataset and before experiment | [Authenticated dataset, experiment, and case links](week4-reviewed-langsmith-baseline.md); 30 saved roots, 330 feedback records, 12 matching graph children. | Recorded readback evidence, not a new remote inspection in this step. No public sharing or upload occurred here. |
| Trace inputs/outputs, children, versions, errors and timing | Privacy-safe case/node summaries and case IDs are recorded. Synthetic fixture recipes supply detailed reproduction locally. | Fake targets have no actual LLM token usage to display. Full live trace/usage evidence is not established by synthetic spans. |
| Baseline and failure clusters | [Before report](evaluation/week4-reviewed-baseline-2026-09-06.json): one correctness failure and a separate runtime overrun. See clusters below. | Do not invent a third cluster just to fill a top-three template; clearly separate historical live observations. |
| 3–4 targeted improvements with measured deltas | [Heading-grounding repair](week4-heading-grounding-repair.md) has one comparable 30-case before/after result. | Evidence for the remaining 2–3 targeted improvements is incomplete. Diagnostics and a larger allowance are not additional quality gains. |
| Comparable LangSmith after experiment | [Local after report](evaluation/week4-heading-grounding-after-2026-09-06.json): 30/30 with unchanged manifest/evaluators. | Upload once with existing tooling after explicit approval; verify saved results, matching cases and actual comparison links. |
| Mentor: easier failed-case summaries | [Step 1](week4-triage.md#first-delivery-quick-verification) adds case IDs, failed checks, grouped counts and safe guidance. | Implemented and tested; not a measured agent-quality improvement. |
| Mentor: window-related failures | Not reproduced on the inspected macOS environment; no Windows runner evidence. | Obtain the exact failing test/runner log before claiming resolution or making a speculative platform fix. |
| Report, dataset, prompts, trace evidence and short Loom | This index, dataset, [prompt archive](prompts/), [journal](build-journal.md), and before-trace links are available. | Assemble the focused Week 4 report and record/link the walkthrough. An earlier product demo is not evidence of a Week 4 evaluation recording. |

## Comparable measurements, not a new experiment

Dataset: **`scholarpath-week4-30case-reviewed-v1`**; reviewed version:
**`week4-30case-reviewed-v1`**. Both local artifacts share digest
`732ad206d79f30e2f9a3c0efd89c07daf4680216754fa21ce8e4d8f7bda911d5`.
The before name ends `153428Z-e585120b`; the after name ends `162018Z-0cd79546`.
Both were measured on 2026-09-06 with fake providers and graph version `m13`.

| Measure | Saved local before | Saved local after | Interpretation |
| --- | --- | --- | --- |
| Expected behavior / overall correctness | 29/30 (96.67%) | 30/30 (100%) | **+1 case, +3.33 percentage points** |
| Evidence IDs / source URLs / availability integrity | 14/14; 29/29; 29/29 | 14/14; 29/29; 29/29 | No regression on applicable checks |
| Candidate approval enforcement | 12/12 | 12/12 | Unchanged |
| Other deterministic check outcomes | Passing where applicable | Same outcomes | No extra improvement inferred |
| Fake graph target p95 (12 cases) | 0.067619 s | 0.072602 s | +0.004983 s; both below 5 s, not a controlled latency improvement |
| Maximum fake graph port calls | 76/40 | 76/40 | Unchanged overrun; **zero calls saved** |
| Live tokens / money | Unknown | Unknown | Cannot infer from fake calls or runtimes |

These are two saved local runs, not a comparison of local timing with hosted
experiment timing. With 12 graph cases, nearest-rank p95 is the maximum; one run
per revision is not a statistically stable performance comparison.

The [supplemental policy report](evaluation/week4-interaction-policy-2026-09-06.json)
separately records **12 first-review passes**, **3 completed interactions within
budget**, and **9 paused within budget so far**. The request-more case is paused
at 76 calls, not a completed revision-and-approval journey. No eventual approval
cost is inferred. Its CLI still exits 1 because the legacy budget fails.

## Failure analysis and improvement evidence

| Cluster | Frequency and rough effort | Evidence / result |
| --- | --- | --- |
| Heading-context false rejection | 1/30 total; 1/15 evidence cases. The failing case used one fake port call. No billed-cost estimate. | `draft-evidence-heading-bound-research`; [before trace](week4-reviewed-langsmith-baseline.md#recorded-experiment). Step 3ag preserves same-owner role prose context, exact excerpts and source URLs: failed → passed. |
| Whole-case call overrun | 1/12 graph cases; 76 calls across two research passes. | `draft-graph-request-more`; [measured boundaries](week4-interaction-measurements.md). Scope clarified, not optimized. Original finding stays open under its original bar. |

There is no third observed correctness/runtime cluster in the frozen baseline.
Outside it, [step 3w's live canary](week4-live-canary.md#step-3w-instrumented-live-observation-stopped-at-affiliation)
stopped at current affiliation after four logical calls. A prior run reached strict
verification and Research Fit but did not finish. [Step 3y's isolated Nebius check](week4-live-canary.md#step-3y-isolated-live-nebius-review-passed)
passed once with one call. These are different observations, not a same-input
before/after gain or proof of complete live success. No new live check is needed
merely to assemble this scorecard.

Earlier formatting, subject-binding, excerpt-boundary and role-grounding repairs
have focused regression evidence in the [canary history](week4-live-canary.md).
They are useful supporting material, but preceded the frozen 30-case baseline.
Do not retroactively label them as three additional improvements on that baseline.
For each additional improvement, record the lever, hypothesis, exact before/after
implementation, unchanged test inputs/labels, and quality plus effort delta.
Zero or negative deltas are valid findings; a passing test count alone is not a delta.

## Minimum remaining execution order

1. **Close the after-trace gap.** Use the existing
   [reviewed upload command](week4-reviewed-langsmith-baseline.md#reproduce), after
   explicit approval for one LangSmith write. Keep providers fake and the manifest
   unchanged. Verify the saved cases/feedback and record an actual after link.
2. **Complete the improvement ledger.** First reuse the recorded focused before/after
   reproductions to identify defensible comparisons; distinguish their cohorts from
   the 30-case baseline. If comparable evidence is absent, leave the requirement
   incomplete and scope only the smallest reproducible repair. Do not manufacture
   failures, weaken labels, or introduce caching/refactors simply to reach a count.
3. **Assemble the report and recording.** Show the dataset, linked before/after cases,
   measured deltas, unresolved 76/40 finding, live limitations, and next hypotheses.
   Obtain a screenshot/export or suitable access for reviewers without making
   private traces public automatically. Record and attach the short Loom.
4. **Resolve the mentor's unidentified failure when evidence arrives.** Request the
   failing command and runner/test log. Current passing macOS tests do not prove a
   Windows-specific issue fixed.

If another week is available, prioritize reproducible live affiliation grounding
and Candidate-rated usefulness before expanding the feature set. A production
monitoring proposal is to compare expected-outcome failures, provider-error rates,
p95 latency, and measured usage against a versioned baseline in LangSmith, linked
by safe case IDs and prompt/graph versions. Live alert bars require calibration;
fake call limits are not production billing limits. This is a proposal, not deployed
monitoring or a claim of production readiness.

The rubric allows tool-call count as an effort metric. Paid live model calls and
optional LLM judges are not prerequisites merely to meet that metric category.
They would be needed for claims about actual model usage, live quality or cost;
any such experiment needs a separately bounded, explicitly approved scope.

## Quick offline verification

From `projects/scholar-path`:

```bash
venv/bin/pytest -o addopts='' -q tests/contract/test_week4_submission_readiness.py
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/run_reviewed_evals.py --check
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/check_interaction_policy.py
```

Expect the documentation contracts to pass; correctness prints 30/30 and exits 0;
the policy command retains 76/40 and exits 1. These commands do not upload or call
live providers. This step adds documentation and documentation checks only; it
does not change graph execution, verification gates, fixtures, labels or policies.
