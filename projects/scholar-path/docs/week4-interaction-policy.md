# Week 4 step 3aj: approved 40/80 interaction policy

The user approved **40 calls to first review** and **80 total calls for a bounded
interaction**. Policy `week4-interaction-policy-v1` applies these limits alongside
the historical policy, without changing graph execution or claiming a cost saving.

## Decision and rationale

| Check | Approved limit | Boundary |
| --- | ---: | --- |
| First Candidate review | 40 calls | Initial invocation must actually reach review |
| Bounded interaction | 80 total calls | Initial research, at most one revision, then final approval |
| Historical whole-case check | 40 calls | Unchanged complete scripted-case measurement |

The new allowance recognizes that a Candidate may explicitly ask for another
research pass. It is a provisional offline effort target, not a measured latency
or billing guarantee. Approval is archived in the [prompt](prompts/week4-3aj-approved-interaction-policy.md).
It does not erase the original **76/40** failure or demonstrate faster execution.

The bounded scope allows at most two accepted Candidate actions: for example,
request-more then approve, reject then approve, or immediate approval. Approval
must be last. More actions or more than one research revision are outside this
policy, even if their total happens to be under 80. The application itself remains
free to follow its existing bounded review loops; this policy only classifies
evaluation results.

A research revision is observed when a resumed invocation calls the planning
model. Multiple model attempts inside that invocation count as calls, not separate
revisions. A rejection that starts research again uses the same revision allowance.
More than one request-more action is also outside scope, even with missing planning
activity; it cannot silently expand the approved workload.

## How results are interpreted

```text
Measured case -> validate counters and workload scope
                         |
                    compare limits
                         |
            +------------+----------------+
            |            |                |
     Completed with    Still paused    Terminal without
     final approval    for review      valid completion
            |            |                |
       passed or     within budget     not completed
        exceeded     so far / exceeded  / exceeded
```

Out-of-scope cases are `not_applicable`, never completed passes. First review
that is never reached is `not_reached`, not zero effort and not a pass. Limits are
inclusive: 40 and 80 are within their respective limits; 41 and 81 exceed them.
The first-review and interaction checks remain separate: finishing under 80 does
not excuse exceeding 40 before the Candidate can first review.

## Run the offline policy check

From `projects/scholar-path` with the development environment installed:

```bash
venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e . --config-settings editable_mode=strict
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/check_interaction_policy.py
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/check_interaction_policy.py --format json
```

The check reuses the twelve frozen fake graph cases. It disables tracing, emits
only controlled labels and counts, and offers no live, upload, or file-write flags.
The JSON contains the approved policy plus its unchanged source measurement report:
`source_measurements.supplemental_policy_status` remains `not_configured` because
that field belongs to the historical measurement contract, not the new policy.

**Exit 1 remains expected** while the original whole-case failure is present. The
command also returns 1 for exceeded new limits, an unreached first review,
unfinished terminal outcomes, or out-of-scope cases. Exit 2 means the diagnostic
could not validate or complete. A paused prefix is not itself a budget failure,
but it is never included in the completed-pass count. There is no all-completed
claim merely because a command exits successfully.

The old `scripts/inspect_interaction_budget.py` and
`scripts/run_reviewed_evals.py --check` retain their previous behavior. The latter
checks correctness independently from the runtime proxy. Neither historical
measurement artifacts nor frozen expected outcomes are rewritten.

## Observed policy results

The [saved policy report](evaluation/week4-interaction-policy-2026-09-06.json)
records the actual 2026-09-06 offline run, with both policy versions visible.
A regression test compares it against a fresh run of the frozen cases.

| Result | Cases |
| --- | ---: |
| First review within 40 calls | 12 |
| Completed, approved interactions within 80 calls | 3 |
| Paused interactions within budget so far | 9 |
| New-limit overruns | 0 |
| Historical whole-case overruns | 1 |

The request-more case is **76/80 within budget so far**, still paused, and still
**76/40 exceeded** under the historical rule. The completed cases consume 39, 39,
and 40 calls. This cohort does not demonstrate a completed request-more-then-approve
journey; no eventual completion cost is extrapolated from its paused measurement.

Verification: **3,168 tests passed**, nine live tests deselected, **92.79% coverage**;
formatting, Ruff lint, and mypy passed. The frozen correctness suite remains **30/30**.
See the [build journal](build-journal.md) for exact commands and results.

## Remaining limits

Only fake application-port calls are measured here, not live HTTP requests,
tokens, monetary cost, or human review time. A paused request-more case cannot
prove the eventual cost of approving its results. Live calibration and further
agent-quality improvements remain separate work. No cache, reduced evidence
standard, changed provider, or automatic shortlist approval is introduced.
