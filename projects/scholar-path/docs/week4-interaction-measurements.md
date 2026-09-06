# Week 4 step 3ai: first review and interaction effort

ScholarPath now measures **both scopes separately**, as requested. This is an
instrumentation change, not a runtime optimization or a budget increase.

**Subsequent decision:** step 3aj adds the separately
[approved 40/80 policy](week4-interaction-policy.md). This page and its saved v1
measurement contract retain their historical unset limits; they are not rewritten
to make the legacy result pass.

## Metric contract

| Measurement | Boundary | What it does not mean |
| --- | --- | --- |
| First-review calls | Initial invocation, ending at the first Candidate-review interrupt | A saved shortlist, successful real-world match, or HTTP billing |
| Per-invocation calls | Difference between consecutive counter snapshots from the same run | A difference between independent scenarios or an average per round |
| Complete scripted interaction calls | Initial invocation plus every executed scripted resume | Every possible future Candidate action; the case may still end paused |
| Legacy budget | At most 40 calls for the whole graph case | A per-round allowance |

An initial terminal failure does not count as a first result: its first-review
measurement is absent, while its total attempted work remains counted. A rejected
or failed provider attempt still counts as an invocation of its application port.

```text
Start -> research -> first Candidate-review pause
                      [counter snapshot 0]
                               |
                       explicit Candidate action
                               |
                       resume -> pause or END
                                [counter snapshot 1]

First-review effort = snapshot 0 (only if review is reached)
Resume effort       = snapshot 1 - snapshot 0
Interaction effort  = final snapshot
```

The runtime's optional completion hook receives only a review-paused boolean. The
fake target reads its own ten adapter counters; no Candidate profile, thread ID,
Supervisor identity, evidence content, query, URL, or credential enters this report.
The hook is absent from normal application runs and cannot select a route. Failed
invocations or failed observation cannot masquerade as a complete diagnostic.

## Budget decision

The [saved observations](evaluation/week4-interaction-measurements-2026-09-06.json)
record the actual offline run on 2026-09-06. A regression test compares the complete
report with a fresh execution of the same twelve frozen cases.

| Frozen case | First review | Subsequent invocation calls | Total | Final state |
| --- | ---: | --- | ---: | --- |
| Request more | 38 | 38 | 76 | Paused for review |
| Approve one | 38 | 1 | 39 | Completed |
| Reject then approve | 38 | 1, 1 | 40 | Completed |

The request-more resume includes its explicit preference-memory write; no memory
is written merely for viewing. Across all twelve cases, first review takes 31–38
fake port calls, and the complete scripted case takes 31–76. Every case passes its
existing expected-behavior check; eleven of twelve meet the legacy whole-case
limit. This is a measurement result, not an improvement in execution cost.

At step 3ai the user approved tracking both scopes, **not a new numeric allowance**.
The v1 measurement report's limits remain **unset / not configured**. An unset
limit is not a passing result. The unchanged legacy whole-case test still reports
the request-more case as **76/40 exceeded**.

Do not substitute 80 for 40 simply because the observed case uses 76 calls. A
versioned new target needs an explicit workload boundary and agreement. These
synthetic counts do not calibrate live time, tokens, or monetary cost.

## Run the offline check

From `projects/scholar-path`, using the installed development environment:

```bash
venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e . --config-settings editable_mode=strict
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/inspect_interaction_budget.py
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/inspect_interaction_budget.py --format json
```

The command runs the twelve graph cases in the existing reviewed thirty-case
dataset. Tracing is disabled even if enabled elsewhere. No live providers, uploads,
judge calls, or file-write options are added. **Exit 1 is expected** for the retained
legacy budget overrun; exit 2 indicates an invalid or incomplete diagnostic.

Run `scripts/run_reviewed_evals.py --check` for the separate correctness check.
Its exit policy is unchanged: a runtime overrun is reported separately from
correctness, rather than rewriting approved labels to make the suite pass.

## Provenance and next decision

- Measurement contract: `week4-interaction-measurements-v1`.
- Frozen dataset: `scholarpath-week4-30case-reviewed-v1`.
- Source checkpoint before this increment: `45c0ecd`.
- Historical [independent-case comparison](week4-request-more-budget.md) is retained.
- The [build journal](build-journal.md) records the exact verification commands.

Validation: **3,111 tests passed**, nine live tests deselected, **92.71% coverage**;
Ruff formatting/lint and mypy passed. The thirty-case correctness suite remains
**30/30**, while the historical whole-case runtime failure remains visible.

The numerical decision deferred at this checkpoint is now recorded separately in
step 3aj. Its policy distinguishes initial review from an interaction with a search
revision and final approval. Caching and live performance calibration remain separate
work; this measurement step is not another agent-quality gain.
