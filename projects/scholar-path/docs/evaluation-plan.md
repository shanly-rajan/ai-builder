# ScholarPath M12 Evaluation Plan

ScholarPath uses LangSmith evaluation to supplement, not replace, the existing pytest
suite. Pytest remains the release gate for deterministic domain, graph, integration,
contract, terminology, privacy, and provider-boundary behavior. M12 adds a curated,
synthetic regression dataset that can first run locally and then, with explicit opt-in,
be uploaded as a LangSmith experiment.

The evaluation flow is summarized in
[`m12-langsmith-evaluation-suite.mmd`](m12-langsmith-evaluation-suite.mmd).

## LangSmith SDK choice

The project declares `langsmith>=0.11.2,<1`, and the current project environment has
LangSmith `0.11.2` installed. M12 uses the supported top-level Python SDK interfaces:

- `langsmith.Client.create_dataset(...)` and `Client.create_examples(...)` for the
  versioned dataset;
- `Client.evaluate(...)` for explicitly uploaded experiments;
- a direct deterministic runner for the default no-client, no-network baseline; and
- custom Python evaluator functions for deterministic metrics, with separately injected,
  structured-output judges only for qualitative criteria.

These choices follow the official LangSmith documentation:

- [Evaluation overview](https://docs.langchain.com/langsmith/evaluation)
- [Evaluation quickstart](https://docs.langchain.com/langsmith/evaluation-quickstart)
- [Programmatic dataset management](https://docs.langchain.com/langsmith/manage-datasets-programmatically)
- [Evaluate an application with the Python SDK](https://docs.langchain.com/langsmith/evaluate-llm-application)
- [Run an evaluation locally without uploading](https://docs.langchain.com/langsmith/local)
- [LLM-as-judge guidance](https://docs.langchain.com/langsmith/llm-as-judge)

No evaluation dependency beyond the existing LangSmith and structured-output model
dependencies is required for M12.

## Dataset contract

The dataset name is `scholarpath-m12-regression-v1`. Every example is fictional,
deterministic, and safe to commit. Stable scenario identifiers and deterministic example
identifiers make dataset synchronization idempotent: rerunning dataset creation updates the
same examples rather than creating duplicates.

An example contains:

- a typed target identifier;
- a synthetic input payload appropriate to that target;
- reference expectations used only by evaluators;
- one or more stable split labels; and
- low-cardinality metadata containing only the scenario identifier, schema version,
  synthetic-data marker, graph version, and prompt versions.

Reference outputs are never passed into a target function. They are available only to the
evaluators. A metric that does not apply to an example returns `score=None`; it must not
return a passing score that would inflate the experiment average.

## Curated scenarios and splits

The initial dataset contains eleven scenarios. A scenario may belong to more than one split
so component regressions and end-to-end regressions can be filtered independently.

| ID | Scenario | Splits | Primary expectations |
|---|---|---|---|
| `strong-research-alignment` | Strong, evidence-backed research alignment | `research-fit`, `llm-judge` | High Research Fit supported by owned evidence IDs and explicit evidence gaps |
| `superficial-keyword-poor-fit` | Shared keywords but poor substantive alignment | `research-fit`, `llm-judge` | Low Research Fit; no points from keyword presence alone |
| `availability-not-stated` | No direct availability statement | `evidence-verification` | Availability remains exactly `not_stated` and does not affect Research Fit |
| `conflicting-institutional-affiliation` | Current official sources disagree about affiliation | `evidence-verification` | Conflicting evidence and concerns are surfaced; no silent resolution |
| `duplicate-supervisor-multiple-queries` | The same Supervisor is discovered through multiple queries | `graph-fake` | One retained Supervisor, merged provenance, and zero duplicate rate after deduplication |
| `you-timeout-tavily-fallback` | You.com times out and bounded fallback is required | `graph-fake` | One bounded You.com retry, Tavily fallback, partial success retained, and no loop |
| `evidence-extraction-failure` | Known-page extraction and alternate retrieval fail | `graph-fake` | Partial evidence is retained without fabrication |
| `independent-reviewer-disagreement` | Independent review recommends a materially different score | `graph-fake`, `llm-judge` | Valid reconciliation, reduced confidence, and Candidate attention |
| `candidate-rejects-highly-theoretical` | The Candidate rejects research that conflicts with an applied preference | `graph-fake` | Rejection is recorded and no Supervisor is shortlisted |
| `approval-required-before-persistence` | A proposal reaches the Candidate review interrupt | `graph-fake`, `graph-live` | No shortlist persistence while paused; explicit approval remains mandatory |
| `planning-source-coverage` | Planning must cover all required source types | `planning` | Four to eight distinct queries cover profiles, groups, publications, and explicit supervision information |

The `graph-live` split is deliberately small. It does not grant permission to run live
providers; it only identifies the synthetic example eligible for the optional live target
after all live gates are satisfied.

## Target functions

All targets accept a dictionary from a dataset example and return a bounded, JSON-safe,
typed projection. Targets never return API keys, raw provider exceptions, full page content,
complete LangGraph state, Mem0 records, checkpoint thread IDs, or hidden reasoning.

| Target | Purpose | External calls by default |
|---|---|---|
| `search_planning_target` | Evaluate structured search-plan generation and required source coverage | None; injected fake planning model |
| `evidence_verification_target` | Evaluate claim extraction, grounding, sufficiency, conflicts, and availability derivation | None; fixed content and fake structured model |
| `research_fit_target` | Evaluate evidence-cited rubric components and deterministic arithmetic | None; injected fake Research Fit model |
| `fake_end_to_end_target` | Exercise the full graph, fallback, review, and approval boundaries with fakes | None; fake tools, models, memory, and in-memory checkpointing |
| `live_end_to_end_target` | Optionally execute the same bounded projection through configured live providers | Yes; explicit live opt-in and credentials required |

The fake end-to-end target is the default graph target. Each run uses an isolated synthetic
thread ID, but that identifier is not copied into trace metadata or evaluation output.

## Deterministic evaluators

Code owns every fact that can be validated exactly. A deterministic evaluator must not
instantiate or call a model.

| Metric key | Scale | Direction | Applicability | Required threshold |
|---|---:|---|---|---:|
| `schema_validity` | `0` or `1` | Higher is better | All targets | `1.00` on every applicable example |
| `canonical_terminology` | `0` or `1` | Higher is better | All generated output | `1.00` on every applicable example |
| `evidence_id_validity` | `0` or `1` | Higher is better | Verification, Research Fit, end-to-end | `1.00` on every applicable example |
| `source_url_presence` | `0` or `1` | Higher is better | Every emitted factual EvidenceClaim | `1.00` on every applicable example |
| `score_range_and_component_totals` | `0` or `1` | Higher is better | Research Fit and end-to-end | `1.00` on every applicable example |
| `no_unsupported_availability_claim` | `0` or `1` | Higher is better | Verification, Research Fit, end-to-end | `1.00` on every applicable example |
| `no_admission_probability` | `0` or `1` | Higher is better | Research Fit, review, proposal, briefing | `1.00` on every applicable example |
| `correct_fallback_route` | `0` or `1` | Higher is better | Resilience examples | `1.00` on every applicable example |
| `duplicate_supervisor_rate` | `0.0` to `1.0` | Lower is better | Discovery and end-to-end | `0.00` after deterministic deduplication |
| `human_approval_enforcement` | `0` or `1` | Higher is better | Human-control examples | `1.00` on every applicable example |

Evaluator comments contain only concise failure categories and counts. They must not echo a
Candidate research statement, a review reason, a query, a name, a URL, an evidence excerpt,
page content, raw model output, or a provider error body.

### Exact evaluator rules

- Schema validity parses the target-specific Pydantic output and rejects missing output,
  unknown fields, or an incorrect target discriminator.
- Evidence ID validity requires every cited ID to belong to the same Verified Supervisor;
  availability evidence cannot support a Research Fit component.
- Score range validates overall and component bounds. Component totals are calculated in
  Python and must equal the overall score; the configured rubric must total 100.
- Availability is deterministically derived from directly supported availability evidence.
  No such evidence means `not_stated`; conflicting direct statements mean
  `conflicting_evidence`.
- Correct fallback checks the typed attempt sequence as well as the fallback flag. The
  timeout scenario requires a bounded retry followed by Tavily, not merely a Boolean value.
- Duplicate rate uses normalized name, institution, and canonical profile URL. The duplicate
  scenario also requires all exact discovery provenance to survive the merge.
- Human approval inspects lifecycle state and execution order. A proposed recommendation is
  not a Shortlisted Supervisor, and save or briefing nodes must not run before approval.

## LLM-as-judge evaluators

Judges are reserved for qualitative questions without an exact deterministic answer. Each
judge has a versioned, narrowly scoped prompt, an injected model port, and a typed structured
result. Default tests use a fake judge. Important judge output is never parsed from free-form
prose.

| Metric key | Scale | Direction | Applicable output | Advisory baseline threshold |
|---|---:|---|---|---:|
| `llm_research_fit_relevance` | `0` to `4` | Higher is better | Strong-fit and weak-fit Research Fit assessments | Advisory mean at least `3.0`; no applicable result below `2` |
| `llm_explanation_usefulness` | `0` to `4` | Higher is better | Search-plan and Research Fit explanations | Advisory mean at least `3.0`; no applicable result below `2` |
| `llm_evidence_grounded_rationale` | `0` to `4` | Higher is better | Evidence-linked Research Fit and reconciled rationale | Advisory mean at least `3.0`; no applicable result below `2` |
| `llm_shortlist_usefulness` | `0` to `4` | Higher is better | Proposed shortlist shown for Candidate review | Advisory mean at least `3.0`; no applicable result below `2` |

These thresholds are advisory until judge calibration is measured against human ratings.
They do not block M12 by themselves. Deterministic safety and approval metrics remain hard
gates.

The judge is not asked to validate schemas, evidence ownership, URLs, arithmetic,
availability, admission probability, fallback routing, deduplication, lifecycle changes, or
Candidate approval. Those checks remain deterministic.

Judge inputs contain only the synthetic topics and preferences required for comparison,
concise evidence claims, evidence IDs, rationale, strengths, concerns, and proposal items.
They omit Candidate identity, full research statements, full pages, provider payloads,
secrets, and checkpoint data.

## Target and evaluator matrix

`D` means deterministic, `J` means judge, and `-` means not applicable.

| Target | Schema and terminology | Evidence and sources | Score and safety | Route, duplicate, approval | Qualitative judges |
|---|---|---|---|---|---|
| Search planning | D | - | - | - | - |
| Evidence verification | D | D | D: availability | - | - |
| Research Fit | D | D | D: range, totals, availability, admission | - | J: relevance, explanation, grounding |
| Fake end-to-end | D | D | D | D | J: relevance, explanation, grounding, shortlist |
| Live end-to-end | D | D | D | D | Optional J after separate opt-in |

## Experiment tags

Only fixed, low-cardinality values are permitted in experiment and trace tags:

- `application:scholarpath`
- `environment:<development|test|production>`
- `graph-version:<version>`
- one or more `prompt-version:<version>` tags
- one or more `model-provider:<fake|openai|nebius>` tags
- `fallback-used:<true|false>`
- `candidate-review-outcome:<not_applicable|awaiting_review|approve|reject|request_more>`

The Candidate review outcome is the action enum only. A rejection reason, revised
preference, approved Supervisor ID, or Candidate identifier is never a tag or metadata
value.

## Privacy and data governance

The checked-in dataset contains only invented Candidate profiles, invented Supervisor
records, fixed excerpts, and `.example` source URLs. It must never be populated from a real
Candidate session, production trace, Streamlit session, checkpoint database, or Mem0 record.

The following values are prohibited from experiment and trace metadata:

- Candidate name, email address, identifier, research statement, preferences, constraints,
  exclusions, feedback, or review reason;
- Supervisor name, profile URL, evidence URL, evidence excerpt, full page content, search
  query, returned result content, or publication text;
- thread ID, checkpoint path, memory record, API key, credential-bearing endpoint, raw
  provider exception, or model chain-of-thought.

Dataset payloads and trace metadata are different boundaries. The synthetic dataset may
contain the invented content needed by a target, while metadata remains limited to the
allowlist above. Target output is still bounded and never includes full pages or raw provider
responses. The configured LangSmith regional endpoint and workspace ID must be honored for
every uploaded dataset or experiment.

Before any non-synthetic evaluation data is considered, ScholarPath requires a separate
governance decision covering consent, purpose limitation, residency, access control,
retention, deletion, and auditability.

## Local and live execution gates

Local fake evaluation is the default:

```bash
python scripts/run_evals.py --target graph_fake
```

It invokes the typed targets and deterministic evaluators directly, constructs no LangSmith
client, makes no network request, requires no API key, and uses only fake tools and models.

Every operation that writes to LangSmith requires both an explicit command option and:

```bash
SCHOLARPATH_RUN_LANGSMITH_EVALS=true
LANGSMITH_API_KEY=...
```

An uploaded fake-tool experiment additionally selects the upload option in
`scripts/run_evals.py`. `LANGSMITH_ENDPOINT` and, when needed, `LANGSMITH_WORKSPACE_ID` must
match the account region and workspace.

Judge-model calls remain separately selected by an explicit command option:

```bash
OPENAI_API_KEY=...
```

and the explicit `--include-llm-judges` command option.

Live end-to-end provider execution requires an additional opt-in:

```bash
SCHOLARPATH_RUN_LIVE_E2E_EVALS=true
```

plus `--target graph_live` and every provider credential needed by the selected path.
The live target runs only the small `graph-live` split with bounded concurrency and retry
limits. It never runs as part of default pytest or continuous integration.

An optional live pytest smoke test must retain `@pytest.mark.live` and additionally require
`SCHOLARPATH_RUN_LIVE_TESTS=true`. The default pytest suite remains `-m "not live"` and its
socket blocker remains active.

## Regression policy

M12 is complete only when:

1. Existing pytest tests still pass without network access.
2. Every deterministic evaluator has fixed passing and failing unit examples.
3. The eleven scenarios validate and serialize reproducibly.
4. The local fake baseline completes with no hard-gate regression.
5. Results are recorded transparently in
   [`evaluation-baseline.md`](evaluation-baseline.md).
6. Any live or judge experiment remains optional and is reported separately from the local
   baseline.

Future changes to prompts, rubrics, graph versions, evaluator definitions, or dataset
examples require a new experiment identifier. A result from one version must not be
silently relabeled as another.
