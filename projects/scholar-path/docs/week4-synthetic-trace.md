# Week 4: one synthetic fallback trace

This step checks trace wiring, not live research quality. The graph and routing
code are real; all application providers are fake. LangSmith is the only remote
service used by the explicit upload command.

```text
Curated synthetic case → real LangGraph → safe node summaries → LangSmith
                           │
                fake You.com timeout twice
                           ↓
                fake Tavily → verification → fit → independent review
                           ↓
                   pause for Candidate review
                   no shortlist saved
```

## Run from projects/scholar-path

Check the single case without any network calls:

```bash
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false \
venv/bin/python scripts/trace_eval_case.py
```

Upload only this case after configuring the LangSmith API key, correct regional
endpoint, and workspace ID if required in the ignored `.env` file:

```bash
SCHOLARPATH_RUN_LANGSMITH_EVALS=true SCHOLARPATH_LOG_LEVEL=WARNING \
LANGSMITH_TRACING=false venv/bin/python scripts/trace_eval_case.py --upload
```

The explicit upload scope enables tracing despite `LANGSMITH_TRACING=false`.
That flag keeps normal application tracing off; the dedicated client inherits
the evaluation parent and experiment. It does not enable live providers or LLM
judges. The command prints the experiment name and opaque trace reference.

## What to inspect

Open the printed experiment in LangSmith and select its one example. Expand
`Target` → `scholarpath_graph`. Confirm:

1. Planning runs before discovery.
2. Two simulated You.com timeout attempts precede Tavily fallback.
3. Evidence verification, Research Fit, and independent review execute.
4. The graph pauses for Candidate review; no shortlist is saved without approval.
5. Node inputs/outputs show field counts, presence, and closed status values—not
   Candidate content, credentials, source pages, queries, or evidence URLs.

The dedicated dataset is `scholarpath-week4-synthetic-trace-v1`. Only an exact
match to the repository's curated fallback inputs and reference is accepted.
The historical and provisional multi-case datasets are unchanged.

Inputs, outputs, metadata, and error text are filtered at the dedicated client.
Model-token counts and provider monetary cost are not measured in this fake
experiment. Synthetic timing must not be presented as live service latency.

## Observed result

Recorded **2026-09-06 at 11:13 UTC**:

- Experiment: `scholarpath-week4-m13-01c56dc8`, **1/1 passed**.
- [Open the experiment](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/datasets/8076ea5d-f6af-489f-bd3d-16be72f31ad3/compare?selectedSessions=7b7b906e-918b-4d4e-a74c-1fe659ea5ca5).
- [Open the verified trace](https://smith.langchain.com/o/8cf85d4c-234a-42f3-9611-a3f19687db75/projects/p/7b7b906e-918b-4d4e-a74c-1fe659ea5ca5/trace/01a0766c-2d14-72b3-81eb-48b6f4dd4c77/run/01a0766c-2d14-72b3-81eb-48b6f4dd4c77?start_time=2026-09-06T11%3A13%3A16.052047Z).
  Both links require authorized workspace access; no public share was created.
- Authenticated API readback confirmed **24 spans** sharing one trace ID,
  including two simulated You.com timeouts and three successful fake Tavily attempts.
- The graph retained **6 Prospective Supervisors**, completed **6 verification
  records**, **6 assessments**, and **6 independent reviews**, and proposed **5**.
- `interrupted=true`, `review_status=proposed`, **0 shortlisted Supervisors**.
  The Candidate-review span has no normal return output while paused; that is expected.
- Root and node inputs/outputs contain the intended aggregate summaries. No raw
  Candidate profile, search query, page content, identity, or evidence URL was
  present in the inspected input/output summaries.
- The full non-live suite passed: **1,820 passed, 9 deselected in 24.82s**,
  **91.74% coverage**. Ruff formatting/lint and strict mypy passed.

This is a successful synthetic trace check, not a live-provider quality baseline.
The provider labels in the trace identify simulated roles, not billed service calls.

The implementation uses the SDK's scoped parent/client context and client-side
masking mechanisms: [scoped tracing](https://docs.langchain.com/langsmith/trace-without-env-vars),
[input/output masking](https://docs.langchain.com/langsmith/mask-inputs-outputs).

## Next boundary

After this trace check, perform a separately authorized, tightly limited real
provider journey. Use live-appropriate expectations rather than fixture
Supervisor IDs. Curating the remaining golden dataset, freezing labels/budgets,
and comparing measured improvements remain Week 4 work.
