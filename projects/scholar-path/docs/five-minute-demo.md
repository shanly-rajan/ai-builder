# ScholarPath Five-Minute Demonstration

This demonstration has two layers:

1. a deterministic offline release journey that always shows the complete
   reject/refine/approve route; and
2. an optional traced Streamlit run for a real LangSmith route visualization.

The offline journey is the release proof. The traced run is an operational demonstration and
requires configured provider credentials. Never paste credentials, a real Candidate's personal
data, or full source content into a terminal transcript or screenshot.

## Before the timer

From `projects/scholar-path`, install the exact-version constraints and load only the ignored
local `.env` when you intend to run the traced layer:

```bash
python -m pip install --upgrade "pip==26.1.2" "setuptools==84.0.0"
python -m pip install --constraint requirements.lock --no-build-isolation -e ".[dev]" \
  --config-settings editable_mode=strict
```

For the optional trace, `.env` must contain valid OpenAI, You.com, Tavily, Nebius, and LangSmith
configuration. Set the correct LangSmith regional endpoint and workspace for the key. Keep
`SCHOLARPATH_DISCOVERY_FAILURE_MODE=off` in the file; the demonstration overrides it for one
process only.

## 0:00–1:00 — Run the deterministic full journey

```bash
LANGSMITH_TRACING=false pytest -o addopts='' -q -s \
  tests/integration/test_m13_release_end_to_end.py
```

The privacy-safe transcript and assertions show this exact sequence:

```text
Candidate profile accepted: 2 research topics; applied orientation
SearchPlan created: 4 source-diverse queries
You.com route: timeout -> one retry -> retryable provider failure
Tavily fallback: 6 plausible profiles retained
Verification: 6 Verified Supervisors with source URLs
Research Fit: 6 assessments; independent reviews: 6
Candidate action: reject 1 Supervisor; shortlist writes: 0
Preference learning: rejection reason stored; planning round: 2
Candidate action: approve 5 Supervisor IDs
Final briefing: 5 Candidate-approved, evidence-backed Supervisor recommendations
```

This test uses fake ports, an in-memory checkpointer, a fixed clock, and no network. It proves
that the failure is injected, partial provider work is retained, rejection is learned before
replanning, and no Shortlisted Supervisor exists before explicit approval.

## 1:00–2:00 — Start the traced application

Load `.env`, then override tracing and failure injection for this process:

```bash
set -a
source .env
set +a

LANGSMITH_TRACING=true \
SCHOLARPATH_DISCOVERY_FAILURE_MODE=you_retryable_error \
streamlit run streamlit_app.py
```

The injected failure is typed and deterministic. It prevents the You.com call for this run and
forces the existing bounded routing policy to Tavily. The setting is off by default and is
rejected when `SCHOLARPATH_ENVIRONMENT=production`.

## 2:00–3:00 — Enter a synthetic Candidate profile

Use demonstration data, not personal data:

| Field | Demonstration value |
|---|---|
| Proposed research statement | Evaluate applied enterprise architecture controls for traceable agentic AI systems. |
| Research topics | enterprise architecture; agentic AI governance |
| Preferred regions | United Kingdom; Netherlands |
| Study mode | part-time; remote |
| Research orientation | applied |
| Methodological interests | design science; case study evaluation |
| Exclusions | purely theoretical model pre-training |

Select **Start Supervisor research**. Expand **Canonical LangGraph progress** and point out:

```text
load_candidate_preferences
plan_supervisor_searches
discover_prospective_supervisors
enough_supervisors_found
fallback_supervisor_search
enough_supervisors_found
deduplicate_supervisors
extract_supervisor_evidence
supervisor_evidence_sufficient
evaluate_research_fit
review_fit_assessments
synthesize_supervisor_shortlist
candidate_review_gate
```

In the privacy-safe discovery diagnostics, show the typed primary failure, that Tavily fallback
was used, and the raw/plausible/retained counts. Do not expand or copy provider content outside
the application.

## 3:00–4:00 — Inspect evidence, reject, and refine

For one proposed recommendation, point out:

- Supervisor name and institution;
- verification status and evidence source links;
- Research Fit Score and explanation;
- evidence confidence and concerns;
- availability status as a separate sourced fact; and
- independent review status.

Open **Reject**, choose one Supervisor, enter:

```text
I want stronger applied design-science evidence.
```

Submit the rejection. Show that:

- the graph resumes the same thread;
- `learn_candidate_preferences` runs before replanning;
- the rejected Supervisor does not become shortlisted;
- the next planning round includes the durable rejection preference; and
- the graph pauses again at Candidate review within its finite iteration budget.

## 4:00–5:00 — Approve and inspect the trace

Select the final Verified Supervisors and choose **Approve selected Supervisors**. Show:

- `save_shortlisted_supervisors` occurs only after the approval;
- `generate_shortlist_briefing` follows the save;
- the final page labels the records as Shortlisted Supervisors; and
- the briefing says the recommendations were Candidate-approved and evidence-backed.

In LangSmith, open the configured project and inspect the newest `scholarpath_graph` trace
sequence. Interrupt resume is a new graph invocation, so the start, rejection resume, and
approval resume appear as separate root traces rather than one artificial long-running request.
Together they should visibly show planning, primary discovery, fallback search, verification,
Research Fit, independent review, preference learning and replanning, shortlist save, and
briefing. Confirm the trace metadata contains low-cardinality versions, provider/route
categories, aggregate counts, fallback use, and review outcome—but not Candidate identity,
research statement, query text, source URLs, page content, thread ID, or credentials.

## Optional bounded live canary

The canary validates one configured public official profile rather than spending the full
five-result graph budget. Set these non-secret target values in the process environment:

```dotenv
SCHOLARPATH_LIVE_CANARY_SUPERVISOR_NAME=Exact public Supervisor name
SCHOLARPATH_LIVE_CANARY_INSTITUTION=Exact public institution
SCHOLARPATH_LIVE_CANARY_PROFILE_URL=https://institution.example/people/exact-profile
```

Then load `.env` and run:

```bash
SCHOLARPATH_RUN_LIVE_TESTS=true \
SCHOLARPATH_RUN_LIVE_CANARY=true \
LANGSMITH_TRACING=false \
pytest -o addopts='' -q -rs -m live \
  tests/integration/test_m13_live_canary.py
```

The test is skipped unless both opt-ins, all required credentials, and the three public target
values are present. Its wrappers reject calls beyond the declared budget: at most two planning
calls, one You.com search, one Tavily fallback search, one Tavily extraction, one evidence-model
call, two Research Fit calls, and one Nebius review call—at most nine provider calls in total.
The one-profile path creates a shortlist only after constructing an explicit approval decision.
It must remain excluded from default pytest and CI.

## Demonstration failure paths

| Observation | Response |
|---|---|
| Missing provider key | Stop the traced layer and show the deterministic offline journey; do not paste the key into a command. |
| LangSmith `403` | Verify endpoint region, workspace ID, key scope, and project; keep the offline release result separate. |
| Too few live profiles | Explain the bounded recoverable state; do not weaken identity, evidence, or availability rules during a demonstration. |
| Evidence remains partial | Show the retained evidence and missing categories; do not present the record as a Verified Supervisor. |
| Review limit reached | Show the safe terminal message and start a new research run with revised preferences. |
