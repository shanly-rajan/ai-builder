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
