# Week 4 step 2: Expected outcomes and runtime metrics

Date: 2026-09-06.

## User prompt

> Lets proceed to next step

## Approved context and bounded interpretation

Continue item **2** of [Week 4 triage](../week4-triage.md), after the separately committed
failure-summary repair. The underlying instruction is to prioritize low-effort, high-value
Week 4 evaluation requirements under an end-of-day deadline, preserving existing architecture.

Implement an expected-behavior evaluator using the current reference labels, record per-case
target time and tool/model usage, and document a small set of headline metrics and numeric
pass bars. Preserve fake/offline defaults and explicitly mark unmeasured live cost/usage.
Test correct, empty, malformed, and wrong outcomes, missing telemetry, errors, and reporting.
Use an accurately dated run identity and preserve the historical dataset/baseline.

Do not expand the eleven-case cohort, upload a LangSmith experiment, invoke a live provider,
change graph/UI behavior, or claim human-reviewed labels or measured quality improvements.
Those are subsequent ordered steps. Run formatting, lint, mypy, and the complete non-live
suite; record the outcome in the journal and commit this step separately.
