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

## Step 3g: excerpt normalization repaired with fixed fixtures

Accumulated steps 3b–3f were committed as `268600b` before this repair; no push.
Five offline cases reproduced inconsistent formatting treatment between excerpt
admission and profile-context positioning. The scoped repair normalizes matching
while retaining original offsets and checking all equivalent occurrences. Another
negative case now keeps unsupported claims out of identity-context construction.

Twenty new cases cover this path and rejection controls; **123 profile-context
tests passed**. Strict identity, current affiliation, and research gates remain
unchanged. No live request was made, and the historical live cause is still unknown.

Next execution boundary, only after offline gates pass: one separately approved
canary using the unchanged target and safe diagnostics. Do not add another broad
diagnostic layer or weaken gates preemptively. Research-grounding causes, live
Research Fit/Nebius coverage, the reviewed dataset, and measured quality remain open.

## Step 3h: live verification still stops after the formatting repair

The [single post-repair canary](week4-live-canary.md#step-3h-post-repair-live-result)
returned **1 failed in 11.11s**, four logical calls. Extraction completed; strict
verification still lacked grounded current affiliation and research-interest/publication
evidence. It retained identity 1, affiliation 1, research interest 1, publication 2,
and project 1; only identity was grounded. Research Fit and Nebius were not called.

The prior local defect remains reproduced and repaired, but this new stochastic
execution did not pass the live gate or identify the remaining rejection condition.
Do not infer causality from the changed claim counts or keep adjusting heuristics.

Next bounded offline diagnostic: fixed aggregate reason codes from the existing
claim-support and context decisions, with fake/privacy tests. Do not log raw content,
duplicate validation rules, broaden verification, or run another live attempt as
part of that preparation. Golden dataset, quality/cost, and submission gaps remain open.

Pre-run checks passed **1,892 tests**, **84 subtests**, and **91.78% coverage**; nine
live tests were deselected. No new source/test changes, commit, or push in step 3h.

## Step 3i: offline grounding reasons without changing verification

The [canary diagnostic](week4-live-canary.md#step-3i-retained-claim-grounding-diagnostics-offline)
now reports fixed final grounding reasons by claim type, preserving the original
model support flag and counting contextual rescue as success. It reuses existing
grounding checks; no parallel validator, relaxed gate, heuristic, or provider change.

Counters cover retained claims only, after admission/deduplication and before
conflict merging. They cannot explain discarded drafts or retroactively identify
step 3h's cause. Empty completed output and unavailable diagnostics remain distinct.
No raw data is stored in the collector or added to trace metadata.

Added 57 offline reason/privacy/equivalence/call-budget tests. Full suite:
**1,949 passed, 9 deselected, 85 subtests in 24.87s**, **91.86% coverage**;
formatting, lint, and mypy pass. No live call,
credential edit, commit, or push. Next is a separately approved single live canary
to observe these reasons; quality, golden dataset, cost, and submission gaps remain.

## Step 3j: live reasons locate the remaining subject/context gates

The [single instrumented live canary](week4-live-canary.md#step-3j-live-grounding-reason-result)
returned **1 failed in 10.33s**, four logical calls. Extraction completed; strict
verification still lacked grounded affiliation and research/publication evidence.
The retained affiliation failed `profile_identity_context_invalid` once. One
research-interest claim and six publications failed `profile_subject_mismatch`.
Identity passed. Research Fit and Nebius were not called.

These reasons establish which existing checks rejected retained claims, not that
the checks are defective or the sources lack facts. No raw text was retained;
discarded drafts and historical failure causes remain unobserved.

Next: one bounded offline **profile-subject binding reproduction**, with owner
headings/academic-role text/contextual affiliation examples and genuine wrong-person
controls. Fix only a demonstrated false rejection; keep strict gates and provenance.
No further live invocation or speculative heuristic change in this execution step.

Pre-run full suite: **1,949 passed, 9 deselected, 86 subtests in 25.09s**,
**91.86% coverage**; Ruff formatting/lint and mypy pass. No new runtime/test changes,
commit, push, Mem0, persistent graph/shortlist, outreach, or tracing upload.

## Step 3k: profile subject false positives repaired offline

Fixed examples reproduced the two measured rejection categories: three exact
section labels were mistaken for people, and `Professor Of/In ...` role phrases
were mistaken for titled names. The narrow repair extends only the known section
allowlist and excludes those professorial role prepositions from the person regex.

Added 30 regression cases, retaining actual-person, repeated-excerpt, unknown-label,
unsupported-model, source/route, missing-field, and exact-provenance checks. The
five-module focused run passed **204 tests in 0.64s**. See the
[offline reproduction and limits](week4-live-canary.md#step-3k-fixed-fixture-profile-subject-repair-offline).

Full non-live suite: **1,979 passed, 9 deselected, 87 subtests in 25.17s**,
**91.86% coverage**. Formatting, lint, mypy, and independent scoped review pass.

These synthetic fixtures prove local defects, not the unseen historical live text.
Strict gates, actual wrong-person controls, source provenance, and availability
handling remain intact. No live call, commit, push, or model/prompt change.
Any next live canary requires separate approval; remaining quality/submission work
and the pre-existing compound role-heading limitation are not declared complete.

## Step 3l: the post-subject-repair live gate still fails

The [single approved live observation](week4-live-canary.md#step-3l-post-subject-repair-live-result)
returned **1 failed in 7.06s**, four logical calls. Extraction completed; strict
verification still lacked grounded current affiliation and research/publication
evidence. Identity was grounded. Affiliation, research interest, and availability
each failed `profile_identity_context_invalid`; publication and project each failed
`profile_subject_mismatch`. Research Fit and Nebius were not called.

These six retained claims do not reveal dropped drafts or the exact source text.
Availability was optional and not the blocking gate. Changed reason counts do not
prove which repair was exercised, historical causality, or a regression.

Next proposed boundary: refine the **existing linked-identity/context diagnostic**
offline into fixed nested failure reasons, with same-decision and privacy tests.
No exact production repair is currently supported by the counts. Keep heading
policy and strict verification unchanged; no blind live rerun or weaker gate.

Pre-run full suite: **1,979 passed, 9 deselected, 88 subtests in 25.14s**,
**91.86% coverage**; formatting, lint, mypy, and 43 focused tests passed.
Only documentation changed in this step. No commit, push, tracing upload, Mem0,
persistent shortlist, or automatic rerun. Quality, dataset, measured improvement,
and submission gaps remain open.

## Step 3m: isolate context failures without changing decisions

The [offline context diagnostic](week4-live-canary.md#step-3m-precise-context-failure-diagnostics-offline)
splits the existing coarse failure into fixed reference/source/identity and
excerpt-subject reason codes. Grounding and availability derivation reuse the same
predicates. No heading exception, weaker evidence gate, or extra provider call.

Fixed domain, extraction, and fake-canary examples test failure order, unchanged
decisions, source provenance, and count-only privacy. The old coarse enum remains
readable for historical output; old live failures cannot be relabelled without
their unretained source/model data.

Added **115 passing offline tests**. Full suite: **2,094 passed, 9 deselected,
89 subtests in 25.43s**, **91.95% coverage**; formatting, lint, and mypy passed.
Independent predicate review found no decision changes in 4,278 comparisons.

This step prepares fault isolation, not live success. A future single live
observation needs separate approval; do not tune matchers from synthetic examples
alone or run repeatedly until green. Research Fit/Nebius live coverage, reviewed
dataset, measured quality/cost improvement, and submission gaps remain open.

## Step 3n: live context failures narrowed to excerpt checks

The [single approved canary](week4-live-canary.md#step-3n-live-precise-context-result)
returned **1 failed in 10.20s**, four logical calls. Extraction completed; only
identity was grounded. Affiliation failed `context_conflicting_person` once;
research interest failed `context_subject_pattern_missing` once; four publications
failed `profile_subject_mismatch`. Research Fit and Nebius were not called.

The two new context reasons occur after linked-identity/source checks passed.
They identify matcher decisions, not actual wrong-person text or absent research.
The rejected affiliation's later typed-field checks remain untested. Seven retained
claims reconcile to one grounded and six rejected; no availability claim was retained.

Next: prioritize an offline affiliation-conflict reproduction with genuine
other-person controls. Research-interest wording is the second mandatory gap;
do not broaden all three matchers or blindly rerun. An exact live-cause repair
needs a minimal source-backed failing excerpt/expected subject for replay, which
the count-only diagnostic did not retain. Any new payload capture needs a separate
privacy-scoped decision. Synthetic examples alone cannot establish historical cause.

Pre-run suite: **2,094 passed, 9 deselected, 90 subtests in 25.59s**,
**91.95% coverage**; formatting, lint, mypy, and 122 focused tests passed.
Only documentation changed; no automatic rerun, commit, push, Mem0, trace upload,
or persistent shortlist write. Remaining dataset, quality, cost, and submission
requirements are not declared complete.

## Step 3s: observed role/discipline conflict repaired offline

The [bounded repair](week4-live-canary.md#step-3s-role-discipline-repair-offline)
shares one deterministic role-label filter across direct/contextual grounding and
private replay. It skips only the complete known professorial discipline label
inside a single-line excerpt. Extra name tokens, Doctor titles, real other people,
and line-wrapped names/particles keep their previous conservative treatment.

The saved affiliation excerpt's conflict clears in offline replay; the research
excerpt retains its original rejection. Strict fake examples with identity,
affiliation fields, and supported research now verify. Tests still reject missing
evidence, changed provenance, unsupported model claims, and other-person conflicts.
No live provider was called and the private capture was not changed or committed.

**Next bounded priority:** reproduce the research title-prefix and sentence-form
case offline, using minimal synthetic text and negative controls. Inspect whether
the sentence actually states a supported research relation before proposing a
narrow change; do not whitelist every sentence beginning with a name or `is`.
The real affiliation's later field checks, project-heading failures, live Research
Fit/Nebius, reviewed labels, and submission quality/cost metrics remain unproven.

## Step 3t: named academic specialisation repaired offline

The remaining research excerpt has an explicit specialisation relation. A narrow
research-only contextual rule now recognizes its complete owner name with or
without an academic title. It does not whitelist all `is` sentences, change direct
identity matching, relax source requirements, or alter any verification threshold.

Both saved excerpt checks now clear in read-only replay. Synthetic complete-evidence
cases verify strictly; negative controls still fail for missing identity/affiliation,
different people/pages, unsupported model output, and incomplete source excerpts.
The private source text remains ignored and has not been copied into regression
fixtures or documentation. No provider was called.

**Next bounded priority:** separately approve one tightly limited live canary to
observe the remaining full-verification gates after these two reproduced repairs.
Do not repeatedly rerun services or assume excerpt success establishes affiliation
fields, research scores, or Nebius review. The reviewed dataset, quality/cost metrics,
project-heading debt, and remaining submission requirements stay open.
See the [runbook](week4-live-canary.md#step-3t-named-specialisation-repair-offline)
and [build journal](build-journal.md) for exact offline results.

## Step 3u: strict live verification and Research Fit reached

One separately approved live observation returned **1 failed in 22.19s**, with
**six logical calls**. Unlike the previous observation, strict identity,
affiliation, and research evidence passed; Research Fit input and evaluation
completed, and Nebius was called once. No fallback search was needed.

The failed test is not a successful end-to-end canary. Current diagnostics stop at
Research Fit evaluation, so they cannot distinguish an unavailable/invalid Nebius
review from a later proposal, synthetic approval, or assertion failure. Do not
infer that review was unavailable or tune credentials/model settings from this
summary alone. No rerun or further runtime change was made.

**Next bounded priority:** add offline-tested, privacy-safe outcomes for independent
review and the later synthesis/approval/check boundaries. Use fixed status/failure
codes and counts only, preserve existing behaviour/call limits, and prove that
each failure is located without leaking model output or exception text. Only after
that should another single live observation be considered for separate approval.

No human relevance labels, model quality/cost result, persisted graph/UI completion,
or completion of all Week 4 requirements is claimed. Exact counts and validation
are in the [runbook](week4-live-canary.md#step-3u-post-repair-live-result).

## Step 3v: checkpoint and post-fit diagnostics ready for observation

Committed the 21 validated files from steps 3q–3u as **`2fbfbeb`** before starting
this change; no push. The separate new diagnostics cover review input, adapter
call/return, reconciled status/failure kind, the completed-review requirement,
synthesis, proposal checks, synthetic in-memory approval, and final assertions.

Fake regressions distinguish an adapter error from a returned but unusable review
and from a later shortlist failure. They preserve exception propagation, call
ceilings, approval ordering, exact evidence, and privacy. Production source,
models, provider configuration, retries, and strict evidence thresholds did not change.

**Next bounded priority:** separately approve one live canary with these diagnostics,
tracing/capture disabled, and the same synthetic Candidate/public target and call
limits. Stop after its first result. Do not change Nebius settings or relax review
validation before the new summary identifies the actual failure boundary.

The earlier live failure cannot be diagnosed retroactively. No new live review,
shortlist/UI success, quality/cost measurement, or completion of all Week 4
requirements is claimed. See the [stage guide](week4-live-canary.md#step-3v-post-fit-diagnostics-offline).

## Step 3w: upstream variation prevented post-fit observation

The single approved live canary returned **1 failed in 8.62s**, using **four
logical calls**. Extraction completed, but strict verification lacked grounded
current affiliation (`institution_not_in_excerpt`: 1). Identity and research
evidence passed. All Research Fit, review, synthesis, and approval stages were
`not_reached`; review/proposal/shortlist summary fields were null.

Do not blame Nebius: it was not called in this run. The earlier step 3u post-fit
failure remains unconfirmed, and its successful verification was not repeated
here. Counts cannot identify the exact raw-page/model-excerpt difference. No
second invocation, private artifact access, runtime edit, or lowered gate occurred.

**Next bounded priority:** isolate Nebius using the existing fixed synthetic-
evidence review smoke test. Check single-call/time bounds and privacy-safe stage
reporting offline before separately approving that live observation. This can
test a real reviewer without repeatedly paying for variable upstream discovery
and extraction; it is not an end-to-end success claim.

Keep current-affiliation repeatability as separate evidence-reproduction debt.
Quality labels, cost metrics, persisted graph/UI behaviour, and the remaining
Week 4 submission requirements are still open. See the
[runbook result](week4-live-canary.md#step-3w-instrumented-live-observation-stopped-at-affiliation).

## Step 3x: isolated reviewer diagnostic prepared offline

The existing Nebius smoke now reports fixed configuration/input/model/response/
reconciliation/final-check outcomes, without serializing input or review content.
It retains the original synthetic fixtures and validation requirements. A guard
prevents a second logical call; request timeout is capped at 60 seconds and tracing
is forcibly disabled. Fake regressions exercise success, failures, privacy, and
scope. No production or live-provider change was made.

**Next bounded priority:** separately approve one invocation of this isolated smoke
with its safe command. Stop at the first result; do not repeat the full pipeline
or change provider prompts/gates speculatively. An isolated pass would establish
one fixed-input Nebius integration observation, not explain the exact historical
response or close end-to-end/quality requirements.

Settings-loader failures and opt-in/missing-key skips are before summary creation;
those remain explicit preflight outcomes. Affiliation repeatability, measured
quality/cost, and persisted graph/UI completion are separate open work.
See the [smoke guide](week4-live-canary.md#step-3x-isolated-nebius-smoke-diagnostics-offline).

## Step 3y: isolated Nebius integration confirmed once

One separately approved live smoke passed (**1 passed in 4.37s**, safe elapsed
**4.356s**, **one Nebius call**). Every diagnostic stage completed, the review
was `accepted`, and no reconciliation failure kind was present. Fixed synthetic
evidence passed schema, score, reference, and reconciliation checks.

This closes the immediate question of whether the reviewer can complete a real
call with valid fixed input. It does not diagnose the historical step 3u output,
resolve step 3w's affiliation repeatability, or establish end-to-end/quality results.
No other provider, capture, tracing, persistence, or approval was exercised.

**Next bounded priority:** resume original priority 3: prepare a versioned,
review-ready 30-case synthetic dataset with distinct cases and labeling provenance.
Preserve the eleven-case baseline; build on the five starting outcomes approved
for review without presenting new labels as human-reviewed. Use the planned
15 happy / 9 edge / 4 known-failure / 2 adversarial mix, including observed failure
patterns as synthetic scenarios rather than copying private live content.
Human review, freezing/uploading the dataset, and baseline comparisons remain
separate subsequent gates. No further live canary is needed for this next step.

See the [observed result](week4-live-canary.md#step-3y-isolated-live-nebius-review-passed).

## Step 3z: separately versioned thirty-case review draft

Original priority 3 now has a [review-ready case inventory](week4-evaluation-draft.md)
and offline CLI. The original eleven scenarios remain byte-for-byte unchanged;
nineteen new synthetic variations exercise real verification and graph policies.
The mix is 15 happy / 9 edge / 4 known-failure / 2 adversarial. All detailed labels
are pending human review; five earlier acknowledged concepts are not full approval.

Offline correctness result: **29/30**. The heading-bound research case exposes an
existing `profile_subject_mismatch` false negative even though separate publication
evidence still permits verification. Keep its expectation; do not tune fixtures or
production policy to manufacture a green baseline. The new request-more case has
76 fake-port invocations against the old provisional 40-call bar, reported separately.
No live result, performance pass, frozen dataset, upload, or baseline overwrite is claimed.

**Next gate:** review the thirty proposed labels, especially the observed failure,
and record explicit reviewer/date/decisions before freezing/uploading a dataset.
Subsequent baseline and comparison work must retain failures and use the same
reviewed version. No automatic fix, live rerun, upload, commit, or push in this step.

### Step 3aa: first expected behavior approved

The project owner explicitly approved heading-bound research acceptance with the
source URL and exact supporting text retained. The [review ledger](week4-label-review.md)
records the response against the current draft version/digest. This approves one
intended behavior only; the other 29 cases await review. The original snapshot
remains unchanged, and the actual heading-grounding bug remains open. Continue
with the remaining review cases before creating a reviewed/frozen dataset.

### Step 3ab: negative-availability behavior approved

The project owner approved retaining verified facts while recording explicit
doctoral non-acceptance as `confirmed_not_accepting` and `verified_with_concerns`,
with a visible, degree-scoped warning. Decision 002 is in the
[review ledger](week4-label-review.md). Two intended behaviors are approved;
28 cases still await review. No implementation change, automatic Supervisor
rejection/shortlisting, manifest rewrite, freeze, or upload is implied.

### Step 3ac: missing-identity behavior approved

The project owner approved retaining a partially verified record and its sources
without promotion when identity cannot be grounded. Institution and research
information do not establish attribution to a person on their own. Decision 003
is in the [review ledger](week4-label-review.md). Three intended behaviors are
approved; 27 cases remain pending. The draft manifest and implementation remain
unchanged, and the known correctness/runtime findings stay open.

### Step 3ad: unsupported-availability behavior approved

The project owner approved rejecting an unsupported accepting assertion and
keeping availability `not_stated`, not `confirmed_not_accepting`. Otherwise complete
verification may succeed; all other required gates remain. Decision 004 is in the
[review ledger](week4-label-review.md). Four intended behaviors are approved;
26 cases remain pending. No implementation or immutable-manifest changes, live
calls, dataset freeze/upload, or commits occur in this step.

### Step 3ae: remaining approvals and local reviewed baseline

The project owner explicitly approved case 5 and the remaining batches. The
[ledger](week4-label-review.md) records five individual expected-behavior approvals
and one batch approval covering the other 25, with no invented per-field reviews.
The [local reviewed manifest and baseline](week4-reviewed-baseline.md) preserve the
original thirty-case draft/digest and eleven-case defaults. Expected behaviors are
approved; passing results are still measured separately. No production fixes, live
provider calls, LangSmith uploads, or commits occur here. Priority 4's uploaded
experiment/trace linkage and later measured improvements remain separate work.

### Step 3af: reviewed LangSmith upload and readback

The [reviewed upload path](week4-reviewed-langsmith-baseline.md) preserves all thirty
approved expectations and the original eleven-case defaults. It validates an exact
server snapshot, executes only fake targets, and records deterministic feedback and
count-only traces. Inspection can recover persisted results without executing an
experiment again. Known heading-grounding and request-more budget findings must
remain visible. The next repair is the measured heading-bound research false
negative, not another broad tuning pass or a change to approved labels.

Actual recorded result: **29/30**, with thirty runs, 330 metric records, and twelve
graph cases with traces. One upload only; the readback issues were repaired and the
same experiment recovered read-only. The full non-live suite passes **2,910 tests**
at **92.53% coverage**. No production repair, provider calls, commit, or push.

### Step 3ag: heading-bound research grounding repair

The [bounded production repair and comparison](week4-heading-grounding-repair.md)
fix the one observed heading-context false rejection. The same reviewed manifest,
source fixtures, expectations, and evaluators now measure **30/30 correctness**
locally, up from 29/30; no other case/metric outcome changes. A same-owner role
sentence no longer replaces the real heading, while other-person and ambiguous
boundaries remain blocked. Exact source provenance is retained.

This is one measured quality improvement, not completion of the required broader
improvement/reporting cycle. The **76/40** fake-call budget finding is unchanged;
next inspect its multi-round scope before altering behavior or thresholds. No
live provider calls, after-experiment upload, environment edits, staging, or commit.

## Step 3o: two excerpt false rejections repaired offline

The [fixed reproduction](week4-live-canary.md#step-3o-excerpt-boundary-repair-offline)
proved complete titled owner names were truncated and a recognized research heading
behaved differently inside versus immediately before an excerpt. Both are repaired
without weakening strict gates or changing the separate page-heading/publication
policy. Fifty new tests preserve actual-person/shared-prefix negatives, exact
provenance, fake call limits, and diagnostic-on/off equivalence.

The combined fake case now completes strict verification; a different person with
the same given-name prefix still fails. Availability remains `not_stated`.
This establishes offline correctness for the fixed cases, not live causality or a
completed Research Fit/Nebius journey. No live call, credential change, commit, or push.

Next: separately approve one bounded live observation with existing safe counts and
call limits. Do not automatically rerun or weaken gates. Exact historical-cause
replay would require source-backed minimal excerpts under a separate privacy scope.
The reviewed dataset, measured quality/cost improvement, publication-heading debt,
and remaining submission requirements are still open. Full suite: **2,144 passed,
9 deselected, 91 subtests passed in 25.99s**, **91.95% coverage**; formatting,
lint, and mypy pass. Exact commands are in the [build journal](build-journal.md).

## Step 3p: live verification remains unresolved after excerpt repairs

The [single approved observation](week4-live-canary.md#step-3p-post-excerpt-repair-live-result)
returned **1 failed in 15.62s**, four logical calls. Identity was grounded;
affiliation again failed `context_conflicting_person`, research interest failed
`context_subject_pattern_missing`, and five publications failed
`profile_subject_mismatch`. Research Fit and Nebius were not reached.

The 50 new offline regression cases remain green. Their validity does not prove
that the live input exercised the repaired paths. These counts are not enough
to select another production exception or establish historical causality.

**Next priority: obtain a minimal exact replay under an explicit privacy scope.**
Use only the rejected affiliation/research excerpt, expected subject, relevant
source-section context, and matcher result. Prefer an existing sanitized sample;
any new live capture needs separate approval. Do not capture a full page, Candidate
input, or credentials. No capture or extra live rerun was performed in step 3p.

Pre-run suite: **2,144 passed, 9 deselected, 92 subtests passed in 25.62s**,
**91.95% coverage**; formatting, lint, mypy, and 75 focused checks passed.
Only documentation changed. Strict gates, public target, model settings, and
provider limits were preserved. No commit, push, Mem0, trace upload, or persistent
shortlist write. Quality, reviewed dataset, cost, and submission work remain open.

## Step 3q: prepare a minimal private replay before further tuning

Checkpoint `af115b6` preserves steps 3g–3p. The new
[private diagnostic](week4-live-canary.md#step-3q-private-excerpt-replay-preparation)
adds an optional observer and offline replay of the **unchanged** excerpt checks.
It is tested using fixed synthetic inputs; no live invocation or actual source
excerpt was captured. This diagnostic work remains separate from that commit.

The bounded capture admits at most one rejected affiliation and one rejected
research excerpt, preserves their exact wording, and writes only a new ignored
private file. Three explicit flags are required for canary capture; ordinary
application runs do not attach the observer. Logs/CLI output show counts only.

Next: separately approve one capture under this privacy scope, inspect its exact
matcher locally, and add a source-backed regression if it reveals a false rejection.
Do not infer success from replaying a rejection, broaden verification, or repeatedly
rerun live services. Live Research Fit/Nebius, reviewed labels, measured quality/cost,
and remaining submission requirements are still unresolved.

## Step 3r: live rejection reproduced without exposing source text

The [single approved capture](week4-live-canary.md#step-3r-live-capture-and-offline-replay-result)
returned **1 failed in 11.81s**, four logical calls, and two eligible private
excerpts. Both excerpt checks reproduced their observed failures offline.
Identity was grounded; strict affiliation/research requirements remained unmet.
Research Fit and Nebius were not reached. No second live invocation was made.

The affiliation case now identifies a concrete false-person match: a role/discipline
label was consumed as a titled person's name. Research is a separate case: the
asserted name contains an academic title, the excerpt's owner prefix does not, and
the remaining sentence form is outside the existing research-relation allowlist.
An in-memory title-only adjustment still fails. This is not proof that all factual
requirements would pass after either change.

**Next bounded priority:** turn the role/discipline case into a privacy-reviewed
minimal offline regression, retain true different-person negative controls, and
repair only that false-person boundary. Then replay both samples to measure the
actual effect. Keep the research grammar and project-heading issues visible as
separate debt; do not accept all named sentences or lower evidence requirements.

The source text remains in an ignored private `0600` artifact inside a `0700`
directory. It was not copied into documentation, tests, traces, or application logs.
No runtime code was changed in this observation. Pre-run validation: **2,320 passed,
9 deselected, 94 subtests passed in 26.55s**, **92.00% coverage**, with formatting,
lint, and mypy passing. Live quality, reviewed labels, cost, and other submission
requirements are not declared complete.
