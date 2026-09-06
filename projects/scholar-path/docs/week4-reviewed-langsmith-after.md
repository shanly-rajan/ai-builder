# Week 4: comparable LangSmith after-experiment

**30/30 cases pass, up from 29/30 on the same reviewed dataset.** Authenticated
readback confirmed all thirty roots, 330 metric records and twelve graph-child
traces. The original **76/40** whole-case call-budget overrun remains unchanged.
This closes the after-trace evidence gap, not all Week 4 submission requirements.

## Recorded run

| Item | Observed value |
| --- | --- |
| Date / implementation | 2026-09-06 UTC; committed checkpoint `1c9ad44`; graph version `m13` |
| After experiment | `scholarpath-week4-reviewed-upload-m13-b804f2f2` |
| After experiment ID | `ab08118f-afbb-47e0-bbdd-6d6726b83e20` |
| Before experiment | `scholarpath-week4-reviewed-upload-m13-5c37c1c1` |
| Dataset | `scholarpath-week4-30case-reviewed-v1` |
| Dataset ID | `327ce17a-9808-42b1-ad5f-590c38fe0258` |
| Snapshot | `2026-09-06T15:55:54.898948Z`, unchanged |
| Reviewed content SHA-256 | `732ad206d79f30e2f9a3c0efd89c07daf4680216754fa21ce8e4d8f7bda911d5` |
| Saved roots / metric records / graph children | 30 / 330 / 12 |
| Correctness / readback | 30/30; complete; CLI exit 0 |
| Provisional runtime budget | Failed: maximum graph calls 76/40 |
| Execution | One after experiment; one repetition; fake providers only; LangSmith is live |
| Dataset creation / public sharing | Neither performed |

Actual workspace-authenticated links:

- [Before experiment: 29/30](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/projects/p/9a11e789-7ed9-43e3-b6fd-54f968eb8cac)
- [After experiment: 30/30](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/datasets/327ce17a-9808-42b1-ad5f-590c38fe0258/compare?selectedSessions=ab08118f-afbb-47e0-bbdd-6d6726b83e20)
- [Reviewed dataset](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/datasets/327ce17a-9808-42b1-ad5f-590c38fe0258)

Open the after link and select the before experiment as the second comparison in
LangSmith. Both experiment names use the existing uploader's prefix; the dataset
was not renamed and the historical experiment was not overwritten.

The [saved actual after report](evaluation/week4-reviewed-langsmith-after-2026-09-06.json)
contains every case ID, example ID, run URL, metric observation and timing. It was
captured from the successful CLI output, not reconstructed from expected results.
The [saved before report](evaluation/week4-reviewed-langsmith-baseline-2026-09-06.json)
remains untouched. A read-only inspection before this upload independently
confirmed its 29/30 result and identical snapshot, dataset ID and digest.

## Observed delta

| Check | Uploaded before | Uploaded after | Delta |
| --- | --- | --- | --- |
| Overall / expected behavior | 29/30 | 30/30 | **+1 case; +3.33 percentage points** |
| Heading-bound research `expected_behavior` | Fail | Pass | The only changed case/metric outcome |
| Other applicable deterministic checks | Passing | Passing | No regression; unchanged denominators |
| Human approval enforcement | 12/12 | 12/12 | Unchanged |
| Graph target p95, 12 cases | 0.131363 s | 0.142125 s | +0.010762 s; not a speed improvement |
| Maximum fake graph calls | 76/40 | 76/40 | **Zero calls saved** |
| Dataset / case IDs / expected labels | Frozen reviewed version | Same version | No changes |

Graph timing includes traced fake-target execution, not live service latency or
Candidate thinking time. With twelve cases, nearest-rank p95 is the maximum. The
two single runs are not a stable performance benchmark. Every per-case fake port
count is unchanged. API readback may express boolean feedback as numeric 0/1;
that representation difference is not a metric improvement.

The sole improvement remains the [heading-grounding repair](week4-heading-grounding-repair.md):
same-owner academic role prose no longer interrupts otherwise valid profile-heading
context. No additional production repair was made during this experiment. All
thirty cases retain their expected behavior labels and the eleven evaluators are
unchanged. The before experiment used the implementation identified in its report;
the after experiment runs the committed repaired implementation at `1c9ad44`.

## Case-level evidence

| Case | Before | After |
| --- | --- | --- |
| Heading-bound research | [Failed expected behavior](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/projects/p/9a11e789-7ed9-43e3-b6fd-54f968eb8cac/r/01a0776e-fb47-7720-ab9f-f0e1143c1895?trace_id=01a0776e-fb47-7720-ab9f-f0e1143c1895&start_time=2026-09-06T15:55:57.127719) | [Passed expected behavior](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/projects/p/ab08118f-afbb-47e0-bbdd-6d6726b83e20/r/01a07809-2779-7862-bd98-5162521a4ad8?trace_id=01a07809-2779-7862-bd98-5162521a4ad8&start_time=2026-09-06T18:44:20.985223) |
| Request more | [Correct behavior, 76 calls](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/projects/p/9a11e789-7ed9-43e3-b6fd-54f968eb8cac/r/01a0776e-fc3a-71e3-b37e-b810aea7880c?trace_id=01a0776e-fc3a-71e3-b37e-b810aea7880c&start_time=2026-09-06T15:55:57.370552) | [Correct behavior, still 76 calls](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/projects/p/ab08118f-afbb-47e0-bbdd-6d6726b83e20/r/01a07809-2866-7a21-a288-7dec86926b61?trace_id=01a07809-2866-7a21-a288-7dec86926b61&start_time=2026-09-06T18:44:21.222641) |

The after [reject-then-approve trace](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/projects/p/ab08118f-afbb-47e0-bbdd-6d6726b83e20/r/01a07809-28e1-7101-b30c-0ad0cbe4dc3a?trace_id=01a07809-28e1-7101-b30c-0ad0cbe4dc3a&start_time=2026-09-06T18:44:21.345194)
provides a scripted human-review route. Fake Candidate actions are not real
Candidate approval of an actual Supervisor. Privacy-safe summaries show canonical
node names, statuses and counts, not source excerpts, private research or secrets.

## Reinspect without creating another experiment

From `projects/scholar-path`, explicitly permitting a read-only LangSmith operation:

```bash
SCHOLARPATH_RUN_LANGSMITH_EVALS=true LANGSMITH_TRACING=false SCHOLARPATH_LOG_LEVEL=WARNING \
venv/bin/python scripts/upload_reviewed_evals.py \
  --inspect scholarpath-week4-reviewed-upload-m13-b804f2f2 --format json
```

Expected: 30 cases, zero failures, complete readback; runtime budget still false.
Do not use `--upload` just to inspect: it creates another experiment. The existing
configured endpoint was verified to reach the correct workspace, so no `.env` or
credential changes were necessary. No OpenAI, Nebius, You.com, Tavily, Mem0 or
LLM-judge calls occurred. No automatic dataset repair, public sharing or Git push
was performed.

## 60-second demonstration

1. Open the dataset comparison and select the two exact experiments above.
2. Show expected behavior rising from 29/30 to 30/30.
3. Open the heading-bound case's before/after trace pair and its feedback.
4. Show request-more still uses 76 calls and explain that correctness and effort
   are separate. The 40/80 policy is supplemental, not a cost saving.

This completes one comparable after-experiment. The remaining 2–3 measured
improvement evidence items, focused Week 4 report and recording remain outstanding.
The [current scorecard](week4-submission-readiness.md) gives the next bounded order.
Live relevance, billed usage and a repeatable live end-to-end result remain unknown.
