# Week 4 submission evidence scorecard

Updated **2026-09-06**, step 3am after checkpoint **`dfd31a7`**. **Submission incomplete.**
This is the current evidence index; older step reports remain historical records.
The supplied Week 4 handout's **own Week 3 agent / LangSmith track** applies to
ScholarPath. Customer-support and social-post examples are not extra product requirements.

## Bottom line

- The reviewed dataset and comparable LangSmith **before and after** experiments exist.
- One same-dataset repair improved correctness from **29/30 to 30/30**, now also
  confirmed in the [uploaded after-experiment](week4-reviewed-langsmith-after.md).
- The [improvement ledger](week4-improvement-ledger.md) consolidates three earlier
  focused comparisons separately from that golden-benchmark repair. Evidence for
  3–4 separate improvements on the frozen benchmark remains incomplete.
- The focused Week 4 report/recording is the next delivery.
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
on the same frozen version, with the after upload and readback now complete.

## Requirement cross-check

| Requirement | Evidence / present status | Remaining work |
| --- | --- | --- |
| Agent and user outcome | ScholarPath helps a Candidate find research-aligned Supervisors with sources and explicit shortlist approval. | Real Candidate ratings are needed to establish the product target of four relevant recommendations out of five within 15 minutes. |
| 3–5 metrics, judges, numeric bars | [Five headline metrics](week4-metrics.md); eleven deterministic checks remain active. Human approval covers expected behaviors, not observed live quality. | No optional LLM judge has been calibrated or used for this cohort. Live tokens/cost remain unknown. |
| 30–50 labeled, versioned cases | [Frozen manifest](evaluation/week4-30case-reviewed-v1.json): 30 cases, 15 happy / 9 edge / 4 known failure / 2 adversarial. [Approval ledger](week4-label-review.md): five individual approvals, 25 explicitly batch-approved. | Synthetic, informed by reported failures; not 30 real-user journeys or independent expert annotations. |
| LangSmith dataset and before experiment | [Authenticated dataset, experiment, and case links](week4-reviewed-langsmith-baseline.md); 30 saved roots, 330 feedback records, 12 matching graph children. Read-only preflight reconfirmed the baseline in step 3al. | Historical experiment remains unchanged; no public sharing. |
| Trace inputs/outputs, children, versions, errors and timing | Privacy-safe case/node summaries and case IDs are recorded. Synthetic fixture recipes supply detailed reproduction locally. | Fake targets have no actual LLM token usage to display. Full live trace/usage evidence is not established by synthetic spans. |
| Baseline and failure clusters | [Before report](evaluation/week4-reviewed-baseline-2026-09-06.json): one correctness failure and a separate runtime overrun. See clusters below. | Do not invent a third cluster just to fill a top-three template; clearly separate historical live observations. |
| 3–4 targeted improvements with measured deltas | [Four repair records](week4-improvement-ledger.md): three earlier focused regression comparisons and one comparable frozen 30-case before/after result. | Evidence for the remaining 2–3 improvements on the frozen benchmark is incomplete. Earlier journal-recorded red results are not separate LangSmith comparisons. Diagnostics and a larger allowance are not additional quality gains. |
| Comparable LangSmith after experiment | [Uploaded after report and links](week4-reviewed-langsmith-after.md): 30/30, complete readback, 30 roots, 330 metric records, 12 graph children; same dataset snapshot. | Complete for this fake-provider cohort. Does not establish live quality or three separate improvements. |
| Mentor: easier failed-case summaries | [Step 1](week4-triage.md#first-delivery-quick-verification) adds case IDs, failed checks, grouped counts and safe guidance. | Implemented and tested; not a measured agent-quality improvement. |
| Mentor: window-related failures | Not reproduced on the inspected macOS environment; no Windows runner evidence. | Obtain the exact failing test/runner log before claiming resolution or making a speculative platform fix. |
| Report, dataset, prompts, trace evidence and short Loom | This index, dataset, [prompt archive](prompts/), [journal](build-journal.md), and before/after trace links are available. | Assemble the focused Week 4 report and record/link the walkthrough. An earlier product demo is not evidence of a Week 4 evaluation recording. |

## Saved local comparison

These earlier local observations are preserved. The separately
[uploaded comparison](week4-reviewed-langsmith-after.md#observed-delta) records
the hosted before/after timing and feedback; do not mix the two timing cohorts.

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

The [improvement ledger](week4-improvement-ledger.md) now records formatting **0/5 →
5/5**, subject binding **17/30 → 30/30**, and specialisation **42/56 → 56/56**,
with source links, current rechecks and explicit historical limitations. These
repairs preceded the frozen baseline; do not label them three additional gains on
it or sum their cohorts. Historical red results are journal observations, not
isolated committed pre-repair snapshots. Their live quality/cost delta was not
measured. The ledger completes evidence consolidation, not the full rubric.

## Minimum remaining execution order

The after-trace gap is closed by step 3al; no further upload is needed to prove
this repair's 29/30 → 30/30 result.

1. **Assemble the report and recording.** The improvement ledger is complete as an
   evidence inventory. Show the dataset, linked before/after cases, cohort limits,
   measured deltas, unresolved 76/40 finding, live limitations, and next hypotheses.
   Obtain a screenshot/export or suitable access for reviewers without making
   private traces public automatically. Record and attach the short Loom.
2. **Resolve the mentor's unidentified failure when evidence arrives.** Request the
   failing command and runner/test log. Current passing macOS tests do not prove a
   Windows-specific issue fixed.

Do not manufacture failures, weaken labels, or introduce caching/refactors simply
to reach an improvement count. Disclose the remaining comparability gap in the report.

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
live providers. The initial scorecard step was documentation-only; step 3al updated
it after one authorized LangSmith after-upload. Step 3am only consolidates public
historical evidence and reruns offline checks. These steps do not change graph
execution, verification gates, fixtures, labels or policies.
