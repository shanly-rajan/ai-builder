# ScholarPath Five-Minute Demonstration

This demonstration has three deliberately separate layers:

1. a deterministic offline release journey that always shows the complete
   reject/refine/approve route; and
2. a development-only `deterministic_demo` Streamlit profile for the interactive five-minute
   walkthrough; and
3. an optional provider-backed `live` Streamlit profile for a real LangSmith route visualization.

The offline journey is the release proof. The deterministic Streamlit profile uses fixed
synthetic adapters, an in-memory checkpoint, and forced-off tracing. The optional traced profile
requires configured provider credentials. Never paste credentials, a real Candidate's personal
data, or full source content into a terminal transcript or screenshot.

## Before the timer

From `projects/scholar-path`, install the exact-version constraints:

```bash
python -m pip install --upgrade "pip==26.1.2" "setuptools==84.0.0"
python -m pip install --constraint requirements.lock --no-build-isolation -e ".[dev]" \
  --config-settings editable_mode=strict
```

No `.env` or provider credential is required for the deterministic layer. For the optional live
trace, `.env` must contain valid OpenAI, You.com, Tavily, Nebius, and LangSmith configuration.
Set the correct LangSmith regional endpoint and workspace for the key. Keep
`SCHOLARPATH_RUNTIME_PROFILE=live` and `SCHOLARPATH_DISCOVERY_FAILURE_MODE=off` in the file; the
commands below use process-local overrides.

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

## 1:00–2:00 — Start the deterministic Streamlit application

Fully stop any existing Streamlit server, then run this exact block without loading provider
credentials:

```bash
SCHOLARPATH_RUNTIME_PROFILE=deterministic_demo \
SCHOLARPATH_ENVIRONMENT=development \
LANGSMITH_TRACING=false \
venv/bin/streamlit run streamlit_app.py
```

The app must show the persistent, non-dismissible warning **Synthetic offline demonstration mode
is active.** It explains that the runtime uses invented test data rather than live Supervisor
research. Keep that warning visible in every screenshot and verify it remains present after
reruns and stage changes. The demonstration composition makes no provider call, requires no
provider key, forces tracing off regardless of broader environment settings, and stores its
threads only in memory.

Confirm the active academic hero is exactly **🎓 ScholarPath** and its subtitle is exactly
`Evidence-backed Supervisor discovery for Master's and doctoral research.` Stage one must read
**1. Your Research Degree Profile**, with the exact guidance
`Describe your Master's or doctoral research direction and practical preferences that should guide Supervisor discovery.`

`deterministic_demo` is rejected when `SCHOLARPATH_ENVIRONMENT=production`. Runtime composition
is held by Streamlit's cached application service, so a browser refresh or rerun cannot switch
profiles. Fully stop and restart the Streamlit server to change profiles; restarting discards the
in-memory demonstration thread.

## 2:00–3:00 — Enter a synthetic Candidate profile

Use demonstration data, not personal data. This walkthrough frames it as a Master's research
direction; the same free-text profile supports doctoral research without adding a degree-type
field or inferring programme eligibility:

| Field | Demonstration value |
|---|---|
| Proposed research statement | Evaluate applied enterprise architecture controls for traceable agentic AI systems. |
| Research topics | enterprise architecture; agentic AI governance |
| Preferred regions | United Kingdom; Netherlands |
| Study mode | part-time; remote |
| Research orientation | applied |
| Methodological interests | design science; case study evaluation |
| Exclusions | purely theoretical model pre-training |

Select **Start Supervisor research** and observe **Canonical LangGraph progress** while it is
active. After the graph pauses, confirm completed progress is collapsed by default, then expand it
and point out the same real graph stages used by the provider-backed profile:

```text
load_candidate_preferences
plan_supervisor_searches
discover_prospective_supervisors
enough_supervisors_found
deduplicate_supervisors
extract_supervisor_evidence
supervisor_evidence_sufficient
evaluate_research_fit
review_fit_assessments
synthesize_supervisor_shortlist
candidate_review_gate
```

Bounded fallback or alternate-source nodes appear only when the synthetic state reaches their
existing route conditions; the demonstration profile does not force or bypass them. Confirm the
Prospective Supervisor outcomes start as collapsed cards labelled with name and institution.

Open the collapsed outer panels **Discovery diagnostics**, **Alternate-source diagnostics**, and
**Evidence-verification diagnostics** one at a time. Show aggregate discovery, retrieval,
retained-claim, directly grounded, and verification counts, then collapse each panel again.
Emphasize that page retrieval success is not verification. Do not copy fixed source content
outside the application.

## 3:00–4:00 — Inspect evidence, reject, and refine

Confirm every review outcome starts collapsed under a label containing the Supervisor's name,
institution, and `Research Fit: N/100`. Expand one proposed recommendation and point out:

- Supervisor name and institution;
- verification status and evidence source links;
- Research Fit Score and explanation;
- evidence confidence and concerns;
- availability status as a separate sourced fact; and
- independent review status.

For this Master's-scoped example, an explicit doctoral-availability statement remains evidence
only for its stated doctoral context; it is not proof of Master's availability. Do not infer
degree eligibility from the profile, Research Fit Score, or `not_stated`.

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

## 4:00–5:00 — Approve and inspect the final shortlist

Select the final Verified Supervisors and choose **Approve selected Supervisors**. Show:

- `save_shortlisted_supervisors` occurs only after the approval;
- `generate_shortlist_briefing` follows the save;
- the final page labels the records as Shortlisted Supervisors; and
- Shortlisted Supervisor cards remain collapsed initially with name, institution, and applicable
  `Research Fit: N/100` in each label;
- the briefing says the recommendations were Candidate-approved and evidence-backed; and
- the persistent warning still identifies every displayed result as synthetic.

The demonstration exercises the unchanged identity, grounding, verification, minimum-count,
alternate-retry, availability, Research Fit, independent-review, Candidate-approval, and
lifecycle rules. Only dependency composition, tracing, persistence, and the synthetic warning
differ from `live`.

## Optional provider-backed traced Streamlit layer

The `live` profile is the default provider-backed composition; the name does not make this
trusted-local release production-ready. To run it, fully stop the deterministic Streamlit server,
load the ignored `.env`, and start a new process:

```bash
set -a
source .env
set +a

SCHOLARPATH_RUNTIME_PROFILE=live \
LANGSMITH_TRACING=true \
SCHOLARPATH_DISCOVERY_FAILURE_MODE=you_retryable_error \
venv/bin/streamlit run streamlit_app.py
```

The typed failure injection prevents the You.com call for this process and exercises the existing
bounded Tavily fallback; it is off by default and rejected in production. Use only the synthetic
Candidate profile above even though the Supervisor results are live. The synthetic-runtime
warning must not appear in `live`.

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
| Synthetic warning is absent in `deterministic_demo` | Stop immediately; verify the process environment and perform a full Streamlit server restart before demonstrating results. |
| Supervisor details or diagnostics appear missing | Expand the relevant collapsed outcome card or one of the three exact diagnostic panels; do not change the evidence projection. |
| Profile change appears ignored | Stop the Streamlit process completely and relaunch it; browser refresh and rerun retain the cached application service. |
| Demonstration thread disappears after restart | Expected: `deterministic_demo` uses an in-memory checkpointer. Start a new synthetic run. |
| `deterministic_demo` is rejected in production | Expected safety behavior. Use it only with a non-production environment; never weaken the guard. |
| Missing provider key in `live` | Stop the traced layer and show the deterministic profile or offline journey; do not paste the key into a command. |
| LangSmith `403` | Verify endpoint region, workspace ID, key scope, and project; keep the offline release result separate. |
| Too few live profiles | Explain the bounded recoverable state; do not weaken identity, evidence, or availability rules during a demonstration. |
| Evidence remains partial | Show the retained evidence and missing categories; do not present the record as a Verified Supervisor. |
| Review limit reached | Show the safe terminal message and start a new research run with revised preferences. |
