# Week 4: approved expectations and local baseline

**30 expected behaviors approved; 29/30 measured cases pass.** Human approval
sets the expected outcomes; it does not turn implementation failures into passes.

## Local freeze and provenance

| Item | Recorded value |
| --- | --- |
| Dataset | `scholarpath-week4-30case-reviewed-v1` |
| Reviewed version | `week4-30case-reviewed-v1` |
| Status | `frozen_local`; not uploaded |
| Approval | Project owner, 2026-09-06; `expected_behaviors` only |
| Review method | Five individual approvals and one explicit batch approval covering 25 cases |
| Reviewed content SHA-256 | `732ad206d79f30e2f9a3c0efd89c07daf4680216754fa21ce8e4d8f7bda911d5` |
| Original draft SHA-256 | `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e` |
| Baseline name | `scholarpath-week4-reviewed-local-20260906T153428Z-e585120b` |
| Measurement date | 2026-09-06, UTC |
| Graph version | `m13` |
| Execution | Fake providers, tracing disabled; no live calls or uploads |

The [approval ledger](week4-label-review.md) retains the exact responses and
explicit case coverage. Batch approval is not presented as 25 individual reviews
or inspection of every typed field. The
[frozen JSON manifest](evaluation/week4-30case-reviewed-v1.json) embeds the unchanged
pre-review draft and its pending metadata as historical source material. Review
decisions live in the outer wrapper. No existing case inputs or expectations were
edited; the original eleven-case defaults and historical baselines are unchanged.

The builder pins the original draft digest and rejects missing/duplicate approvals,
unrecorded provenance, or changed inputs/labels under this version. Its digest also
includes the review provenance. Tests compare the saved artifact to that builder.
The manifest freezes scenario recipes and expected outputs, not provider behavior
or dependency binaries. Synthetic fixtures and target implementation come from
the repository; production/fixture source at measurement was unchanged from
`e0a1cddb3db4225bec8288b4ba3e70409afa2985`, with the additive reviewed-manifest/runner
files still uncommitted. Use the same recipes, fixtures, and evaluator definitions
for later before/after comparisons and identify each implementation revision.

## Reproduce locally

From `projects/scholar-path`, using the installed project environment:

```bash
venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e . --config-settings editable_mode=strict
venv/bin/python scripts/run_reviewed_evals.py
venv/bin/python scripts/run_reviewed_evals.py --format json
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/run_reviewed_evals.py --check
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/run_reviewed_evals.py --check --format json
```

Preview commands execute no targets. Both checks run the same 30 fake-provider cases
and force tracing off even if live/tracing flags are enabled. They intentionally
exit **1** while correctness is 29/30. Every execution gets a unique local baseline
name; latency is an observation, not a fixed fixture. The CLI writes only to stdout;
it does not overwrite the saved baseline and has no live, upload, or judge option.
Exit status measures correctness; provisional runtime limits are reported separately.

Quality checks: formatting and Ruff pass; mypy reports no issues in 254 source files.
`venv/bin/pytest -q --tb=short` completed with **2,773 passed, 9 deselected,
107 subtests passed in 33.20s**, **92.38% coverage**. The 55 new tests cover approval
provenance, drift rejection, offline execution, and report/artifact integrity.
A passing test suite confirms that the evaluation harness correctly reports the
known failure; it does not mean the baseline has become 30/30.

## Observed baseline

The [saved machine-readable report](evaluation/week4-reviewed-baseline-2026-09-06.json)
contains all 30 per-case metric records, timings, fake-port counts, and failures.
No target payloads, credentials, private Candidate content, or invented trace links
are included. All fixtures use synthetic inputs. There is no LangSmith experiment
URL because this run was local and tracing was disabled.

| Deterministic check | Passed / applicable |
| --- | --- |
| Schema validity | 30 / 30 |
| Expected behavior | 29 / 30 |
| Canonical terminology | 30 / 30 |
| Evidence ID validity | 14 / 14 |
| Source URL presence | 29 / 29 |
| Score range and component totals | 14 / 14 |
| No unsupported availability claim | 29 / 29 |
| No admission probability | 30 / 30 |
| Correct fallback route | 1 / 1 |
| Duplicate Supervisor rate | 12 / 12 |
| Human approval enforcement | 12 / 12 |

Metric definitions and provisional numeric bars remain in
[Week 4 metrics](week4-metrics.md). Applicability denominators differ by target;
they are not dropped failures. See the draft guide for the distinction between
typed expected-behavior metrics and additional unit assertions (such as region
propagation or preserving an unstated publication year).

| Target family | Cases | Median target time | p95 target time | Max fake port calls / budget |
| --- | --- | --- | --- | --- |
| Evidence verification | 15 | 0.003820 s | 0.006277 s | 2 / 2 |
| Fake graph | 12 | 0.044389 s | 0.067619 s | **76 / 40 — exceeded** |
| Research Fit | 2 | 0.003412 s | 0.003422 s | 1 / 2 |
| Search planning | 1 | 0.000132 s | 0.000132 s | 1 / 2 |

Target time excludes evaluator overhead. All measured p95 values are below the
provisional five-second fake-target bar. The graph invocation budget still fails;
no runtime pass is claimed. Fake calls are not billed API requests. Tokens,
monetary cost, real provider latency, relevance, and live repeatability are unmeasured.

## Failure clusters and next bounded work

1. **Grounding false negative — 1/30 cases (1/15 evidence cases).**
   `draft-evidence-heading-bound-research` fails `expected_behavior` because the
   research-interest claim is rejected as `profile_subject_mismatch` despite the
   correct profile-heading context. Separate publication evidence permits overall
   verification, so aggregate verification alone would miss this failure. Keep the
   approved label; do not rearrange the fixture or relax the expectation to pass.
2. **Provisional runtime overrun — 1/12 fake graph cases.**
   `draft-graph-request-more` makes 76 application-port invocations over two rounds,
   against the unchanged 40-call bar. This is a separate runtime finding, not another
   correctness failure. Review the budget's multi-round scope before deciding on
   a targeted improvement; do not silently raise it or claim a live cost saving.

The local freeze and baseline are complete. The next submission-evidence step is
an explicitly authorized upload/experiment using this same reviewed version, with
actual trace links. Existing upload commands still default to eleven cases and
must not be presented as uploading this manifest. Then repair the reproduced
grounding failure and measure its effect against these frozen cases. No production
repair or external upload was performed here. Week 4 still needs comparable measured
improvements, linked trace evidence, and the focused report/recording.
