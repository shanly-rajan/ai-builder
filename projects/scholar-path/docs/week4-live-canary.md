# Week 4: bounded live-provider canary

This is a one-profile service-integration diagnostic using real provider adapters
and a synthetic Candidate profile. It reuses the existing M13 manual pipeline;
it is **not** a persisted LangGraph execution or a live quality benchmark.

```text
Synthetic Candidate profile → live OpenAI planning → one live You.com search
  → optional Tavily search → known-profile extraction → OpenAI evidence
  → strict verification → OpenAI Research Fit → Nebius independent review
  → one proposed result → synthetic approval tested in memory only
```

## Before execution

- All required credential loaders reported configured values. No secret values
  were printed, copied, or changed.
- Public target: [Alan Woodward, University of Surrey](https://www.surrey.ac.uk/people/alan-woodward).
  On 2026-09-06 its official page was readable, and local preflight classified its
  HTTPS URL as a singular university profile. This is not a claim that the app
  has verified the profile, established supervision eligibility, or assessed fit.
- Keep the test's existing synthetic enterprise-architecture/responsible-AI
  research input. No real Candidate data or production preferences are used.
- Strict identity, current affiliation, and research-evidence gates remain intact.
- Nebius must return a successfully reconciled accepted/revised review. Production
  graceful degradation is unchanged; it is no longer a canary success.
- LangSmith tracing is explicitly disabled. No Mem0, SQLite writes, or outreach.

## Call ceilings

| Operation | Maximum logical calls | Timeout per call |
|---|---:|---:|
| OpenAI planning | 2 | At most 60 seconds |
| You.com search | 1 | At most 20 seconds |
| Tavily fallback search | 1 | At most 20 seconds |
| Tavily extraction | 1 | 20-second provider / 25-second application |
| OpenAI evidence extraction | 1 | At most 60 seconds |
| OpenAI Research Fit | 2 | At most 60 seconds |
| Nebius independent review | 1 | At most 60 seconds |

Total: at most **9 logical calls**. OpenAI and Nebius SDK retries are disabled.
Logical calls are not guaranteed billable-request counts. Tokens and monetary
cost remain unmeasured; there is no enforced currency budget or overall wall-clock
deadline. The canary stops on an unmet gate; do not keep rerunning until it passes.

## Exact command

From `projects/scholar-path`, with the project's existing ignored `.env` populated:

```bash
SCHOLARPATH_RUN_LIVE_TESTS=true \
SCHOLARPATH_RUN_LIVE_CANARY=true \
SCHOLARPATH_LIVE_CANARY_SUPERVISOR_NAME="Alan Woodward" \
SCHOLARPATH_LIVE_CANARY_INSTITUTION="University of Surrey" \
SCHOLARPATH_LIVE_CANARY_PROFILE_URL="https://www.surrey.ac.uk/people/alan-woodward" \
LANGSMITH_TRACING=false SCHOLARPATH_LOG_LEVEL=WARNING \
venv/bin/pytest -o addopts='' -q -rs -s --tb=no --show-capture=no \
  --log-level=CRITICAL -m live tests/integration/test_m13_live_canary.py
```

Settings loaders read credentials from `.env`; the command supplies only opt-ins
and public target fields. Tracebacks and captured logs are suppressed to avoid
copying raw provider exceptions into a report. The safe `live_canary.summary`
event contains counts, elapsed time, and fixed stage outcomes, not source content
or identities. The stage diagnostics were added after the first attempt below;
they cannot retroactively establish its exact failure cause.
One skipped test is **not** a passed canary.

## Step 3b: first observed result

On **2026-09-06**, the single authorized invocation returned **1 failed in
12.16 seconds** (exit code 1). Its budget summary measured **12.090 seconds**
and **four logical provider calls**:

| Operation | Actual calls | What this execution establishes |
|---|---:|---|
| OpenAI planning | 1 | A validated SearchPlan was returned and the pipeline continued. |
| You.com search | 1 | Discovery recovered the exact configured public profile. |
| Tavily fallback search | 0 | Not needed or tested in this execution. |
| Tavily extraction | 1 | Page content was returned and passed to the evidence model. |
| OpenAI evidence extraction | 1 | Invoked; completion and subsequent local verification are unconfirmed. |
| OpenAI Research Fit | 0 | Model not called. |
| Nebius independent review | 0 | Not reached; no claim of working live Nebius review. |

The attempt did **not confirm** completed verification and did not reach proposal
or approval. It made no Mem0 call, graph/shortlist persistence write, or LangSmith
upload. Tokens and cost are **unknown**, not zero. Configured OpenAI model:
`gpt-5.4-mini`; configured but unreached Nebius model:
`Qwen/Qwen3-235B-A22B-Instruct-2507`.

Raw traceback/captured-log suppression deliberately kept provider content out of
the report. The aggregate summary places the stop after the evidence-model attempt
and before any Research Fit model call. It does not distinguish provider invocation
failure, invalid structured evidence, an unmet strict verification gate, or local
Research Fit input validation before the model call. **The exact stage and cause
are unconfirmed.** Do not infer that
credentials failed or lower evidence requirements from this result alone.

No second invocation was made within step 3b. No target, prompt, timeout, or production policy
was changed to make the canary pass. Step 3c adds the offline-tested diagnostics
below; another live attempt requires separate approval.

Regression verification for this change:

- Formatting: 288 files already formatted; Ruff passed.
- Type checking: no issues in 219 source files.
- Focused review/budget checks and existing M13 contracts: **23 passed in 0.14s**.
- Complete default offline suite: **1,836 passed, 9 deselected, 78 subtests passed
  in 24.63s**, **91.74% coverage**. External sockets were blocked by test fixtures.

## Step 3c: fixed stage outcomes (offline only)

The canary now records completion explicitly at these boundaries:

```text
Evidence extraction → Strict verification → Research Fit input → Research Fit evaluation
                              │                    │
                    Missing required evidence   Invalid local input
                              └─────── stop ───────┘
```

The added `stage_outcomes` field always includes these four fixed keys. Each has
`status` (`not_reached`, `started`, `completed`, or `failed`) and `failure_category`
(null unless a caught failure has been classified). No failure is swallowed and
no additional model call is introduced. Early stops before extraction leave all
four stages `not_reached`. An interruption outside normal exception handling can
leave `started`; it is not reported as completed.

| Stage / condition | Failure category |
|---|---|
| Evidence model invocation error | `model_invocation` |
| Evidence model output error | `invalid_output` |
| Evidence extraction local validation error | `local_validation` |
| Verification returns no Verified Supervisor | `missing_required_evidence` |
| Verification contract validation or conflicting evidence-ID error | `verification_contract_invalid` |
| Research Fit input construction fails validation before any model call | `input_validation` |
| Research Fit agent reports a model failure / exhausted invalid output | `model_invocation` / `invalid_output` |
| Other Research Fit local validation error | `local_validation` |
| Unclassified exception | `unexpected_failure` |

Research Fit input is prevalidated using the existing `ResearchFitInput.from_domain`
method. This repeats only deterministic input mapping; the production agent still
owns its own validation, evidence-limited behavior, and bounded retries. An evidence
extraction stage completing means claim processing returned, not that verification
passed. A completed evaluation is not by itself proof of a model call; the separate
call counts remain authoritative for attempted invocations.

For example, this is **illustrative fake output**, not a diagnosis of the live run:

```json
{
  "evidence_extraction": {"status": "completed", "failure_category": null},
  "evidence_verification": {"status": "completed", "failure_category": null},
  "research_fit_input": {"status": "failed", "failure_category": "input_validation"},
  "research_fit_evaluation": {"status": "not_reached", "failure_category": null}
}
```

The summary serializes only fixed stage names and enum values. It never includes
exception messages, causal chains, Pydantic error details, Candidate inputs, names,
source URLs, excerpts, or API keys. Keep the traceback/log-suppression flags in the
live command: the summary is safe, but an unrestricted raw pytest traceback is not.

Run the stage regressions offline from `projects/scholar-path`:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/evaluation/test_live_canary_stages.py
```

Step 3c verification: **19 focused stage tests passed**. The complete offline suite
returned **1,855 passed, 9 deselected, 79 subtests passed in 24.95s**, with **91.78%
coverage**. Formatting, lint, and type checking passed.

This preparation does **not** prove the live failure is fixed. No new live attempt
was made for step 3c. Exact commands are recorded in the [build journal](build-journal.md).

## Step 3d: instrumented live result

On **2026-09-06**, the user authorized the next single live attempt using the exact
command above. It returned **1 failed in 9.35 seconds** (exit code 1). The safe
summary measured **9.277 seconds** and **four logical calls**:

| Operation | Calls |
|---|---:|
| OpenAI planning | 1 |
| You.com search | 1 |
| Tavily fallback search | 0 |
| Tavily extraction | 1 |
| OpenAI evidence extraction | 1 |
| OpenAI Research Fit | 0 |
| Nebius independent review | 0 |

Actual stage outcomes from this invocation:

```json
{
  "evidence_extraction": {"status": "completed", "failure_category": null},
  "evidence_verification": {"status": "failed", "failure_category": "missing_required_evidence"},
  "research_fit_input": {"status": "not_reached", "failure_category": null},
  "research_fit_evaluation": {"status": "not_reached", "failure_category": null}
}
```

Planning and exact-profile discovery completed, Tavily returned page content, and
the evidence agent finished processing claims. Verification then returned a valid
partial record, with no Verified Supervisor. The canary deliberately failed at
that gate. Research Fit input mapping, its model, Nebius, proposal, and approval
were not reached. This attempt did not stop on a typed model-invocation or
structured-output error.

At least one required evidence category was absent after grounding: **identity**,
**current affiliation**, or **research interest/publication**. The summary does not
identify which category, how many claims were retained, or why support was missing.
It cannot distinguish missing page facts, omitted model claims, and rejected
grounding. This locates the stopping gate, **not the underlying cause**, and does
not retroactively diagnose the first attempt.

**MVP scope caveat:** the canary always constructs the evidence agent with its
strict default. It does not read the application's identity-only MVP policy or
its minimum number of Verified Supervisors. This tests one profile; changing the
app's two- or three-Supervisor minimum would not fix this canary failure.

No second invocation occurred within step 3d. No Mem0, persisted graph/shortlist,
outreach, or LangSmith upload occurred. Credentials, target, prompts, code, gates,
and call/time limits were not changed for this attempt. Token usage and monetary
cost remain **unknown**, not zero. There is still no passing live quality baseline
or live Nebius result from these canary attempts.

Pre-run verification: formatting, Ruff, and mypy passed; **42 focused tests passed**.
The initial full suite caught a missing journal link for this step's new prompt.
After adding that documentation link, the complete offline suite returned
**1,855 passed, 9 deselected, 80 subtests passed in 25.77s**, **91.78% coverage**,
before the live attempt started.

The next bounded **offline** repair was to expose the verification-standard enum and only
the three allowlisted missing-evidence tokens from the partial record, optionally
with retained/grounded counts from the existing grounding function. Test each gate,
multiple missing gates, complete evidence, retained-but-ungrounded claims, privacy,
and unchanged call budgets. Do not print raw records or lower the gate. A further
live invocation remains a separate approval boundary. Step 3e implements that
diagnostic preparation below, without changing this historical live result.

## Step 3e: missing evidence and grounding counts (offline only)

`live_canary.summary` now includes `verification_diagnostics`. It is **null** if no
valid verification record was captured, including an earlier extraction failure
or failure while constructing the record. Once a record exists, the summary is
stored **before** the strict missing-evidence gate raises, so partial results are
inspectable without rerunning a model.

| Field | Meaning |
|---|---|
| `verification_standard` | The record's standard enum value, or null for an unrecognized value. The live canary remains strict. |
| `missing_required_evidence` | Canonically ordered, deduplicated subset of `identity`, `current_affiliation`, `research_interest_or_publication`. |
| `unrecognized_missing_category_count` | Number of unrecognized entries; their text is never emitted. |
| `retained_claim_counts` | Counts by the fixed `EvidenceClaimType` values. |
| `grounded_claim_counts` | Counts by those same types using the existing domain grounding check with complete evidence context. |

Interpret the counts alongside the missing categories:

```text
No verification record → verification_diagnostics: null (unknown, not all-clear)
Partial record → missing category names + counts → unchanged strict gate stops
Complete record → empty missing list + counts → existing Research Fit path
```

A retained claim is not necessarily grounded, even if its model-proposed direct
support flag is true. The diagnostic uses the domain grounding function, including
linked identity context. Positive research-interest/publication counts may satisfy
the research gate; a project count alone does not replace that strict requirement.
An empty missing list is not a global canary pass: also check the standard,
unknown-entry count, stage outcomes, and final pytest result.

Only fixed labels, numeric counts, and nullable enum values enter this projection.
No names, source URLs, claim/evidence IDs, claims, excerpts, concerns, research
statements, or raw errors are serialized. Unrecognized category values cannot
introduce arbitrary strings into the JSON.

Run the fixed-fixture checks offline from `projects/scholar-path`:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/evaluation/test_live_canary_verification.py
```

Observed offline result: **17 passed in 0.20s**. Formatting, Ruff, and mypy passed.
The complete non-live suite returned **1,872 passed, 9 deselected, 81 subtests passed
in 24.92s**, with **91.78% coverage**.

No live invocation was performed in step 3e. The exact missing categories of steps
3b/3d remain unknown; these fields are not retroactive evidence. Verification
rules, retries, timeouts, and the nine-call ceiling are unchanged. Results are
recorded in the [build journal](build-journal.md).

## Step 3f: live missing-evidence result

On **2026-09-06**, one separately approved invocation used the exact command above
with step 3e's diagnostics. It returned **1 failed in 11.31s** (exit code 1).
The summary measured **11.242s** and **four logical provider calls**: one each for
OpenAI planning, You.com search, Tavily extraction, and OpenAI evidence extraction.
Tavily fallback search, OpenAI Research Fit, and Nebius each had **zero calls**.

```text
Planning → exact-profile discovery → page extraction → evidence extraction
  → strict verification STOP: current affiliation + research evidence missing
  → Research Fit / Nebius / proposal / approval not reached
```

Evidence extraction **completed**. Verification **failed** with
`missing_required_evidence`; both Research Fit stages were `not_reached`.
The captured verification standard was `strict`, with zero unknown category entries.
The actual missing categories were `current_affiliation` and
`research_interest_or_publication`.

| Evidence type | Retained claims | Grounded claims |
|---|---:|---:|
| Identity | 1 | 1 |
| Current affiliation | 1 | 0 |
| Research interest | 8 | 0 |
| Publication | 9 | 0 |
| Methodology | 0 | 0 |
| Project | 0 | 0 |
| Availability | 0 | 0 |

Identity satisfied its gate. The other required categories were not absent from
the retained collection: they were present but did not qualify as directly grounded
evidence. This narrows the investigation to claim support/grounding, rather than
simply retrieving more results or reducing the application's Supervisor-count minimum.

The counts do **not** identify the specific rejected field or condition. They do
not distinguish a model-proposed unsupported claim from a local subject-context,
institution/department, or other grounding rejection. No raw draft, source excerpt,
or per-claim rejection reason was retained in this diagnostic. Do not claim the
Supervisor's actual affiliation or research is absent, or that a parser bug is
proven. Earlier attempts remain separate observations, not retroactively diagnosed.

The test remained at one profile with strict verification and a nine-call ceiling.
No provider configuration, source target, model prompt, gate, or retry policy changed.
No second invocation, Mem0 call, persisted graph/shortlist, outreach, or LangSmith
upload occurred. Tokens and monetary cost remain unknown. This is a **failed live
integration diagnostic**, not a completed live journey or quality baseline.

Pre-run checks passed: **59 focused tests**, formatting (**294 files**), Ruff, and
mypy (**221 source files**). The complete non-live suite returned **1,872 passed,
9 deselected, 82 subtests passed in 25.37s**, with **91.78% coverage**.

Next bounded step: inspect and reproduce the **current-affiliation grounding gate
offline first**, using fixed official-profile layouts and fake structured claims.
Compare directly supported fields, excerpt matching, and same-page identity context;
preserve negative cases for unrelated people and invented affiliations. A repair
requires a reproduced defect, not just these counts. Research-interest/publication
grounding remains the second known gap. No gate relaxation or new live run is included.

Read-only inspection found a concrete **hypothesis to reproduce**, not a confirmed
live cause: `extract_claims` admits excerpts after case/whitespace normalization,
while `_exact_excerpt_is_under_expected_profile_subject` searches raw page text.
Start with a formatting-only fixture in
`tests/unit/agents/test_official_profile_evidence_context.py`, including other-person
and invented-affiliation rejection controls. Do not broaden identity binding or
label the live failure fixed without that reproduction.

## Interpretation and remaining work

A successful result establishes only this one configured pipeline execution.
Search must recover the exact configured profile within three results per provider.
You.com transport errors stop this canary; graph-level timeout/fallback remains
covered separately. Extraction is capped at 20,000 characters with no alternate
page attempt. These constraints may expose a useful failure before Nebius is reached.

Live Mem0 isolation, real graph interrupts/resume, live trace privacy, human-rated
relevance, tokens/cost, the reviewed golden dataset, and before/after improvements
remain separate work. An application fallback is not evidence that its upstream
provider succeeded; structured output still needs validation and refusal/error
handling, as described in [OpenAI's structured-output documentation](https://developers.openai.com/api/docs/guides/structured-outputs).
