# Week 4 evaluation triage

Date: 2026-09-06. Scope: evaluate and improve the existing ScholarPath agent using the
supplied **Week 4 Project Handout (Aug 2026)** and the mentor's **Focus next** feedback.
Steps 1 and 2 are now implemented as separate bounded deliveries. This document is a
gap analysis, not a claim that the Week 4 submission is complete.

The handout is evaluation guidance for the selected own-agent track. Its other tracks,
example agent names, and suggested architectural changes do not expand this task into
building another agent or redesigning ScholarPath.

## Mentor actions and current evidence

The original feedback remains in the [project README](../README.md):

> Focus next on the remaining window-related test failures and make the
> summary of failed evaluation cases easier to follow.

1. **Window-related test failures: not reproduced.** The inspected revision passed
   **1,587 tests**, with **9 live tests deselected** and **91.14% coverage**, on macOS
   with Python **3.14.6**. No Windows runner was used. “Window-related” could refer to
   a platform, an interface window, or a time-window rule; the available feedback does
   not identify a failing test. Preserve the passing behavior and investigate a
   concrete failing test or runner log if one becomes available.
2. **Failed evaluation summaries: actionable repair.** Before this delivery,
   [`scripts/run_evals.py`](../scripts/run_evals.py) printed aggregate metric means
   without identifying failed cases. The local runner discarded evaluator explanations,
   and an unexpected target exception could stop evaluation of later cases. Uploaded
   experiment reporting retained only a total failure count. These are specific,
   reproducible reporting gaps.

The passing pytest result is a regression check. It does not measure live Supervisor
relevance, live provider cost, or the quality of an entire research run.

## Prioritized execution order

Order reflects requirement alignment and value relative to implementation effort.
Later items remain pending; each should be delivered as a separate small change.

| Order | Deliverable | Requirement or mentor alignment | Bounded implementation / verification |
|---|---|---|---|
| **1 — complete** | Readable failure summaries for offline and uploaded evaluations | Mentor: easier failed-case summary. Week 4 phase 3: connect failed cases to metrics and cluster failures. | Extend the existing result records and CLI with case identifiers, failed checks, sanitized failure explanations, and grouped counts; retain remaining cases after a target error. Verify with fixed passing, failing, and error examples. |
| **2 — complete** | Check expected behavior and measure runtime | Week 4 phase 1: outcome-based metrics, numeric pass bars, and at least one quality plus one cost/latency metric. | Explicit outcome labels, per-case target/evaluator time, family median/p95, measured fake port invocations, and optional runtime-budget enforcement. See [metrics and observations](week4-metrics.md). Live tokens/cost remain unmeasured. |
| **3** | Verify one trace, then version and review a 30-case golden dataset | Week 4 phases 1–2: working trace instrumentation and 30–50 labeled happy, edge, known-failure, and adversarial cases. | First verify a synthetic case's bounded inputs/outputs and child runs are visible in LangSmith. Then reuse realistic fixtures and reported failure patterns for distinct cases with scenario type and label provenance. A practical mix is 15 happy, 9 edge, 4 known failures, and 2 adversarial. Human review must confirm expected behavior before calling the labels reviewed ground truth. |
| **4** | Run the frozen baseline and identify its dominant failure clusters | Week 4 phases 2–3: comparable measurements and failures linked to trace evidence. | Reuse dataset upload and experiment commands. Preserve dataset version, experiment name, case IDs, actual trace links, and metric results; rank failures by frequency and measured cost. |
| **5** | Address the dominant failures with 3–4 measured changes | Week 4 phases 3–4: failure frequencies/costs, targeted improvements, and measured delta. | Choose fixes from the baseline clusters, freeze the dataset, and rerun the same metrics after each small improvement. Record gains, regressions, and no-change results honestly. Avoid a model upgrade or architecture rewrite unless a measured failure requires it. |
| **6** | Assemble the Week 4 report and short walkthrough | Submission: framework, dataset, prompts or relevant screenshots, trace evidence, and video explaining what changed, improved, and still fails. | Link real baseline and comparison evidence; summarize metrics, top failures, 3–4 hypotheses/results, remaining work, and monitoring decisions. Record the walkthrough after results exist. |

The first repair improves evaluation visibility. It is not automatically one of the
three to four required agent-quality improvements: those must target observed failures
and have measured effects on the chosen metrics.

## Initial requirement cross-check (before steps 1–2)

| Week 4 requirement | Existing evidence | Remaining gap |
|---|---|---|
| Evaluation one-liner and completed framework | Product purpose and regression goals are described in the [evaluation plan](evaluation-plan.md). | Write the Week 4 measurement one-liner and framework with agreed metric bars, latency/cost limits, dataset version, and actual baseline/comparison references. |
| Three to five outcome, behavior, and cost/latency metrics | Ten deterministic invariant evaluators and four optional qualitative judges already exist in [`src/evaluation/`](../src/evaluation/). | Select headline metrics that predict Candidate value. Add missing expected-behavior and timing observations rather than treating valid schemas alone as task success. |
| Labeled 30–50-case golden dataset | [`scenarios.py`](../src/evaluation/scenarios.py) defines eleven synthetic cases with stable IDs, splits, and typed expectations. | Add distinct cases, scenario-type mix, labeling provenance, and human review. Do not relabel the existing eleven cases as a sufficient Week 4 dataset. |
| Reference expectations actually checked | Score ranges, availability, fallback, and approval expectations feed existing evaluators. | `expected_supervisor_ids` is currently populated but unused by evaluators. Conflict and extraction-failure scenarios need explicit outcome checks so their named behavior is scored. |
| Versioned LangSmith dataset | [`runner.py`](../src/evaluation/runner.py) supports stable example IDs and dataset synchronization. | Freeze the reviewed Week 4 version and retain its actual uploaded dataset reference. |
| Trace visibility and linkage | Existing trace context includes scenario ID, versions, provider, fallback, and review outcome. | The evaluation client hides all inputs and outputs. Verify a safe synthetic projection is visible and case results can be connected to traces. Do not expose raw production content to meet this requirement. |
| Baseline metrics and verified trace | The [historical baseline](evaluation-baseline.md) honestly records **11/11 offline scenarios passed**. | It explicitly records no LangSmith upload, live provider run, or judge run. Actual Week 4 trace evidence and measured baseline results are still required. |
| Failure clusters with frequency, examples, and rough cost | Existing evaluator comments and typed errors provide useful building blocks. | Current delivery adds readable case/cluster reporting. Actual baseline clusters, linked example traces, and costs still require a measured run. |
| Three to four improvements and comparable delta | Earlier milestones document implementation iterations. | Historical changes are not a same-dataset Week 4 comparison. Record new hypotheses and before/after measurements without inventing improvements. |
| Submission report and recording | Project architecture, reliability notes, and evaluation documentation are available. | A focused Week 4 report, dataset handoff, trace links/screenshots, and short recorded walkthrough remain pending. |

The optional LLM judges already exist. They are not required to check facts that code
can validate. If used for Research Fit relevance or usefulness, compare their judgments
with human ratings and record disagreement; an uncalibrated judge score is not human
ground truth.

## First delivery: quick verification

Run these commands from `projects/scholar-path` with the project's environment installed:

```bash
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false \
venv/bin/python scripts/run_evals.py --target all
venv/bin/pytest -o addopts='' -q tests/unit/evaluation/test_failure_reporting.py
```

The first command exercises the existing fake-provider dataset without a network call.
An all-pass dataset should report no failures. The focused tests provide deliberately
failing cases and provider errors so the failure summaries are verified without adding
known-bad examples to the accepted baseline or calling a live provider.

Failed summaries group checks by frequency and list each public case ID, target, check,
score, and a fixed explanation of what to inspect. Uploaded summaries include a LangSmith
run ID when returned by the SDK and resolve cases by example ID, independent of row order.
Target errors, evaluator errors, and missing results are separate categories. No raw error
text, evaluator comments, Candidate content, or target payload is copied into the summary.
Expected fallback, safe rejection, and non-applicable checks do not become failures.

For the complete non-live regression check:

```bash
venv/bin/pytest -m "not live"
```

An uploaded experiment is a separate operation. Use it only when intentionally ready
to write evaluation data to the configured LangSmith workspace:

```bash
SCHOLARPATH_RUN_LANGSMITH_EVALS=true LANGSMITH_TRACING=true \
venv/bin/python scripts/run_evals.py --target all --upload
```

This uploads the current fake-provider experiment; it does not run live model/search
providers or establish live quality/cost. Credentials, the regional endpoint, and any
required workspace ID must already be configured. The baseline and all remaining
Week 4 measurements must be named and dated accurately rather than reusing the historical
Aug 30 baseline identity.

## Completion boundaries

- Preserve the historical eleven-case baseline and its provenance.
- Keep the default test and evaluation path offline.
- Human label review, actual trace evidence, measured before/after deltas, and the
  recording are pending submission evidence, not facts inferred from passing tests.
- No major refactor, additional model provider, vector database, or unrelated product
  feature is needed for this evaluation work.

## Step 2 completion and remaining gaps

The [metric framework](week4-metrics.md) now defines five headline metrics with numeric bars.
`expected_supervisor_ids` is no longer unused: declared IDs, evidence status, conflicts,
partial-result retention, source coverage, revised review scores, and Candidate-review outcomes
are checked by `expected_behavior`. Unknown measurements remain unknown rather than zero.

The eleven cases pass the stronger checks on a newly named provisional dataset,
`scholarpath-week4-regression-v1`. Fresh offline runs receive an actual UTC date and unique
suffix. The historical M12 dataset is protected against overwrite by new labels, and the
historical baseline remains intact. No application graph/UI behavior changed.

**Next: step 3**, not another runtime feature. Verify one privacy-safe synthetic LangSmith
trace, then version and human-review the 30-case golden dataset. Actual trace links, stable
baseline/comparison measurements, 3–4 agent-quality improvements, and submission recording
remain outstanding. Current synthetic labels are not claimed to be human-reviewed ground truth.

## Step 3a completion: synthetic trace visibility

The [one-case trace check](week4-synthetic-trace.md) is now complete: experiment
`scholarpath-week4-m13-01c56dc8` passed **1/1** on 2026-09-06. Authenticated readback
confirmed 24 linked spans, inspectable safe node summaries, simulated timeout/fallback,
and a Candidate-review pause with no persisted shortlist. No live application provider
was used. Changes were initially left uncommitted; the Candidate subsequently
authorized committing this completed step on 2026-09-06.

The Candidate approved the five starting scenario outcomes for review. That is not
equivalent to a reviewed 30–50-case golden dataset or human validation of real Supervisor
facts. Next, a separately authorized, tightly bounded live provider journey can validate
service behavior while golden-dataset curation continues. Live expectations, latency,
tokens/cost, measured before/after improvements, and the recording remain outstanding.

## Step 3b: first real-provider diagnostic

The [bounded one-profile canary](week4-live-canary.md) was run **once** on
2026-09-06: **1 failed in 12.16s**, four logical calls. Planning, You.com discovery,
and Tavily page extraction completed; execution stopped after the evidence-model
attempt and before any Research Fit model call. Verification completion and the
exact failure stage/cause are unconfirmed. Nebius was not reached. This is a manual provider pipeline,
not a live LangGraph run or evidence of live quality. No Mem0, persistent shortlist
write, or LangSmith upload occurred, and tokens/cost remain unknown.

The regression change prevents unavailable Nebius review from being counted as
canary success and reports safe attempted-call counts even on failure. All
**1,836 offline tests passed**, with **91.74% coverage**. This does not turn the
failed live diagnostic into a pass.

The next small diagnostic improvement is an allowlisted evidence-stage failure
outcome, including pre-model Research Fit validation, tested with fakes, so a
separately approved follow-up run can distinguish provider failure, malformed
output, missing required evidence, and local input validation. Do not relax
verification or rerun until green. The reviewed golden dataset and remaining
submission measurements are still outstanding.

## Step 3c: stage diagnostics prepared offline

The [canary stage diagnostics](week4-live-canary.md#step-3c-fixed-stage-outcomes-offline-only)
now distinguish evidence-model errors, missing mandatory evidence, verification
contract failures, and pre-model Research Fit input validation using explicit
stages and fixed categories. Successful stages and unreached stages are recorded
separately; raw errors or inputs never enter the JSON summary. The strict gate,
nine-call ceiling, production agents, and existing retry policies are unchanged.

Nineteen fixed-fixture stage tests exercise the categories without a network call;
the full offline suite passed **1,855 tests**, with **91.78% coverage**. This does not
diagnose or repair the earlier live failure. The next execution boundary is one
separately approved live attempt with the new safe diagnostics; no repeated runs
until green. The dataset, measured improvements, and submission work remain open.

## Step 3d: strict verification is the confirmed stopping gate

The [instrumented live attempt](week4-live-canary.md#step-3d-instrumented-live-result)
ran once after fresh offline checks: **1 failed in 9.35s**, four logical calls.
Evidence extraction completed; verification failed with `missing_required_evidence`.
Research Fit and Nebius were not reached. The exact missing category and underlying
cause are not in the summary, so do not infer them or attribute this outcome to the
earlier uninstrumented attempt.

The canary uses strict verification, not the app's identity-only MVP policy, and
its single-profile gate is unrelated to the app's minimum Supervisor count.
No implementation, gate, target, credential, or provider budget was changed; no
Mem0/shortlist persistence, trace upload, or additional live attempt occurred.

Next bounded offline step: report the verification standard and allowlisted
missing-gate tokens (optionally retained/grounded counts), using the existing
grounding function and fixed-fixture privacy/validation tests. Do not weaken the
verification policy or treat this diagnostic as a passing live baseline.

## Step 3e: missing-category detail prepared offline

The [verification summary](week4-live-canary.md#step-3e-missing-evidence-and-grounding-counts-offline-only)
now includes the record's verification standard, allowlisted missing-gate names,
and retained/grounded counts. It uses the existing full-context domain grounder,
not a model explanation or the direct-support flag alone. Unknown labels are
counted without exposing text, and absence of a record remains null.

Only canary diagnostics, fake-driven tests, and documentation change. There is no
weaker gate, additional provider call, production behavior change, or commit.
Another live attempt needs separate approval; the previous attempt's exact missing
category is still unknown. Golden dataset, quality/cost comparison, and submission
work remain open.

## Step 3f: affiliation and research grounding are the observed gaps

The [single live diagnostic](week4-live-canary.md#step-3f-live-missing-evidence-result)
returned **1 failed in 11.31s**, four logical provider calls. Evidence extraction
completed. Strict verification found grounded identity, but no grounded current
affiliation or research-interest/publication evidence. It retained 1 affiliation,
8 research-interest, and 9 publication claims; none qualified as grounded.
Research Fit and Nebius were not reached. The specific support/grounding rejection
reason is not captured, and previous runs remain unclassified at that detail.

Next bounded offline step: reproduce the current-affiliation gate with fixed
official-profile layouts and fake model output; examine support flags, asserted
institution/department text, and same-page identity context. Repair only a reproduced
defect while preserving negative cases. Research-interest/publication grounding is
the next known gap, not an excuse to lower verification standards or rerun until green.

First reproduction: excerpt admission normalizes case/whitespace, but contextual
page positioning uses raw text matching. Test this formatting-only discrepancy
in the existing official-profile context suite. It is a code-level hypothesis,
not the established cause of this live result.

No production/test code changed in this live-execution step. The pre-run suite
passed **1,872 tests**, **82 subtests**, and **91.78% coverage**; nine live tests
were deselected. There was no Mem0 call, persisted shortlist, trace upload, or commit.
Golden dataset, measured improvement, and submission gaps remain open.
