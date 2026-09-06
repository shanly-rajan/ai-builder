# Week 4 step 3ah: explain the request-more call budget

**The 76/40 finding is a whole-case budget overrun, not an infinite loop.** The
initial-review case makes 38 fake application-port calls. The request-more case
executes two planning passes and makes 76. The original 40-call bar still fails;
this step explains it without changing behavior or declaring a cost improvement.

## What the budget actually covers

[Week 4 metrics](week4-metrics.md) defines **at most 40 calls per graph case**.
The original eleven-case calibration observed a maximum of 39. The later reviewed
cohort adds a Candidate-driven region revision and another research pass before
pausing for review. Dividing 76 by two would change the bar to a per-round limit;
that is not the metric we froze.

The scenario uses the real deterministic graph with fake adapters. Its planner
receives the revised Germany preference, but its scripted response deliberately
returns the same fixture queries. This does not demonstrate identical live searches
or establish live provider cost.

## Observed attribution

The [saved diagnostic report](evaluation/week4-request-more-budget-2026-09-06.json)
records the actual offline run on 2026-09-06. A regression test compares this
snapshot with a fresh execution of the same two frozen cases.

The new optional observer copies only the ten existing adapter counters. Its total
must equal the existing target measurement, including failed attempts and resumes.
No graph state or source content is passed to the observer.

| Application port | Initial-review case | Request-more case | Difference |
| --- | ---: | ---: | ---: |
| Planning model | 1 | 2 | +1 |
| Primary search | 4 | 8 | +4 |
| Fallback search | 0 | 0 | 0 |
| Alternate-source search | 0 | 0 | 0 |
| Page extraction | 8 | 16 | +8 |
| Evidence model | 8 | 16 | +8 |
| Research Fit model | 8 | 16 | +8 |
| Independent review model | 8 | 16 | +8 |
| Preference-memory load | 1 | 1 | 0 |
| Preference-memory write | 0 | 1 | +1 |
| **Total** | **38** | **76** | **+38** |

These are **two independently executed frozen cases**, not separately measured
phase counters. The request-more trace has two `plan_supervisor_searches` executions,
one explicit request-more action, and another review interrupt. Code inspection
attributes the extra work to preference capture and a new research pass:

```text
Initial research -> Candidate review pause
                         |
                    request_more
                         |
                Write revised preferences
                         |
               Plan and research again -> Candidate review pause
```

The initial view writes no preference memory. Request-more writes once. Both cases
remain paused without a saved shortlist and pass the existing expected-behavior
evaluator. Neither Candidate approval nor evidence strictness was bypassed.

## Reproduce in 60 seconds

From `projects/scholar-path`:

```bash
venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e . --config-settings editable_mode=strict
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/inspect_request_more_budget.py
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/inspect_request_more_budget.py --format json
```

**Exit 1 is expected** because the 40-call whole-case budget is exceeded. Exit 2
indicates a diagnostic/contract failure. There are no live, upload, or file-write
options. The diagnostic disables tracing even if opt-in flags are set elsewhere.
It emits closed scenario/status labels and counts, never names, queries, source
content, credentials, or exception details.

The frozen correctness suite remains separate:

```bash
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/run_reviewed_evals.py --check
```

That command still reports **30/30 correctness, exit 0**, with **76/40 exceeded**
shown separately. The two exit policies are deliberately different.

## Evidence and limits

- Dataset: `scholarpath-week4-30case-reviewed-v1`.
- Reviewed digest: `732ad206d79f30e2f9a3c0efd89c07daf4680216754fa21ce8e4d8f7bda911d5`.
- Source draft digest: `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.
- Source checkpoint: `4672168` plus this count-only diagnostic change; graph
  version remains `m13`. No case recipes, labels, fakes, or evaluator definitions changed.
- [Build journal](build-journal.md) records commands, tests, and actual results.
- Historical before/after reports are retained. This is attribution, not another
  agent-quality improvement or a new LangSmith experiment.

## Next decision, not an automatic change

Replanning and preference-sensitive scoring/review are legitimate after a Candidate
changes requirements. Reusing identical page/evidence work could theoretically remove
16 of these calls, but would still leave **60/40**. That is arithmetic based on the
fixture counts, not an implemented or measured optimization. Safe reuse would need
identity, URL, freshness, and model/policy-version checks.

Before implementing such reuse, agree whether the desired performance requirement
is first-result effort, a full interaction allowance, or both. Any new multi-round
budget must be explicit and versioned, with the original 76/40 result preserved.
Do not raise it silently, skip Candidate-driven work, reduce Supervisor coverage,
or relax verification to produce a green report. Live billing and relevance remain
unmeasured.
