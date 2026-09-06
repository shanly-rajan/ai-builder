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
SCHOLARPATH_CAPTURE_GROUNDING_REPLAY=false \
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

## Step 3g: formatting-only grounding repair (offline)

The Candidate requested a commit checkpoint before the next repair. Accumulated
steps 3b–3f are committed as `268600b` (`test: add bounded live canary diagnostics
and record results`). No push occurred. This repair is a separate change.

Fixed official-profile fixtures reproduced a local defect: case-only, tab, newline,
non-breaking-space, and repeated-space differences were accepted by excerpt admission
but rejected by raw-text context positioning. All **five reproductions failed before
the repair**, although the affiliation claims were retained.

The matching path now uses the same case/whitespace normalization as admission,
with a mapping back to original character positions:

```text
Original page → normalized text + original offsets → all matching excerpts
  → original preceding person headings → unchanged identity/affiliation checks
```

Original text, source URLs, retrieval timestamps, and retained excerpts are not
rewritten. Every normalized occurrence is checked, including differently formatted
duplicates; an occurrence beneath another recognized person heading remains a
rejection. Unicode casefold expansions preserve their original source offsets.
Punctuation and word changes are not treated as formatting equivalents.

A new negative test also exposed unsupported model drafts entering context-link
construction and raising validation errors. The branch now requires the provisional
claim's direct-support flag, so an unsupported claim remains unsupported without
fabricating an identity link or crashing this path.

Twenty offline regression cases were added to the existing official-profile context
suite. The suite returned **123 passed in 0.34s** after repair. It checks all required
strict gates, grounded identity, wrong-person/ambiguous-repeat rejection, absent or
invented affiliation fields, unsupported drafts, original provenance, and availability
remaining `not_stated`. A complete fixture now verifies without weakening any gate.

For a quick offline demonstration, from `projects/scholar-path`:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/agents/test_official_profile_evidence_context.py -k normalized_affiliation_excerpt
```

This proves and repairs a **local formatting defect**. It does not prove that defect
caused step 3f's live failure; the raw live page/drafts were not retained. No live
canary, new model call, prompt change, heading-heuristic redesign, or gate relaxation
was performed here. Other affiliation/research grounding failures remain possible.
Complete quality results are recorded in the [build journal](build-journal.md).

Full offline verification: **1,892 passed, 9 deselected, 83 subtests passed in
24.86s**, **91.78% coverage**. Formatting, Ruff, and mypy passed. The new repair
is left uncommitted for review, separate from the accumulated-work checkpoint.

## Step 3h: post-repair live result

On **2026-09-06**, one separately approved invocation used the same command and
public target with step 3g's formatting repair present. It returned **1 failed in
11.11s** (exit code 1). The safe summary measured **11.04s** and **four logical calls**:
OpenAI planning, You.com search, Tavily extraction, and OpenAI evidence once each.
Tavily fallback search, OpenAI Research Fit, and Nebius each had zero calls.

Evidence extraction **completed**. Verification **failed** with
`missing_required_evidence`; both Research Fit stages were `not_reached`.
The standard remained `strict`, unknown category entries were zero, and the exact
missing categories were again `current_affiliation` and
`research_interest_or_publication`.

| Evidence type | Retained claims | Grounded claims |
|---|---:|---:|
| Identity | 1 | 1 |
| Current affiliation | 1 | 0 |
| Research interest | 1 | 0 |
| Publication | 2 | 0 |
| Project | 1 | 0 |
| Methodology | 0 | 0 |
| Availability | 0 | 0 |

The stopping gates are unchanged from step 3f. Six claims were retained, versus
nineteen in that earlier run, but only identity was grounded in either execution.
These counts are observations, not a controlled quality comparison. A project claim
does not replace the strict research-interest/publication requirement.

Step 3g remains a reproduced and tested local repair, but this run did **not**
demonstrate successful live verification. The summary does not reveal whether the
normalization branch was reached, a model draft was marked unsupported, a typed
affiliation field was absent, or a subject-context check rejected the excerpt.
Do not infer that the source lacks the facts, that credentials failed, that the
formatting repair caused the count change, or that relaxing a cohort minimum helps.

No second invocation, new implementation, prompt/model change, relaxed gate,
credential edit, Mem0 call, persisted graph/shortlist, outreach, or LangSmith upload
occurred. No Verified Supervisor, proposal, or approval was reached. Tokens/cost
remain unknown, and there is still no live Research Fit/Nebius result from these runs.

Pre-run verification passed: **182 focused tests in 0.61s**; formatting (**296 files**),
Ruff, and mypy (**221 source files**). Complete offline suite: **1,892 passed,
9 deselected, 84 subtests passed in 24.96s**, **91.78% coverage**.

Next bounded **offline** preparation: expose fixed, aggregate rejection-reason codes
at the existing claim-support/context checks, reusing their actual decisions rather
than recreating the validator. Distinguish unsupported model flags, unmet typed-field
requirements, and subject/context failures without recording names, excerpts, IDs,
URLs, or raw errors. Test those reasons and privacy with fakes before any further
approved live call. No new heuristic or verification-policy change is justified
by this aggregate result alone.

## Step 3i: retained-claim grounding diagnostics (offline)

The manual canary now includes `grounding_diagnostics` in its safe JSON summary.
It is `null` until extraction completes; a completed extraction with no retained
claims reports zero counts instead. The summary survives a later strict-verification
or Research Fit failure. No additional provider call or retry is introduced.

```text
Retained claim -> existing direct-grounding checks
                         |
                  existing context rescue, if eligible
                         |
                  final success OR one failure reason
                         |
                  claim-type / reason counts only
```

The boolean grounding API now delegates to the same reason-returning predicate;
it does not maintain a second validator. The optional extraction collector exists
only for that invocation, not on the Agent or in durable graph state.

| Example reason | Meaning of the existing failed check |
| --- | --- |
| `model_not_directly_supported` | The original retained model draft was marked unsupported. |
| `grounded_identity_missing` | A dependent draft had no grounded identity from the page. |
| `profile_source_ineligible` | Context rescue requires an official person-profile source kind. |
| `profile_route_ineligible` | Context rescue requires a singular person-profile URL route. |
| `profile_subject_mismatch` | The existing page-position/heading check did not bind the excerpt to the expected person. |
| `profile_identity_context_invalid` | The existing linked-identity/context predicate failed. |
| `institution_not_in_excerpt` / `department_not_in_excerpt` | A typed affiliation value was not explicitly present in the subject-bound excerpt. |

Other fixed domain reasons cover absent name/excerpt/affiliation fields, ownership
and name mismatch, missing identity-name text, unsupported subject, and availability
polarity. These report failed predicates, **not proven facts about the Supervisor**.

For each claim type, `retained_claim_counts` equals `grounded_claim_counts` plus
the sum of `rejection_counts`. Each retained claim contributes exactly one final
outcome. A successful contextual rescue does not count its initial direct-subject
failure. If rescue is ineligible, a more specific existing direct-claim failure
is preserved; otherwise the first failed rescue gate is reported.

Important scope: these counters describe claims **after deduplication and admission,
before verification-record conflict merging**. Invalid drafts, excerpts absent from
the page, and ambiguous availability discarded at admission are not counted.
For example, a directly-supported affiliation draft missing a required typed field
is discarded before these counters; its absence cannot be diagnosed from a zero
count. `affiliation_fields_missing` remains available to direct domain callers.

No names, Candidate data, evidence IDs, excerpts, URLs, page content, API keys,
or exception text enter the collector. It accepts enum values only and exports
detached count dictionaries. These counts are not added to trace metadata.

### 60-second offline demonstration

From `projects/scholar-path`, run:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/domain/test_grounding_failure_reasons.py tests/unit/agents/test_grounding_diagnostics.py tests/unit/evaluation/test_live_canary_grounding.py
```

The fixed examples cover reasons, contextual success, privacy, identical evidence
and verification with diagnostics enabled/disabled, and unchanged fake call counts.
They do not call live providers or prove the cause of step 3h's live failure.

Validation on **2026-09-06**: 57 new diagnostic tests; the focused set plus M6
contract passed **65 tests in 0.24s**. Full non-live suite: **1,949 passed,
9 deselected, 85 subtests in 24.87s**, **91.86% coverage**. Ruff formatting/lint,
mypy (224 files), and the independent diff review passed.

Next boundary: **one separately approved live canary** to observe actual reason
counts, then decide whether a specific offline repair is supported. No live rerun,
model/heuristic change, or relaxed verification gate is part of step 3i.

## Step 3j: live grounding-reason result

On **2026-09-06**, the single approved invocation of the exact command above
returned **1 failed in 10.33s**, exit code 1. The safe summary measured **10.249s**.
It used four logical calls: OpenAI planning, You.com search, Tavily extraction,
and OpenAI evidence extraction once each. Tavily fallback, OpenAI Research Fit,
and Nebius were **not called**. No second invocation was made.

Evidence extraction completed, but strict verification failed with
`missing_required_evidence`: `current_affiliation` and
`research_interest_or_publication`. Both Research Fit stages were `not_reached`.
There were no unrecognized missing-category values.

| Claim type | Retained | Grounded | Final rejection reasons |
| --- | ---: | ---: | --- |
| Identity | 1 | 1 | None |
| Current affiliation | 1 | 0 | `profile_identity_context_invalid`: 1 |
| Research interest | 1 | 0 | `profile_subject_mismatch`: 1 |
| Publication | 6 | 0 | `profile_subject_mismatch`: 6 |
| Methodology | 0 | 0 | None retained |
| Project | 0 | 0 | None retained |
| Availability | 0 | 0 | None retained |

The extraction counters and final verification counters agree in this run.
Nine claims were retained; identity was grounded and the remaining eight have
one recorded rejection each. Missing availability was not the blocking gate.

### What is now established

- This run reached local subject/context checks, rather than stopping on an
  evidence-model invocation or structured-output exception.
- The affiliation claim reached contextual validation and failed the existing
  linked-identity/context predicate. The code is deliberately coarse: it does not
  report which nested reference/subject condition failed.
- The research-interest and six publication claims failed the existing page-position
  subject check. That is not proof that the text really concerns someone else;
  the heading recognizer can itself require investigation.
- Code-path inspection narrows those seven failures to a recognized preceding
  heading that did not match the expected person at at least one excerpt occurrence:
  admission had already found the nonempty excerpt using the same normalization.
  The summary cannot distinguish a genuine different person from a false-positive
  role or section heading. All eight rejected retained claims reached contextual
  rescue with model support and a grounded identity available.
- No retained draft was reported as `model_not_directly_supported` or
  `grounded_identity_missing`. This says nothing about drafts dropped at admission.
- No Verified Supervisor, Research Fit assessment, independent review, proposal,
  or approval was reached. Tokens and cost remain unknown.

This is not proof of a parser defect, a missing real-world affiliation, or the
cause of any historical attempt. No raw page/model output was retained. Structured
output can still contain mistakes; schema compliance is not source grounding, as
noted in [OpenAI's guidance](https://developers.openai.com/api/docs/guides/structured-outputs#handling-mistakes).

Next bounded step: reproduce **profile subject binding** offline with fixed examples
for both observed categories. Pair owner-profile headings, role/navigation text,
and contextual affiliation examples with genuine other-person and multi-person
negative controls. Change only a demonstrated false rejection; do not disable
subject checks, infer missing facts, or rerun providers to obtain a green result.
The exact live excerpt/heading that triggered these checks is still unknown.

Pre-run checks: formatting **301 files**, Ruff passed, mypy **224 files**;
focused tests **72 passed in 0.25s**. Full non-live suite: **1,949 passed,
9 deselected, 86 subtests in 25.09s**, **91.86% coverage**.
Credential presence was checked without printing/changing values. No new runtime
code, test, model/prompt, heuristic, policy, credential, commit, or push in step 3j.
No Mem0, durable graph/shortlist write, outreach, or LangSmith upload occurred.

## Step 3k: fixed-fixture profile-subject repair (offline)

The follow-up reproduced **two local false-rejection patterns** without another
provider call. These are synthetic regression examples, not captured live excerpts.

| Exact fixture text | Before repair | Narrow change |
| --- | --- | --- |
| `Academic Background`, `Research Overview`, `Research Publications` | The preceding-heading matcher treated each label as a different person. | Add only these three exact labels to the existing section-heading allowlist. |
| `Professor Of Computer Science`, `Professor In Information Systems` | The conflict detector interpreted a role as a titled person's name. | Exclude whole-word `of/in` immediately after `Prof/Professor`, including optional period/whitespace. |

```text
Exact source excerpt + grounded profile owner
  -> skip a known section label / distinguish role text from a person
  -> still check actual other people and repeated excerpt positions
  -> existing strict affiliation + research gates
```

The agent-level baseline was **5 failed, 14 passed in 0.26s**. A separate domain
set produced **8 failed, 3 passed in 0.02s**, including abbreviation/newline roles
and direct versus contextual affiliation. The five-module regression run after
the patch passed **204 tests in 0.64s**.

Thirty new tests cover these repairs and negative controls. A real other-person
heading remains a barrier even when followed by a newly recognized section label.
Another titled person after role text in the same excerpt remains a conflict.
The role lookahead uses word boundaries: `Professor Ines Smith`, `Prof Ofelia Stone`,
and the separate `Dr` name branch are not removed from person detection. Unknown
title-cased labels, different-person repeated excerpts, unsupported model claims,
ineligible sources/routes, and missing typed affiliation fields still fail.

No factual text or provenance is rewritten. Diagnostic-on/off claims, deterministic
IDs, and verification records match; each extraction makes one fake model call.
Existing ID derivation remains unchanged (newly grounded claims naturally reflect
their corrected support/context flags). Availability stays `not_stated` when absent.
Strict identity, current affiliation, and research evidence requirements remain.

### 60-second offline demonstration

From `projects/scholar-path`, run:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/agents/test_profile_subject_binding_regressions.py tests/unit/domain/test_academic_role_grounding.py
```

Expect **30 passed**: the owner-profile examples reach strict verification, while
the other-person and unsupported-evidence controls remain rejected. This is not a
live Research Fit/Nebius run or a claim that the previous live failure is resolved.

Verified on **2026-09-06**: the command returned **30 passed in 0.25s**. Full
non-live suite: **1,979 passed, 9 deselected, 87 subtests in 25.17s**,
**91.86% coverage**. Ruff formatting/lint and mypy (226 files) passed, as did
the independent scoped diff review.

Limitations: the allowlist is finite and English-specific. The pre-existing broad
academic-role heading pattern can ignore a compound role heading containing another
name; it is unchanged and remains separate debt. No source eligibility, excerpt
prefix rule, graph route, model/prompt, provider limit, or credential was changed.

Next boundary is one separately approved live observation with the same target
and safe counters; do not rerun automatically or infer historical causality from
these fixed fixtures. No live call, trace upload, commit, or push in step 3k.

## Step 3l: post-subject-repair live result

On **2026-09-06**, one separately approved invocation of the unchanged command
returned **1 failed in 7.06s**, exit code 1; safe measured elapsed time **6.992s**.
It used **four logical calls**: OpenAI planning, You.com search, Tavily extraction,
and OpenAI evidence extraction once each. Tavily search, OpenAI Research Fit,
and Nebius were **not called**. No second invocation was made.

Evidence extraction completed. Strict verification failed with
`missing_required_evidence`: `current_affiliation` and
`research_interest_or_publication`. Both Research Fit stages were `not_reached`;
the unrecognized missing-category count was zero.

| Claim type | Retained | Grounded | Final rejection reasons |
| --- | ---: | ---: | --- |
| Identity | 1 | 1 | None |
| Current affiliation | 1 | 0 | `profile_identity_context_invalid`: 1 |
| Research interest | 1 | 0 | `profile_identity_context_invalid`: 1 |
| Publication | 1 | 0 | `profile_subject_mismatch`: 1 |
| Project | 1 | 0 | `profile_subject_mismatch`: 1 |
| Availability | 1 | 0 | `profile_identity_context_invalid`: 1 |
| Methodology | 0 | 0 | None retained |

Extraction and final verification counts agree: six retained claims, one grounded,
five rejected. The availability claim was not grounded and was **not** a required
verification gate. Its presence does not establish supervision availability.

The three context failures locate the existing linked-identity/context predicate,
not its specific nested condition. The other two failures locate the existing
page-position/heading subject check, not the exact offending heading. No raw page,
model response, evidence ID, or exception text was retained in these diagnostics.

This run **did not establish live success after step 3k**. Nor does it show that
the fixture-proven repair caused a regression: the model output is stochastic and
the previous source/drafts were not retained for a controlled replay. Strict
verification was reached but failed; Research Fit, Nebius review, proposal, and
approval were not reached. Tokens and cost remain unknown.

Pre-run checks passed: Ruff formatting **305 files**, lint, mypy **226 files**;
focused regressions **43 passed in 0.32s**; full non-live suite **1,979 passed,
9 deselected, 88 subtests in 25.14s**, **91.86% coverage**. Credential presence
was checked without printing or changing values. A read-only independent audit
confirmed the nine-call ceiling, strict policy, and interpretation of the result.

### Next boundary

No exact production repair is supported by these aggregate counts yet. The next
proposed step is an **offline refinement of the existing linked-identity/context
failure diagnostic** into fixed subreasons, with synthetic examples proving
unchanged validation decisions, provenance, privacy, and call counts. Reuse the
existing predicate; do not create a second validator or expand heading exceptions.
Do not automatically rerun the canary or relax evidence gates.

Step 3l changed documentation only. No runtime/test, model/prompt, policy, or
credential change; no commit, push, Mem0 call, durable graph/shortlist write,
outreach, or LangSmith upload. A later live observation needs separate approval.

## Step 3m: precise context-failure diagnostics (offline)

The coarse `profile_identity_context_invalid` outcome now reports the first
failing condition inside the **existing** linked-identity/context checks. It is a
diagnostic change, not a verification repair. The old enum value remains readable
for historical summaries; new evaluations emit the more precise reason.

```text
Retained claim attempting official-profile context
  -> resolve linked identity and match source details
  -> check identity against this Supervisor
  -> reject conflicting-person text / check existing subject pattern
  -> existing affiliation fields or availability polarity checks
  -> success OR one fixed failure code in the existing count summary
```

| New reason family | Existing check being reported |
| --- | --- |
| `context_identity_reference_missing`, `context_identity_not_found`, `context_identity_type_mismatch` | A reference must resolve to identity evidence. |
| `context_identity_not_directly_supported` | The referenced identity must be directly supported. |
| `context_supervisor_id_mismatch`, `context_source_kind_mismatch`, `context_source_url_mismatch`, `context_retrieval_time_mismatch` | Claim and identity must share the existing ownership/source/retrieval context. |
| `context_identity_reference_chained` | Identity evidence must not itself reference another identity. |
| `context_identity_name_missing`, `context_identity_excerpt_missing`, `context_claim_name_missing` | Required context fields must exist. |
| `context_identity_name_not_in_excerpt`, `context_identity_name_mismatch`, `context_identity_not_grounded` | Identity wording and the complete name must pass the existing checks. |
| `context_conflicting_person` | The existing matcher found another-person text in the excerpt; this is a matcher result, not proof about the source. |
| `context_subject_pattern_missing` | The excerpt did not match an existing pronoun or claim-type section prefix. This is distinct from the page-heading check. |

Ineligible sources and routes retain their existing `profile_source_ineligible`
and `profile_route_ineligible` codes. Some missing-field/reference branches are
defensive helper checks: outer schema/grounding guards can reject them earlier.
An absent optional link does not invalidate an otherwise grounded direct statement.
An **explicit invalid link** still cannot be bypassed by a direct statement.

Availability derivation and grounding share the same reason-returning helpers
through boolean wrappers. No second validator, new matching rule, heading exception,
source normalization, or altered check order was introduced. Current affiliation
retains its existing subject-prefix exemption, but still requires no conflicting
person and both explicit typed affiliation fields. Availability polarity remains
a separate existing check.

The collector, canary summary schema, and provider call limits are unchanged.
Only fixed enum labels and aggregate counts are recorded. Successful context rescue
still records success, not its initial direct-subject failure; original unsupported
model flags still take precedence. Counts still exclude drafts lost at admission.

This work cannot assign subreasons retrospectively to step 3l's three context
failures. No raw historical source/draft was retained, and no live call was made.
The page-subject mismatch branch is unchanged. Only a separately approved future
observation could show which subreason occurs in a new live response.

### 60-second offline demonstration

From `projects/scholar-path`, run:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/domain/test_profile_context_failure_reasons.py tests/unit/agents/test_profile_context_diagnostics.py tests/unit/evaluation/test_live_canary_context_diagnostics.py
```

These fixed examples check reason specificity, unchanged accepted/rejected cases,
evidence/provenance preservation, privacy, and fake-only call budgets. Test results
on **2026-09-06**: **115 passed in 0.28s**. Full non-live suite: **2,094 passed,
9 deselected, 89 subtests in 25.43s**, **91.95% coverage**. Ruff formatting/lint
and mypy (229 files) passed. The prior 210 grounding tests passed before and after
the refactor. An independent comparison of 1,426 fixed valid/malformed combinations
found all 4,278 grounding/reference/availability outcomes unchanged, using the
original boolean orchestration with current matching-policy helpers.

No model/prompt, verification policy, credential, commit, push, or trace upload is
part of step 3m. A future live run would exercise the new diagnostics, not a changed
verification policy; success is not expected merely from adding reason codes.

## Step 3n: live precise-context result

On **2026-09-06**, one separately approved invocation of the unchanged canary
returned **1 failed in 10.20s**, exit code 1. The safe summary measured **10.125s**.
Four logical calls were used: OpenAI planning, You.com search, Tavily extraction,
and OpenAI evidence extraction once each. Tavily search, OpenAI Research Fit,
and Nebius were **not called**. No second invocation was made.

Extraction completed. Strict verification failed with `missing_required_evidence`:
`current_affiliation` and `research_interest_or_publication`. Both Research Fit
stages were `not_reached`; the unknown missing-category count was zero.

| Claim type | Retained | Grounded | Final rejection reasons |
| --- | ---: | ---: | --- |
| Identity | 1 | 1 | None |
| Current affiliation | 1 | 0 | `context_conflicting_person`: 1 |
| Research interest | 1 | 0 | `context_subject_pattern_missing`: 1 |
| Publication | 4 | 0 | `profile_subject_mismatch`: 4 |
| Methodology | 0 | 0 | None retained |
| Project | 0 | 0 | None retained |
| Availability | 0 | 0 | None retained |

Extraction and final verification counters agree: **seven retained, one grounded,
six rejected**. Availability was optional and not the blocking gate; no claim
about accepting or not accepting Candidates follows from its absence.

### What the new reasons establish

- The affiliation and research-interest claims passed the linked-identity/source
  checks, then failed **excerpt-level subject checks**. Missing identity links or
  mismatched source details were not their recorded failure.
- The affiliation excerpt triggered the existing conflicting-person matcher. That
  does not prove it names a different person: a role/name false positive remains
  possible. The subsequent explicit institution/department checks were not reached
  for that claim, so their validity is not established by this result.
- The research-interest excerpt matched neither an existing contextual pronoun
  nor an allowed research-section prefix. This is a wording/subject-pattern check,
  not a finding that the Supervisor lacks research interests.
- Four publication claims failed the **separate page-position/preceding-heading
  subject check**. The actual headings and excerpts remain unknown.

No Verified Supervisor, Research Fit assessment, independent review, proposal, or
approval was reached. Tokens and cost remain **unknown**, not zero. New reason
codes describe this invocation only, not the exact cause of earlier attempts.
Structured output can still contain mistakes, as noted in
[OpenAI's guidance](https://developers.openai.com/api/docs/guides/structured-outputs#handling-mistakes);
neither schema compliance nor a successful provider call establishes source grounding.

### Next boundary

Prioritize the mandatory **affiliation excerpt/person-match gate** for bounded
offline reproduction, retaining genuine other-person negative controls. Then assess
the research-interest subject-pattern gap separately; publication-heading matching
need not be changed to satisfy a genuine identity + affiliation + research-interest
verification. Do not add arbitrary name/heading/prefix exceptions or weaken gates.

One specific research-pattern fixture gap is worth testing: existing examples allow
a preceding `Research Overview` heading but start the extracted excerpt at
`Research interests: ...`. An excerpt including that heading exercises a different
prefix check. Compare those boundaries with wrong-person controls before deciding
whether any narrow consistency repair is justified. This is a code-level hypothesis,
not the observed wording of this live response.

The diagnostic alone does not identify an exact repair. A representative fixed
example can expose a local defect, but establishing this live cause requires a
minimal, source-backed failing excerpt and expected subject for replay. Obtaining
new live payloads would require a separately scoped privacy decision; it is not
authorized by this count-only observation. No automatic capture or live rerun.

Pre-run checks: Ruff formatting **310 files**, lint passed, mypy **229 files**;
focused tests **122 passed in 0.32s**. Full non-live suite: **2,094 passed,
9 deselected, 90 subtests in 25.59s**, **91.95% coverage**. Credential presence
was checked without displaying or changing values. Independent read-only review
confirmed the limits and the interpretation of this result.

Documentation only changed in step 3n. No runtime/test, model/prompt, policy,
credential, commit, or push change. No Mem0, durable graph/shortlist write, outreach,
or LangSmith upload. Quality, reviewed dataset, cost, and submission gaps remain open.

## Step 3o: excerpt-boundary repair (offline)

On **2026-09-06**, fixed examples reproduced two local false rejections before
any production edit. They are not replays of step 3n's unretained live payload.

| Fixed case | Before repair | Bounded repair |
| --- | --- | --- |
| Complete owner `Professor Alex James Morgan` in affiliation evidence | Matcher stopped at `Professor Alex James`, reporting a different person. | Capture remaining name tokens on the same line, then use unchanged complete-name equivalence. |
| `Research Overview` included in the research excerpt | Failed the subject-prefix check, or treated the heading before `My work ...` as another person. | Ignore exactly one initial, delimited heading in a validation-only view; the body must still satisfy existing subject checks. |

```text
Exact retained excerpt -> narrow validation-only boundary handling
  -> existing identity, source, person, and claim-type checks
  -> strict verification only when all required evidence is grounded
```

The name repair preserves the existing first-two-token whitespace handling,
including wrapped unrelated names. Additional tokens use horizontal whitespace so
the next line's section heading is not swallowed into a name. Exact name matching,
surname requirements, and `Professor Of/In ...` role exclusions are unchanged.

The wrapper rule applies only to research-interest claims. It accepts the exact
`Research Overview` label followed by a colon or newline, optionally prefixed by a
Markdown heading marker. It removes at most one wrapper for validation, not storage.
Unknown/heading-only/nested wrappers, generic unsupported bodies, and genuine
other-person text remain rejected. It does not extend methodology, publication,
project, or availability prefixes. Page-position/preceding-heading checks remain
unchanged, including their repeated-excerpt wrong-person control.

Original excerpts, asserted fields, URLs, source kinds, timestamps, and claim text
are preserved. Evidence ID derivation, diagnostic schema/privacy, provider call
caps, and approval rules are unchanged. Support changes can naturally change a
derived evidence ID; enabling diagnostics does not change any evidence ID or result.
Availability is still optional and remains `not_stated` in the successful fixture.

### Reproduction and 60-second offline demonstration

From `projects/scholar-path`, run:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/domain/test_affiliation_person_excerpt_regressions.py tests/unit/agents/test_research_overview_excerpt_boundaries.py
```

Before repair: affiliation **6 failed, 11 passed**; research boundary **6 failed,
16 passed**. After repair and added boundary controls: **50 passed in 0.37s**.
The combined fixture passes strict identity + affiliation + research verification;
substituting a same-prefix different person fails affiliation. Diagnostic-on/off
runs preserve identical records and use exactly one fake extraction-model call each.
No network access is needed. Full non-live suite: **2,144 passed, 9 deselected,
91 subtests passed in 25.99s**, **91.95% coverage**. Ruff formatting/lint and mypy
(231 files) passed. See the [build journal](build-journal.md) for commands and audits.

### Remaining boundary

These tests establish two code defects and their local repairs, not the wording or
cause of the historical live result. No live canary, credential access/change, raw
payload capture, model/prompt tuning, commit, push, or trace upload occurred here.
The separate publication-heading failures and pre-existing compound-role heading
limitation were not changed. Research Fit/Nebius live success, reviewed labels,
quality/cost comparison, and submission gaps remain open.

Next is a separately approved bounded live observation using the existing safe
summary and call limits, not automatic repeated runs. If the same failures persist,
an exact source-backed minimal replay needs a separate privacy-scoped decision;
do not keep adding speculative matcher exceptions from counts alone.

## Step 3p: post-excerpt-repair live result

On **2026-09-06**, one approved invocation of the unchanged command returned
**1 failed in 15.62s** (exit code 1); safe elapsed time was **15.555s**.
No second invocation was made. Four logical calls were used: OpenAI planning,
You.com search, Tavily extraction, and OpenAI evidence extraction once each.
Tavily search, OpenAI Research Fit, and Nebius were **not called**.

```text
Planning -> exact-profile discovery -> page retrieval -> evidence extraction
  -> strict verification: STOP (affiliation + research evidence not grounded)
  -> Research Fit / Nebius / proposal / approval: not reached
```

Evidence extraction completed. Verification failed `missing_required_evidence`
for `current_affiliation` and `research_interest_or_publication`; unknown missing
category count was zero. Research Fit input/evaluation remained `not_reached`.

| Claim type | Retained | Grounded | Final rejection reason |
| --- | ---: | ---: | --- |
| Identity | 1 | 1 | None |
| Current affiliation | 1 | 0 | `context_conflicting_person`: 1 |
| Research interest | 1 | 0 | `context_subject_pattern_missing`: 1 |
| Publication | 5 | 0 | `profile_subject_mismatch`: 5 |
| Methodology, project, availability | 0 each | 0 each | None retained |

Extraction and final-verification counts agree: **eight retained, one grounded,
seven rejected**. The affiliation/research claims passed linked-identity/source
checks before their recorded excerpt-level failure. Later typed affiliation-field
checks were not reached. No availability statement was retained; availability is
optional and did not block this canary.

### What this does and does not establish

The mandatory rejection labels match step 3n; the number of rejected publications
changed from four to five. No source/model payload was retained, so this does not
show that either fixed step 3o case occurred in the live response, prove a
regression, or reveal an exact wrong person or unsupported source fact. Passing
the 50 new regressions remains local evidence for those fixtures only.

There is still no successful strict live verification, Research Fit model call,
or Nebius review from this canary series. No proposal or synthetic approval was
reached. Tokens and monetary cost remain **unknown**, not zero.

### Next boundary: minimal replay, not more blind tuning

Stop making matcher changes from aggregate reasons alone. The next proposed step
needs an exact, minimal source-backed failing example: rejected affiliation and
research excerpts, expected subject, necessary section context, and the matcher
output. Prefer a previously available sanitized sample. Any new live capture needs
a separately agreed privacy scope; do not automatically save raw provider output,
full page content, Candidate input, or credentials. No such capture was performed
in this step, and no further live call is authorized by this result.

Strict verification, publication-heading rules, target, prompts, model settings,
and call limits were unchanged. No runtime/test edits, credential changes, Mem0,
durable graph/shortlist writes, outreach, trace uploads, commits, or pushes.

Pre-run checks: Ruff formatting **314 files**, lint passed, mypy **231 files**;
focused tests **75 passed in 0.42s**. Full offline suite: **2,144 passed,
9 deselected, 92 subtests passed in 25.62s**, **91.95% coverage**. All required
credential roles reported configured without exposing values. Independent
read-only review confirmed execution limits and privacy boundaries.

## Step 3q: private excerpt-replay preparation

On **2026-09-06**, steps 3g–3p were checkpointed as `af115b6`. The next bounded
change prepares a **default-off diagnostic**, not another matcher repair or live
experiment. All examples tested in this step are synthetic. No real excerpt was
captured, no provider was called, and the strict live verification failure remains
unresolved.

```text
Existing evidence check -> unchanged rejection / unchanged verification outcome
                       -> optional observer -> private local file (max 2 excerpts)
                                             -> offline excerpt replay -> counts
```

### Capture and privacy boundaries

- Only `context_conflicting_person` or `context_subject_pattern_missing`, and
  only the first eligible affiliation/research excerpt per type (two total).
- Each sample keeps exact excerpt text (maximum 1,200 characters), expected and
  asserted Supervisor names, clean official HTTPS source URL/kind, claim type,
  and observed reason. Full pages, claim prose, complete model outputs, Candidate
  data, evidence IDs, and other claim types are not included.
- Oversized or suspicious fields are excluded, **not truncated or rewritten**.
  Recognizable email/credential patterns and source URLs with credentials,
  queries, or fragments are rejected. This is data minimization, not a universal
  personal-data detector: review artifacts privately before any sharing.
- Files are limited to 16 KiB under ignored `artifacts/grounding-replays/` with
  random filenames and `0600` permissions. The private directory is `0700`.
  Symlink paths and overwrites are rejected; existing unrelated artifacts remain
  untouched. No eligible sample means no file. This secure IO targets macOS/Linux
  and fails closed if the required filesystem capabilities are unavailable.
- The observer cannot change evidence, strict gates, or provider-call counts.
  Capture failure is nonfatal. The normal `live_canary.summary` stays aggregate;
  the additional opt-in event reports only status, counts, and a random filename.
  No replay payload is added to traces or application logs.

### Future single capture: explicit approval required

Do **not** use this command as an automatic retry. After separately approving
one live capture, run from `projects/scholar-path` with the existing credentials
configured locally. All three opt-ins must be present in the process environment;
placing the capture flag in `.env` alone does not enable it.

```bash
SCHOLARPATH_RUN_LIVE_TESTS=true \
SCHOLARPATH_RUN_LIVE_CANARY=true \
SCHOLARPATH_CAPTURE_GROUNDING_REPLAY=true \
SCHOLARPATH_LIVE_CANARY_SUPERVISOR_NAME="Alan Woodward" \
SCHOLARPATH_LIVE_CANARY_INSTITUTION="University of Surrey" \
SCHOLARPATH_LIVE_CANARY_PROFILE_URL="https://www.surrey.ac.uk/people/alan-woodward" \
LANGSMITH_TRACING=false SCHOLARPATH_LOG_LEVEL=WARNING \
venv/bin/pytest -o addopts='' -q -rs -s --tb=no --show-capture=no \
  --log-level=CRITICAL -m live tests/integration/test_m13_live_canary.py
```

The existing provider caps, target, strict policy, timeout clamps, and synthetic
Candidate remain unchanged. A canary failure may still produce a private sample;
capture itself is **not** a successful live verification result. If a sample is
written, use only its emitted random filename for the next offline step:

```bash
venv/bin/python -m scripts.replay_grounding artifacts/grounding-replays/REPLACE-WITH-FILENAME.json
```

This command prints only counts and calls no model or network. `matched_count`
means the original **rejection reason was reproduced**, not that a claim passed.
Exit `0` means every captured reason was reproduced, `1` means a reason changed,
and `2` means a safe argument/read/validation failure. The Python-only
`replay_details()` helper offers private matcher-family/matched-span inspection;
its derived text must not be pasted into public logs or traces.

If an older strict editable installation cannot import the new module, refresh
its local package links without downloading or changing dependencies:

```bash
venv/bin/python -m pip install -e . --no-deps --no-build-isolation --config-settings editable_mode=strict
```

Replay covers the excerpt-subject check only. It cannot reconstruct historical
model output or prove page admission, affiliation fields, full verification,
availability, or Research Fit. A later source-backed correction still needs
negative controls and the normal regression suite.

Offline checks for this preparation:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/evaluation/test_grounding_replay.py tests/unit/evaluation/test_private_canary_replay.py
```

No live execution is needed for these tests. See the
[build journal](build-journal.md#week-4-step-3q--checkpoint-and-private-excerpt-replay-preparation-2026-09-06)
for final full-suite results. The new diagnostic work is not part of checkpoint
`af115b6`; no second commit or push was made in this step.

## Step 3r: live capture and offline replay result

On **2026-09-06**, one approved invocation of the three-opt-in capture command
returned **1 failed in 11.81s** (exit code 1); safe elapsed **11.709s**.
There was no automatic retry or second invocation. The unchanged strict canary
made four logical calls: OpenAI planning, You.com search, Tavily extraction, and
OpenAI evidence extraction once each. Tavily search, OpenAI Research Fit, and
Nebius were **not called**. Tokens and monetary cost remain unknown.

```text
Planning -> discovery -> page retrieval -> evidence extraction
  -> strict verification: STOP (affiliation + research evidence not grounded)
  -> private capture: 2 excerpts -> offline replay: 2 failures reproduced
```

### What the live run established

Evidence extraction completed. Strict verification failed
`missing_required_evidence` for `current_affiliation` and
`research_interest_or_publication`. Unknown missing-category count was zero.
Research Fit input/evaluation were both `not_reached`.

| Claim type | Retained | Grounded | Rejection reason |
| --- | ---: | ---: | --- |
| Identity | 1 | 1 | None |
| Current affiliation | 1 | 0 | `context_conflicting_person`: 1 |
| Research interest | 1 | 0 | `context_subject_pattern_missing`: 1 |
| Project | 3 | 0 | `profile_subject_mismatch`: 3 |
| Publication, methodology, availability | 0 each | 0 each | None retained |

Extraction/final-verification counts agree: six retained, one grounded, five
rejected. Availability was not stated and was not a required verification gate.
No Verified Supervisor, Research Fit assessment, independent review, proposal,
or synthetic approval was reached.

### Private capture and offline findings

The observer wrote **two eligible samples, zero excluded**: one affiliation
excerpt (70 characters) and one research excerpt (147 characters). The file is
**1,012 bytes**, mode `0600`, in a `0700` directory covered by the existing
`/artifacts/` ignore rule. No full page, Candidate content, claim prose, credentials,
or complete model response was retained. Source text and matcher spans were not
printed into the public report or copied into documentation/tests/traces.

The offline CLI returned exit **0** with:

```json
{"sample_count":2,"matched_count":2,"changed_count":0,"excluded_count":0}
```

This means both **rejections reproduced**, not that either claim passed.
Private local structural checks, emitting only fixed categories and booleans,
established:

- Affiliation: the `titled_person` matcher captured an academic title followed by
  a discipline label as though it were another person's name. Its 26-character
  match contained no line break. The expected/asserted names were title-equivalent.
  This identifies a false-person match in this excerpt, not an actual affiliation
  conflict. Later affiliation-field checks remain unproven.
- Research: no conflicting-person matcher fired; no permitted contextual prefix
  was recognized. The excerpt begins with the title-equivalent, untitled owner
  name, while the asserted name includes an academic title. The direct-subject
  check requires a literal normalized prefix and fails that comparison. A local
  in-memory title-removal probe still failed because the sentence begins with
  an `is` relation outside the current research-relation allowlist. Neither the
  artifact nor production logic was modified. This describes parser restrictions;
  it does not prove that every named sentence should qualify as research evidence.
- The three project claims failed a separate page-subject check and were outside
  the two-type capture scope. Do not infer their exact failure cause from this file.

### Replay this observation without another provider call

From `projects/scholar-path`, with the ignored file still present locally:

```bash
venv/bin/python -m scripts.replay_grounding artifacts/grounding-replays/faa43dd6-215e-4be0-8ad0-c6d8ecfde3c7.json
```

The random filename is only a local artifact locator. It carries no source identity
and the file is deliberately not available from a fresh Git checkout. Do not upload
it or add it to Git without a separate privacy review.

### Next boundary and checks

Prioritize a minimal offline role/discipline regression and a narrow false-person
repair with real other-person controls. Replay the saved samples afterward before
considering another live observation. Research grammar/title handling and project
page-subject checks remain separate issues; do not relax the mandatory gates.

Pre-run formatting (**320 files**), Ruff lint, and mypy (**235 source files**) passed.
The full non-live suite passed: **2,320 passed, 9 deselected, 94 subtests passed in
26.55s**, **92.00% coverage**. Independent read-only preflight review confirmed
capture privacy, strict gates, timeouts, and the nine-logical-call ceiling.
No runtime/test change, credential change, second live run, Mem0, persistent
graph/shortlist write, outreach, trace upload, commit, or push in this step.

## Step 3y: isolated live Nebius review passed

On **2026-09-06**, one separately network-approved invocation of the
[isolated smoke command](#step-3x-isolated-nebius-smoke-diagnostics-offline)
returned **1 passed in 4.37s** (exit 0). The safe summary measured **4.356s**
and **one logical Nebius call**. No second invocation was made.

```text
Fixed synthetic input -> Nebius -> Structured response and reference checks
  -> Reconciliation: ACCEPTED -> Final check: PASS
```

All six stages completed with null failure categories: `configuration`,
`review_input`, `model_call`, `response_checks`, `reconciliation`, and
`final_checks`. `review_status` was **`accepted`**, and `failure_kind` was **null**.

This establishes one real Nebius response passing the existing schema, score,
evidence-reference, and reconciliation checks for fixed synthetic evidence. It
does not prove that the review is substantively useful to a Candidate, explain
the exact earlier step 3u response, or validate a real Supervisor's evidence.
An isolated success is not full-pipeline, persisted LangGraph/UI, or repeatability
evidence. The current-affiliation failure from step 3w remains open.

The request timeout was capped at 60 seconds and SDK retries remained zero.
Tracing was forced off. No OpenAI, search, extraction, Mem0, private capture or
artifact access, persistence, shortlist approval/write, or outreach occurred.
No provider configuration, prompt, fixture, or production code changed. Tokens
and cost remain **unknown**, not zero.

Preflight: formatting **333 files**, Ruff pass, mypy **241 source files**, full
offline suite **2,541 passed, 9 deselected, 101 subtests passed in 27.12s**,
**92.08% coverage**. Exact execution and final documentation checks are in the
[build journal](build-journal.md).

**Next bounded priority:** return to the Week 4 evaluation deliverable: prepare a
review-ready 30-case synthetic dataset, retaining the original eleven-case version
and the five starting outcomes approved for review. Include distinct happy, edge,
known-failure, and adversarial cases with explicit expected outcomes and label
provenance. Do not call new labels human-reviewed or silently overwrite an existing
baseline. Keep the affiliation/review failure patterns as explicit evaluation
work, not reasons for repeated live canaries or lowered evidence gates.

## Step 3x: isolated Nebius smoke diagnostics (offline)

The existing `tests/integration/test_nebius_review_live.py` now isolates the
reviewer using a fixed synthetic Candidate, Verified Supervisor, and Research Fit
assessment. It makes no search, extraction, OpenAI, or Mem0 call and performs no
shortlist approval or persistence. Step 3x ran it **with fakes only**.

```text
Configuration -> Fixed review input -> Nebius model call
  -> Response checks -> Deterministic reconciliation -> Final check
```

The `nebius_smoke.summary` event always contains six fixed `stage_outcomes`:
`configuration`, `review_input`, `model_call`, `response_checks`, `reconciliation`,
and `final_checks`. Each is `not_reached`, `started`, `completed`, or `failed`,
with a null or fixed `failure_category`.

| Failure boundary | Safe category |
| --- | --- |
| Validated provider configuration or construction raises a validation error | `configuration_invalid` |
| Fixed domain input fails validation | `input_validation` |
| Adapter raises typed request/output error | `model_invocation` / `invalid_output` |
| Returned value fails the structured response schema | `invalid_output` |
| Reviewer cites an ineligible evidence reference | `invalid_evidence_reference` |
| Reconciliation returns a failure kind | `review_not_completed` at final check |
| Local validation, assertion/pytest failure, or other exception | `local_validation` / `check_failed` / `unexpected_failure` |
| A second model invocation is attempted | `call_limit`, before calling the model |

`review_calls` is a logical invocation count, capped at one. `review_status` and
`failure_kind` are allowlisted reconciliation enums, or null before a result (and
for unrecognized labels). An adapter failure can therefore have a failed model
stage but a null reconciliation failure kind; inspect the stage category.
No inputs, IDs, source URLs, scores, review prose, credentials, or exception text
are serialized. Elapsed seconds are measured; token usage/cost remain null.

All original decision, score, evidence-allowlist, and reconciliation requirements
remain in order. The smoke still invokes the adapter directly; it does not turn
the agent's graceful-degradation path into a successful review. Typed response
validation also rejects malformed port returns before local checks.

Tracing is explicitly disabled around construction and invocation and restored
after exit, including failure. The disable context does not load settings or
create a tracing client. The configured request timeout is clamped to **at most
60 seconds**, preserving a lower value; the adapter still has zero SDK retries.
These are not an enforced overall elapsed-time deadline or currency budget.

Opt-in/missing-key skips remain before diagnostics, as do settings-loader errors.
They cannot be mistaken for a completed review, but they do not emit a summary.
A stage interrupted by `KeyboardInterrupt`/`SystemExit` may remain `started`;
the observer does not swallow those exceptions. Deliberate pytest failures are
recorded as failures and rethrown.

Offline demonstration from `projects/scholar-path`:

```bash
venv/bin/pytest -o addopts='' -q tests/unit/evaluation/test_nebius_smoke_diagnostics.py
```

For the **next separately approved single live observation**, use the existing
ignored `.env` for the Nebius credential; do not paste a token into the command:

```bash
SCHOLARPATH_RUN_LIVE_TESTS=true LANGSMITH_TRACING=false \
SCHOLARPATH_LOG_LEVEL=WARNING NEBIUS_REVIEW_TIMEOUT_SECONDS=60 \
venv/bin/pytest -o addopts='' -q -rs -s --tb=no --show-capture=no \
  --log-level=CRITICAL -m live tests/integration/test_nebius_review_live.py
```

Keep traceback/log suppression: raw pytest output can contain provider/input
context even though the custom summary is safe. A skip is not a pass. Do not
automatically rerun or tune prompts/models to get green. This isolated test does
not diagnose the exact historical step 3u response or establish full-pipeline,
UI, live source quality, or repeatable verification success.

No live call or production change occurred in step 3x. The affiliation-repeatability
issue stays open. Exact offline checks are in the [build journal](build-journal.md).

## Step 3w: instrumented live observation stopped at affiliation

On **2026-09-06**, one separately network-approved invocation of the
[bounded vertical-canary command](#exact-command) returned **1 failed in 8.62s**
(exit 1). Safe elapsed time was
**8.521s**. No second invocation or speculative repair followed.

```text
Planning -> You.com discovery -> Tavily extraction -> OpenAI evidence: completed
  -> strict verification: FAILED (current affiliation not grounded)
  -> Research Fit / Nebius / synthesis / synthetic approval: NOT REACHED
```

| Operation | Logical calls |
| --- | ---: |
| OpenAI planning | 1 |
| You.com search | 1 |
| Tavily fallback search | 0 |
| Tavily extraction | 1 |
| OpenAI evidence extraction | 1 |
| OpenAI Research Fit | 0 |
| Nebius independent review | 0 |
| **Total** | **4** |

`evidence_extraction` completed. `evidence_verification` failed with
`missing_required_evidence`. The verification standard was **strict**; the only
missing required category was **`current_affiliation`**, with zero unknown categories.
All remaining ten stages were **`not_reached`**, with null failure categories.
`review_diagnostics`, `proposed_supervisor_count`, and `shortlisted_supervisor_count`
were **null**, meaning unobserved, not zero completed results.

| Claim type | Retained | Grounded | Rejection reason/count |
| --- | ---: | ---: | --- |
| Identity | 1 | 1 | None |
| Current affiliation | 1 | 0 | `institution_not_in_excerpt`: 1 |
| Research interest | 1 | 1 | None |
| Methodology | 0 | 0 | None |
| Publication | 2 | 0 | `profile_subject_mismatch`: 2 |
| Project | 1 | 0 | `profile_subject_mismatch`: 1 |
| Availability | 1 | 0 | `context_subject_pattern_missing`: 1 |

Extraction and verification counts agree: **seven retained, two grounded, five
rejected**. Identity and research evidence cleared their gates. The retained
affiliation claim did not establish the configured institution under the existing
excerpt-matching rule. This reason does not prove that the official page lacks
affiliation, that the discovered affiliation is correct, or that the model omitted
a particular sentence. No raw excerpt was captured or inspected in this step.

This run does **not** diagnose step 3u's later failure: Nebius was not reached.
The differing required-evidence outcome shows that the previous strict-verification
success was not repeatable in this observation; aggregate counts alone do not
isolate whether page content, extraction choices, or identity/institution matching
caused the difference. No timeout, credential problem, or fix is inferred.

Tracing and private capture stayed off. No private artifact access, Mem0, persistent
graph/shortlist write, outreach, or real Candidate approval occurred. Tokens and
cost remain **unknown**. This is not a live quality baseline or full UI/graph result.

**Next bounded priority:** isolate the unresolved Nebius integration using the
existing synthetic, fixed-evidence review smoke test, with safe stage reporting
and a single-call/time limit checked before separate live approval. This avoids
depending on another variable upstream extraction just to reach the reviewer.
It must not be reported as an end-to-end canary pass. Keep the affiliation
repeatability issue open for a separately scoped evidence reproduction; do not
weaken its gate or rerun the full pipeline until green.

Preflight: formatting **330 files**, Ruff pass, mypy **240 source files**, full
offline suite **2,515 passed, 9 deselected, 99 subtests passed in 26.61s**,
**92.08% coverage**. Scope audit found no blocker. Exact execution and final
documentation checks are recorded in the [build journal](build-journal.md).

## Step 3v: post-fit diagnostics (offline)

Checkpoint **`2fbfbeb`** preserves steps 3q–3u. The new diagnostic work is separate
and was tested without live services. It extends the four existing evidence/fit
stage outcomes; it does not replace production agents or change their gates.

```text
Review input -> Independent Review Agent [model call -> reconciliation]
  -> completed-review gate -> synthesis -> proposal checks
  -> synthetic approval (memory only) -> final assertions
```

| New stage | Meaning of `completed` |
| --- | --- |
| `review_input` | The same pure input mapping used by the agent passed. |
| `review_model_call` | The adapter returned; its output is not necessarily an accepted review. |
| `independent_review` | The agent returned a reconciled result, possibly `unavailable`. |
| `review_gate` | Review is accepted/revised and has no failure kind. |
| `shortlist_synthesis` | Deterministic synthesis returned a proposal. |
| `proposal_checks` | Original lifecycle, availability, and one-result assertions passed. |
| `synthetic_approval` | The explicit test-only approval produced an in-memory shortlist. |
| `final_checks` | Original shortlist, call-budget, and prohibited-prose assertions passed. |

The model call occurs inside the agent stage. A caught model failure can therefore
produce `review_model_call: failed`, `independent_review: completed`, and
`review_gate: failed`. This is deliberate: a safely degraded result is not a valid
independent review. A structurally returned response can also fail later local
validation or evidence-reference reconciliation.

New summary fields:

- `review_diagnostics`: `null` before a reconciled result, otherwise only the
  allowlisted `review_status` and `failure_kind` enum values. Unknown values become
  `null`; no critique, evidence identifiers, input data, or exception text is emitted.
- `proposed_supervisor_count` and `shortlisted_supervisor_count`: `null` until the
  corresponding factory returns; zero means an observed empty result. Counts do
  not assert persistence or Candidate-approved production results.
- `review_not_completed`: the explicit completed-review requirement failed.
- `check_failed`: an assertion or deliberate pytest failure stopped a tracked stage.
  Typed review adapter failures retain `model_invocation` or `invalid_output`;
  other exceptions use the existing safe categories, without parsing messages.

The observer catches and rethrows pytest's specific failure outcome as well as
normal exceptions. It does not swallow `KeyboardInterrupt`/`SystemExit`; an
interrupted stage can remain `started`, never falsely `completed`.

Offline demonstration (no API keys or network required):

```bash
venv/bin/pytest -o addopts='' -q tests/unit/evaluation/test_live_canary_post_fit.py
```

Fixtures cover accepted/revised reviews, invocation errors, malformed returned
objects, invalid evidence references, invalid local input, later-stage failures,
redaction, unchanged data, budgets, and exception propagation. The original
assertions remain in the same order: review/proposal checks before synthetic
approval, final checks afterward. Exact results are in the [build journal](build-journal.md).

No live call, new capture, private artifact access, Mem0, tracing, durable shortlist
write, or push occurred. **Step 3u's exact failure remains unconfirmed.** A further
single live observation requires separate approval using the existing command
with capture/tracing explicitly disabled; do not automatically rerun until green.

## Step 3u: post-repair live result

On **2026-09-06**, the single separately network-approved invocation of the
[bounded vertical-canary command](#exact-command) returned **1 failed in 22.19s**
(exit 1), safe elapsed **22.088s**.
Private capture was explicitly `false`. There was no second invocation, new
source artifact, private artifact read/write, or LangSmith upload.

```text
Planning -> You.com discovery -> Tavily page extraction -> OpenAI evidence
  -> strict verification: PASS -> Research Fit input: PASS
  -> OpenAI Research Fit evaluation: PASS -> Nebius: CALLED
  -> canary FAIL: exact post-fit boundary not exposed by current summary
```

| Operation | Actual logical calls |
| --- | ---: |
| OpenAI planning | 1 |
| You.com search | 1 |
| Tavily fallback search | 0 |
| Tavily extraction | 1 |
| OpenAI evidence extraction | 1 |
| OpenAI Research Fit | 1 |
| Nebius independent review | 1 |
| **Total** | **6** |

All four tracked stages (`evidence_extraction`, `evidence_verification`,
`research_fit_input`, `research_fit_evaluation`) reported **completed**, with
null failure categories. Verification standard was **strict**, missing required
evidence was **empty**, and unknown missing-category count was **zero**.

| Claim type | Retained | Grounded | Rejection reason/count |
| --- | ---: | ---: | --- |
| Identity | 1 | 1 | None |
| Current affiliation | 1 | 1 | None |
| Research interest | 2 | 1 | `profile_subject_mismatch`: 1 |
| Methodology | 1 | 0 | `context_subject_pattern_missing`: 1 |
| Publication | 2 | 0 | `profile_subject_mismatch`: 2 |
| Project | 1 | 0 | `profile_subject_mismatch`: 1 |
| Availability | 0 | 0 | None retained |

Extraction/final-verification counts agree: **eight retained, three grounded,
five rejected**. Required identity, current affiliation, and research-interest
evidence all exist, without promoting the rejected claims. Availability evidence
was absent and did not block verification. Tokens and monetary cost are **unknown**.

### What remains unconfirmed

This establishes a live Verified Supervisor and completed Research Fit evaluation,
not a useful score, successful independent review, or a final shortlist. Nebius's
call counter proves an attempted call, not a validated/reconciled result. The test
continues through review validation, proposal synthesis, synthetic approval, and
final assertions after the last tracked stage. With tracebacks suppressed and
no post-fit status fields, the actual failing boundary cannot be identified from
this output. Do not label it a credential, timeout, model, or review failure yet.

No Mem0 call, SQLite/graph persistence, durable shortlist write, outreach, or
real Candidate approval occurred. The test's possible synthetic in-memory approval
is not confirmed as reached. This remains a service-integration diagnostic, not
the full UI/LangGraph workflow or a quality benchmark. Live source/model outputs
can vary, so the new counts do not prove the exact same excerpt forms recurred.

### Next bounded action and checks

Add privacy-safe, offline-tested outcomes for independent review and later
synthesis/approval/check boundaries, without changing their behaviour or provider
budgets. Then separately approve one live observation if needed. Do not rerun
until green or relax verification now that its required gates have passed.

Pre-run validation: Ruff formatting **327 files**, lint pass, mypy **239 source
files**, full default suite **2,490 passed, 9 deselected, 97 subtests passed in
26.81s**, **92.04% coverage**. Focused canary/privacy/contracts: **101 passed,
97 subtests passed in 0.50s**. See the [build journal](build-journal.md) for the
recorded command and final checks. This step changes documentation only; existing
runtime/test repairs remain uncommitted. No commit or push was made.

## Step 3t: named-specialisation repair (offline)

Structural inspection of the retained research sample confirmed an explicit
academic specialisation relation after an untitled owner name. The new contextual
rule recognizes only that affirmative relation (including its spelling variant)
after the complete name. It leaves direct identity/name matching unchanged and
still requires an official singular profile and same-source grounded identity.
Generic employment, `is researching`, uncertain/negated statements, and other
evidence categories do not gain acceptance through this rule.

Synthetic tests replace the person, institution, URL, and research topics. They
exercise strict verification, all invalid identity-reference cases, wrong-person
headings, absent page excerpts, source eligibility, model-unsupported output,
and diagnostic-on/off equivalence. Source text, IDs, timestamps, and confidence
remain untouched. No live provider call, credential access, or trace upload occurred.

Read-only replay:

```bash
venv/bin/python -m scripts.replay_grounding artifacts/grounding-replays/faa43dd6-215e-4be0-8ad0-c6d8ecfde3c7.json
```

Result: **two samples, zero matched, two changed, zero excluded**, exit **1**.
This exit means historical rejection reasons changed, not a tool error. Both current
excerpt reasons are now `None`. The ignored file remains **1,012 bytes**, mode
**0600**, inside a **0700** directory; before/after replay digests match.

**This is not complete verification or a live success.** The capture has no full
page or typed affiliation fields. Later full gates must still pass; Research Fit
and Nebius have not been reached by a new live run. A separately approved bounded
canary is the next observation, with no automatic reruns. Exact offline commands
and results are recorded in the [build journal](build-journal.md).

## Step 3s: role-discipline repair (offline)

On **2026-09-06**, the observed role/discipline false-person match was reproduced
with synthetic names/institutions and repaired without a new live call. The
initial domain regression showed **12 failed, 24 passed in 0.22s**: the positive
role cases failed while existing other-person controls continued to reject.

The change is deliberately narrow:

```text
Titled-name pattern -> shared complete-role filter -> existing grounding checks
                            |
                      same filter used by offline replay
```

Only the complete `Prof`/`Professor` computer-science role label (optional title
period and horizontal spacing variants) is excluded from person matches, and only
inside a **single-line excerpt**. This is not a growing list of inferred disciplines,
a prefix exemption, or a change to identity/affiliation/research requirements.
Direct checks, contextual checks, and replay diagnostics share the same helper.

Independent review identified a wrapped-name risk in the first filter: a longer
name can continue after a line break or surname particle beyond the regex's match.
Eight added LF/CRLF extension cases reproduced that risk before the single-line
bound was added. Those cases now retain conservative rejection, as do Doctor
titles, longer same-line names, near-match labels, and actual other people before
or after the role. Multiline role excerpts deliberately retain the old behavior;
they were not the observed case and were not broadened in this repair.

Synthetic fake-agent checks establish complete strict verification **only when**
identity, current affiliation fields, and supported research are present. Exact
excerpts, source URLs/kinds, retrieval timestamps, evidence IDs, and diagnostics
remain consistent; availability stays `not_stated`. Each extraction uses one fake
model call. Missing evidence, changed identity provenance, source ineligibility,
unsupported claims, and the named-owner research `is` form still fail safely.

### Saved replay result

The same private file was read without modification. Its replay now reports:

```json
{"sample_count":2,"matched_count":1,"changed_count":1,"excluded_count":0}
```

| Captured check | Before | After |
| --- | --- | --- |
| Affiliation excerpt subject | `context_conflicting_person` | No excerpt-subject failure |
| Research excerpt subject | `context_subject_pattern_missing` | Unchanged |

The replay command documented in step 3r now exits **1** because one historical
rejection changed; that is expected for this repair, not a CLI crash. The file is
still 1,012 bytes, `0600`, and Git-ignored. Neither its source text nor identities
were copied into the tests or this report. Only its generic role-label structure
informed the synthetic fixtures.

This proves that the captured false-person check clears, **not** that the real
Supervisor satisfies every affiliation field or complete strict verification.
The private replay does not contain all inputs for those later gates. Research
title/grammar and project/page-subject handling remain unchanged. No live Research
Fit/Nebius result, graph progression, or shortlist approval is claimed.

Next is a bounded offline reproduction of the research title/sentence-form case,
not another automatic live run or a broad `is` relation exception. See the
[build journal](build-journal.md#week-4-step-3s--rolediscipline-false-person-repair-2026-09-06)
for full test results. No credential change, live provider call, trace upload,
private artifact mutation, commit, or push in this step.

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
