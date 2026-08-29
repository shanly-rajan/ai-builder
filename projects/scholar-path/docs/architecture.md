# ScholarPath M6 Architecture

M6 replaces the three fixture-backed evidence nodes with a real, typed verification
boundary while preserving the useful M3–M5 architecture:

- M3 plans searches through a structured OpenAI boundary.
- M4 discovers Prospective Supervisors through You.com.
- M5 adds deterministic discovery quality checks and Tavily search fallback.
- M6 retrieves known pages with Tavily Extract, extracts grounded claims through a
  structured model boundary, and deterministically decides whether each record is
  Verified or partially verified.

Research Fit scores remain fixtures in M6. The evidence pipeline may rebind those
fixture assessments to newly generated evidence IDs, but it does not calculate,
change, or justify a Research Fit Score. Candidate review remains the configured stub,
and no Supervisor becomes Shortlisted without the Candidate approval gate.

## End-to-end milestone view

```mermaid
flowchart LR
    CP[CandidateProfile] --> PLAN[ResearchPlanningAgent]
    PLAN --> SQ[SearchPlan]
    SQ --> YOU[You.com discovery]
    YOU --> DP[DiscoveryPolicy]
    DP -->|quality gap or retryable failure| TS[Tavily search fallback]
    DP --> PS[Prospective Supervisors]
    TS --> PS
    PS --> TE[Tavily Extract known profile URL]
    TE --> EV[EvidenceVerificationAgent]
    EV --> VR[SupervisorVerificationRecord]
    VR -->|partial and retry remains| ALT[One alternate official-source search]
    ALT --> TE
    VR -->|sufficient direct evidence| VS[Verified Supervisor]
    VS --> RF[Fixture Research Fit assessment]
    RF --> GATE[Candidate review gate stub]
    GATE -->|approve| SS[Shortlisted Supervisor]
    GATE -->|reject| RS[Rejected Supervisor]

    classDef human fill:#fff4cc,stroke:#9a6b00,stroke-width:2px;
    class GATE human;
```

The LangGraph topology still contains the same fifteen canonical operational nodes.
M6 changes the implementation behind `extract_supervisor_evidence`,
`supervisor_evidence_sufficient`, and `retry_alternate_evidence_source`; it does not
start a future Research Fit or user-interface milestone.

## M3 research-planning boundary

```mermaid
flowchart LR
    Profile[CandidateProfile] --> Map[Deterministic input mapping]
    Preferences[Remembered Candidate preferences] --> Map
    Constraints[Regions and exclusions] --> Map
    Map --> Input[Identity-free PlanningInput]
    Input --> Agent[ResearchPlanningAgent]
    Agent --> Port{{PlanningModelPort}}
    Port --> Fake[FakePlanningModel]
    Port --> OpenAI[OpenAIPlanningModelAdapter]
    OpenAI --> Native[Native strict JSON schema]
    Native --> DTO[StructuredSearchPlanResponse]
    Fake --> DTO
    DTO --> Domain[Deterministic SearchPlan validation]

    classDef boundary fill:#e8f1ff,stroke:#245a9b,stroke-width:2px;
    class Port,OpenAI,Native boundary;
```

The planner receives the Candidate's research statement and typed preferences but no
search tool. `research-planning-v1` uses
`with_structured_output(..., method="json_schema", strict=True)`; prose JSON parsing
is not used. Python and Pydantic enforce four-to-eight distinct queries, required
source-category coverage, target regions, and query uniqueness. Malformed output has
one explicit retry; provider failures stop cleanly. The OpenAI client has
`max_retries=0`, so the application owns the visible retry policy.

## M4–M5 resilient discovery boundary

```mermaid
flowchart LR
    Plan[SearchPlan] --> Port{{SupervisorSearchPort}}
    Port --> You[YouSearchAdapter]
    Port --> Tavily[TavilySearchAdapter]
    Port --> Fake[FakeSupervisorSearch]
    You --> Result[SearchResult]
    Tavily --> Result
    Fake --> Result
    Result --> Agent[SupervisorDiscoveryAgent]
    Agent --> Quality[Deterministic person and institution checks]
    Quality --> Dedupe[Name institution canonical URL]
    Dedupe --> PS[Prospective Supervisor with provenance]
```

The search port executes one exact query at a time. Transport adapters normalize URL,
title, description, optional publication date, and originating query; they contain no
Supervisor reasoning. The discovery agent conservatively identifies plausible people
and institutions, while deterministic deduplication merges exact source/query pairs.
Discovery never produces Research Fit or availability claims.

`route_after_supervisor_discovery` remains pure. It uses only the current discovery
round's typed `SearchAttempt` records and quality metrics to choose one You.com timeout
retry, Tavily fallback, continuation, immediate stop for non-retryable errors, or a
recoverable `discovery_incomplete` result. Useful partial results survive a later query
failure and remain available to downstream deduplication.

## M6 content-extraction transport boundary

```mermaid
flowchart LR
    URL[One known HTTPS profile URL] --> Port{{ContentExtractionPort}}
    Port --> Fake[FakeContentExtraction]
    Port --> Adapter[TavilyExtractionAdapter]
    Adapter --> PublicURL[Public URL validation]
    PublicURL --> Tool[Official langchain_tavily.TavilyExtract]
    Tool --> Deadline[Provider timeout plus application deadline]
    Deadline --> Normalize[Transport-only normalization]
    Normalize --> EC[ExtractedContent]
    EC --> Fields[URL content retrieved_at truncated flag]

    classDef boundary fill:#e8f1ff,stroke:#245a9b,stroke-width:2px;
    class Port,Adapter,Tool boundary;
```

`ContentExtractionPort.extract()` accepts one known URL and returns one
`ExtractedContent`. Production uses the current official top-level
`langchain_tavily.TavilyExtract` import, not deprecated community imports. The adapter
requests Markdown, excludes images and favicons, applies Tavily's provider timeout
inside a slightly longer application deadline, and caps returned content at the
configured character limit.

The adapter is transport-only. It does not identify a Supervisor, extract a factual
claim, infer availability, resolve a conflict, or calculate Research Fit. It validates
the one-result response contract and normalizes failures into typed categories such as
timeout, transport, authentication, rate limit, quota, invalid request, provider,
response contract, or extraction failure. Provider response bodies are not persisted
in graph errors.

Public-URL validation rejects embedded credentials, localhost and local-domain names,
and non-global literal IP addresses. This reduces server-side request-forgery risk
before a URL reaches Tavily. A returned redirect URL is revalidated through the same
boundary.

## M6 structured evidence-model boundary

```mermaid
flowchart TD
    Page[ExtractedContent] --> Input[EvidenceExtractionInput]
    Hints[Expected name institution department] --> Input
    Input --> Port{{EvidenceVerificationModelPort}}
    Port --> Fake[FakeEvidenceVerificationModel]
    Port --> OpenAI[OpenAIEvidenceVerificationModelAdapter]
    OpenAI --> Schema[Strict StructuredEvidenceExtractionResult]
    Fake --> Schema
    Schema --> Ground{Supporting excerpt occurs in page?}
    Ground -->|no| Invalid[Typed output error]
    Ground -->|yes| Subject{Exact Supervisor named in excerpt?}
    Subject -->|no| Indirect[Retain as not directly supported]
    Subject -->|yes| Bind[Bind system-owned provenance]
    Bind --> Claim[EvidenceClaim]
    Claim --> Rules[Deterministic sufficiency and conflict rules]

    classDef boundary fill:#e8f1ff,stroke:#245a9b,stroke-width:2px;
    class Port,OpenAI,Schema boundary;
```

The versioned `evidence-verification-v1` prompt tells the model to use only the
retrieved page. Expected profile values are comparison hints, not evidence. The model
may classify identity, current affiliation, research interests, methodology,
publication, project, and explicit availability, but every structured claim must carry
a short supporting excerpt. Every claim proposed as directly supported must also carry
the asserted person name, and its excerpt must explicitly name that Supervisor.

The OpenAI adapter uses native strict JSON-schema output with `include_raw=False` and
`max_retries=0`. It does not manually parse JSON. The structured model returns no
authoritative evidence ID, retrieval timestamp, or source provenance. The application
binds those fields from trusted inputs after validating the response.

| Field | Authority |
|---|---|
| Claim type, concise claim, asserted values, confidence | Structured model output |
| Supporting excerpt | Structured model output, then checked against the page |
| `supervisor_id` | Prospective Supervisor record |
| Source URL and source kind | Extracted page and selected source reference |
| Retrieval timestamp | Content-extraction boundary |
| Evidence ID | Versioned deterministic hash of every persisted semantic claim field except retrieval time |
| Availability result, conflicts, sufficiency, lifecycle status | Deterministic Python rules |

The extracted full page is transient: it is sent to the evidence model but is not
stored in `ScholarPathState`. State retains concise claims and supporting excerpts.

## Deterministic grounding and verification rules

```mermaid
flowchart TD
    Draft[Structured claim draft] --> Excerpt{Normalized excerpt in page?}
    Excerpt -->|no| Reject[Reject structured output]
    Excerpt -->|yes| Subject{Name matches and occurs in excerpt?}
    Subject -->|no| Indirect[Retain as not directly supported]
    Subject -->|yes| Type{Type-specific facts grounded?}
    Type -->|no| Indirect
    Type -->|yes| Direct[Directly supported claim]
    Direct --> Required{Required evidence present?}
    Required -->|identity + affiliation + research interest or publication| Verified[Verified Supervisor]
    Required -->|missing category| Partial[Partially verified record]
```

Important deterministic rules are:

1. Every directly supported claim must assert the matching Supervisor name and include
   that exact normalized name in its supporting excerpt. Page-level identity alone
   cannot attach another person's research, publication, project, or availability.
2. Current affiliation must directly state both institution and department. A value
   that differs from discovery remains evidence but is surfaced as a concern and never
   silently overwrites the profile fields.
3. At least one directly supported research-interest or publication claim is required.
   Project evidence is preserved but does not independently satisfy this exact gate.
4. Discovery fields and search snippets are never promoted into verification evidence.
5. A missing fact stays missing. Model knowledge cannot fill it.
6. Availability polarity is checked deterministically against the quoted statement;
   model output cannot invert accepting and not-accepting evidence.
7. Evidence IDs include all grounded semantic fields. Identical claims merge without
   randomness; a same-ID/different-payload collision is rejected rather than dropped.

Availability is derived separately:

```mermaid
flowchart TD
    A[Direct typed availability claims] --> Count{Explicit values}
    Count -->|none| NS[not_stated]
    Count -->|accepting only| CA[confirmed_accepting]
    Count -->|not accepting only| CNA[confirmed_not_accepting]
    Count -->|both from distinct pages| CE[conflicting_evidence]
```

Only an explicit statement that a Supervisor is accepting or not accepting doctoral
Candidates may create an availability claim. General supervision history, student
lists, invitations to collaborate, and contact details are not availability.
`not_stated` never blocks verification. A confirmed not-accepting statement is retained
as a concern; it is not silently discarded.

For current-affiliation conflicts, the agent retains both claims and links their
evidence IDs through `conflicting_evidence_ids`. It does not choose one institution on
the model's authority. The completed record becomes `verified_with_concerns` when all
required categories still exist, and the conflict is surfaced explicitly.

## Partial verification is not a lifecycle shortcut

`SupervisorVerificationRecord` is deliberately separate from
`VerifiedSupervisor`:

```mermaid
classDiagram
    class SupervisorVerificationRecord {
      ProspectiveSupervisor prospective_supervisor
      EvidenceClaim[] evidence
      VerificationStatus verification_status
      AvailabilityStatus availability_status
      string[] verification_concerns
      string[] missing_required_evidence
      VerifiedSupervisor? verified_supervisor
    }
    class VerifiedSupervisor {
      status = verified
      EvidenceClaim[] evidence
    }
    SupervisorVerificationRecord --> VerifiedSupervisor : only when sufficient
```

A `partially_verified` result retains available evidence, provenance, concerns, and
the exact missing categories, but its `verified_supervisor` field is absent. It cannot
enter the Supervisor lifecycle as Verified, be scored downstream, or be shortlisted.
This preserves partial work without weakening the lifecycle contract.

## One alternate official-source retry

```mermaid
flowchart TD
    Primary[Extract original profile URL] --> Record[Build verification record]
    Record --> Partial{Any partial records?}
    Partial -->|no and minimum met| Fit[Continue to fixture Research Fit]
    Partial -->|yes and retry unused| Query[Build deterministic name and institution query]
    Query --> Search[Tavily through SupervisorSearchPort]
    Search --> Select{First plausible alternate official URL?}
    Select -->|no| Keep[Keep partial record]
    Select -->|yes| Extract[Extract alternate URL once]
    Extract --> Merge[Merge prior and new grounded evidence]
    Keep --> Gate{Minimum fully Verified after retry?}
    Merge --> Gate
    Gate -->|yes| Fit
    Gate -->|no| End[evidence_incomplete recoverable END]
```

The pure `route_after_evidence_sufficiency()` function receives a frozen
`VerificationPolicy`, immutable verification records, and the alternate retry count.
It performs no provider or model call. The policy retries every partial record once
before applying the configured minimum of five fully Verified Supervisors.

`retry_alternate_evidence_source` searches for one stronger official page per partial
record. Selection is deterministic: it excludes the original URL and requires HTTPS,
the full normalized person-name sequence, institution correlation, and a
DNS-label-aware academic suffix such as `.edu`, `.edu.au`, or `.ac.za`. Institution
words on a commercial hostname and embedded suffixes such as `.edu.evil.com` are
rejected. The search result's title and description help select a URL only. A snippet
never becomes an
`EvidenceClaim`; the selected URL must pass through Tavily Extract and the structured
grounding boundary.

On the second extraction pass, already Verified records are retained unchanged. Only
partial records with a selected alternate source are processed, and new claims merge
with prior evidence. The retry budget is limited to one, so the loop cannot continue
indefinitely. If five records are fully Verified after the retry, the graph may proceed
while preserving other partial records for audit. Otherwise it ends with the clear,
recoverable `evidence_incomplete` status.

## Walking-skeleton orchestration

```mermaid
flowchart TD
    START([START]) --> Load[load_candidate_preferences]
    Load --> Plan[plan_supervisor_searches]
    Plan -->|valid| Discover[discover_prospective_supervisors]
    Plan -->|failure| END([END])
    Discover --> Found[enough_supervisors_found]
    Found -->|retry You.com| Discover
    Found -->|fallback| Fallback[fallback_supervisor_search]
    Fallback --> Found
    Found -->|sufficient| Dedupe[deduplicate_supervisors]
    Found -->|stopped| END
    Dedupe --> Extract[extract_supervisor_evidence]
    Extract --> Evidence[supervisor_evidence_sufficient]
    Evidence -->|partial and retry unused| Alternate[retry_alternate_evidence_source]
    Alternate --> Extract
    Evidence -->|minimum Verified| Evaluate[evaluate_research_fit]
    Evidence -->|below minimum after retry| END
    Evaluate --> Review[review_fit_assessments]
    Review --> Synthesize[synthesize_supervisor_shortlist]
    Synthesize --> Gate[candidate_review_gate_stub]
    Gate -->|approve| Save[save_shortlisted_supervisors]
    Gate -->|reject or request more| Plan
    Gate -->|exhausted| END
    Save --> Brief[generate_shortlist_briefing]
    Brief --> END

    classDef human fill:#fff4cc,stroke:#9a6b00,stroke-width:2px;
    class Gate human;
```

The graph-derived M2 diagram remains the topology baseline in
[`m2-walking-skeleton.mmd`](m2-walking-skeleton.mmd). M3 adds planning failure routing,
M4 replaces discovery, M5 activates resilient search fallback, and M6 replaces the
evidence path without introducing additional operational nodes.

## Typed state and reducers

```mermaid
flowchart LR
    STATE[ScholarPathState] --> HIST[Append-only history]
    STATE --> SNAP[Canonical snapshots]
    STATE --> CONTROL[Routing control]
    HIST --> SA[search_attempts]
    HIST --> EA[evidence_extraction_attempts]
    HIST --> ERR[tool_errors]
    HIST --> LOG[execution_log]
    SNAP --> PS[prospective_supervisors]
    SNAP --> VR[verification_records]
    SNAP --> VS[verified_supervisors]
    SNAP --> AES[alternate_evidence_sources]
    CONTROL --> RETRY[retry_counts]
    CONTROL --> STATUS[review_status]
```

| State category | M6 channels | Merge behavior |
|---|---|---|
| Immutable Candidate input | `candidate_profile` | Preserved |
| Append-only history | preferences, raw search results, feedback, errors, search attempts, evidence extraction attempts, execution log | Reducers append events |
| Verification snapshots | `verification_records`, `verified_supervisors` | Node returns the complete current ordered snapshot |
| Alternate-source selection | `alternate_evidence_sources` | Deterministic dictionary replacement keyed by `supervisor_id` |
| Other entity snapshots | Prospective Supervisors, Research Fit assessments, proposed and Shortlisted Supervisors | Latest node output replaces prior snapshot |
| Unique terminal history | Rejected Supervisors | Reducer merges by `supervisor_id` |
| Routing control | discovery round, retry counts, review status, fallback flags | Deterministic replacement |

Each `EvidenceExtractionAttempt` preserves Supervisor ID, exact source URL, source
kind, attempt number, discovery round, whether it was alternate, success, and a typed
error category. It does not store a full page or provider exception text. Planning a
new discovery round clears verification snapshots and the alternate-source map while
retaining append-only attempt history.

## Optional M6 LangSmith observability

```mermaid
flowchart LR
    Env[LANGSMITH_TRACING] --> Enabled{Enabled?}
    Enabled -->|no| Off[No LangSmith client]
    Enabled -->|yes| Key[Validate key]
    Key --> Client[Client hides inputs and outputs]
    Client --> Root[scholarpath_graph]
    Root --> PlanTrace[planning node metadata]
    Root --> EvidenceTrace[evidence node metadata]
    Tags[environment plus graph-version:m6] --> Root
```

The graph version is `m6`. Root tags are
`environment:<SCHOLARPATH_ENVIRONMENT>` and `graph-version:m6`. Planning and evidence
nodes add only component and prompt-version metadata. The fixed metadata allowlist is:

- `application`
- `environment`
- `graph_version`
- `component`
- `prompt_version`

The evidence node records `component=evidence_verification_agent` and
`prompt_version=evidence-verification-v1`. Source URLs, full page content, Candidate
identifiers, names, email addresses, research statements, and API keys are not allowed
in trace metadata. The LangSmith client also uses `hide_inputs=True`,
`hide_outputs=True`, and omits runtime information, which is especially important
because the model input necessarily contains the retrieved page.

Tracing remains optional. When disabled, ScholarPath uses an explicitly disabled
tracing context and constructs no LangSmith client.

## Configuration and deferred provider activation

```mermaid
flowchart TB
    OAI[OPENAI_API_KEY] --> OP[OpenAIPlanningSettings]
    OAI --> OE[OpenAIEvidenceSettings]
    OP -->|planning requested| OPA[Planning adapter]
    OE -->|retrieved page ready| OEA[Evidence adapter]
    YDC[YDC_API_KEY and YOU_SEARCH_*] --> YOU[YouSearchAdapter]
    TKEY[TAVILY_API_KEY] --> TS[TavilySearchSettings]
    TKEY --> TE[TavilyExtractionSettings]
    TS -->|fallback or alternate search selected| TSA[TavilySearchAdapter]
    TE -->|known URL extraction requested| TEA[TavilyExtractionAdapter]
    LS[LANGSMITH_*] --> LSC[LangSmith activation]
```

Provider-specific settings may load without credentials. Compiling the graph or
importing ScholarPath does not validate OpenAI, You.com, Tavily, or LangSmith keys.
OpenAI evidence settings are validated only when a retrieved page reaches the lazy
evidence adapter. Tavily Extract settings are validated only when content extraction
is requested. Tavily search remains lazy until discovery fallback or alternate
official-source search requires it.

M6 environment variables are:

| Boundary | Variables |
|---|---|
| OpenAI planning | `OPENAI_API_KEY`, `OPENAI_PLANNING_MODEL`, `OPENAI_PLANNING_TIMEOUT_SECONDS` |
| OpenAI evidence | `OPENAI_API_KEY`, `OPENAI_EVIDENCE_MODEL`, `OPENAI_EVIDENCE_TIMEOUT_SECONDS` |
| You.com search | `YDC_API_KEY`, `YOU_SEARCH_ENDPOINT`, `YOU_SEARCH_TIMEOUT_SECONDS`, `YOU_SEARCH_RESULT_COUNT` |
| Tavily search | `TAVILY_API_KEY`, `TAVILY_SEARCH_TIMEOUT_SECONDS`, `TAVILY_SEARCH_RESULT_COUNT` |
| Tavily Extract | `TAVILY_API_KEY`, `TAVILY_EXTRACT_PROVIDER_TIMEOUT_SECONDS`, `TAVILY_EXTRACT_REQUEST_TIMEOUT_SECONDS`, `TAVILY_EXTRACT_DEPTH`, `TAVILY_EXTRACT_MAX_CONTENT_CHARACTERS` |
| LangSmith | `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` |

The Tavily Extract application request timeout must be greater than its provider
timeout. API keys use `SecretStr`, remain in environment variables, and are never
written into repository files or graph error records.

## Dependency direction

```mermaid
flowchart LR
    CLI[cli] --> GRAPH[graph]
    UI[ui] --> GRAPH
    GRAPH --> DOMAIN[domain]
    GRAPH --> AGENTS[agents]
    GRAPH --> SEARCHPORT[SupervisorSearchPort]
    GRAPH --> CONTENTPORT[ContentExtractionPort]
    AGENTS --> PLANPORT[PlanningModelPort]
    AGENTS --> EVIDENCEPORT[EvidenceVerificationModelPort]
    PLANPORT --> OPENAI[LangChain OpenAI]
    EVIDENCEPORT --> OPENAI
    SEARCHPORT --> YOU[YouSearchAdapter and httpx]
    SEARCHPORT --> TSEARCH[TavilySearchAdapter]
    CONTENTPORT --> TEXTRACT[TavilyExtractionAdapter]
    TSEARCH --> TSDK[langchain-tavily]
    TEXTRACT --> TSDK
    GRAPH --> LANGGRAPH[LangGraph and LangChain Core]
    OBS[LangSmith observability] --> GRAPH
    CONFIG[config] -. settings .-> OPENAI
    CONFIG -. settings .-> YOU
    CONFIG -. settings .-> TSEARCH
    CONFIG -. settings .-> TEXTRACT
```

Domain contracts remain independent of LangGraph and provider SDKs. Transport adapters
depend on provider libraries and return provider-neutral typed values. Agents depend
on typed ports and domain schemas. The graph composes those boundaries and owns finite
routing.

## Physical package layout

The flattened physical `src/` tree remains mapped directly to the `scholarpath` import
namespace:

```text
src/
├── __init__.py
├── cli.py
├── config.py
├── domain/
│   ├── enums.py
│   ├── lifecycle.py
│   └── models.py
├── agents/
│   ├── evidence_verification.py
│   ├── openai_evidence.py
│   ├── openai_planning.py
│   ├── prompts.py
│   ├── research_planning.py
│   └── supervisor_discovery.py
├── graph/
│   ├── discovery.py
│   ├── state.py
│   ├── verification.py
│   └── workflow.py
├── observability/
│   └── tracing.py
└── tools/
    ├── content_extraction.py
    ├── supervisor_search.py
    ├── tavily_extraction.py
    ├── tavily_search.py
    └── you_search.py
```

Setuptools maps these physical paths onto `scholarpath.*`; no additional physical
`src/scholarpath/` directory is required.

## Operational trade-offs and NFRs

| Concern | M6 control | Trade-off or remaining risk |
|---|---|---|
| Evidence integrity | Every direct claim has a source URL, retrieval time, conservative source kind, matching asserted name, and checked excerpt; IDs hash all semantic fields | Textual grounding proves presence and subject binding, not that a page itself is truthful |
| Availability safety | Only explicit typed accepting or not-accepting statements are retained; absence stays `not_stated` | Institutional pages may be stale, so freshness policy remains limited |
| Conflict safety | Conflicting affiliations remain linked and visible | M6 surfaces conflicts but does not adjudicate them |
| Reliability | Typed errors, application deadlines, one alternate retry, partial-result preservation, recoverable terminal status | A two-source cap may miss a valid third official source |
| Security | Deferred secrets, public-URL checks, sanitized errors, bounded content, hidden trace inputs/outputs | Institution pages and model inputs still leave the application boundary and require governance review |
| Privacy | Full page content is transient and excluded from state and trace metadata | Concise evidence excerpts remain persisted because they are required provenance |
| Latency | Sequential known-URL extraction with explicit deadlines | Worst-case latency grows with the number of Prospective Supervisors and one alternate pass |
| Cost | One extraction and structured-model call per processed URL; alternate calls are bounded | M6 has no cross-run cache, batching, or provider budget accounting |
| Scalability | Provider ports support fakes and later alternative adapters | Current synchronous orchestration and sequential calls defer concurrency and backpressure |
| Determinism | IDs, grounding, conflict links, sufficiency, availability, routing, and retry arithmetic use Python | Claim wording and confidence remain model-variable |
| Observability | M6 graph, planning, and evidence prompt versions are traceable with safe metadata | Evaluation datasets, quality dashboards, and alerts remain deferred |
| Termination | Search, evidence, and review loops use validated finite budgets | LangGraph recursion limit remains defense-in-depth, not the primary termination rule |

The synchronous Tavily adapters currently bridge the provider's async invocation with
`asyncio.run()`. An async port is deferred before embedding ScholarPath inside an
already-running event-loop runtime.

## M6 quality boundaries

| Concern | Control |
|---|---|
| Packaging | Flattened physical `src/` mapped to the `scholarpath` namespace |
| Planning | Versioned strict structured output; no search tools; one visible format retry |
| Discovery | You.com primary, official Tavily fallback, deterministic quality policy and provenance merge |
| Extraction | One-URL `ContentExtractionPort`, official Tavily Extract, public-URL checks, dual timeouts and content cap |
| Evidence model | Injected typed port, versioned prompt, strict native schema, no prose parsing |
| Grounding | Every direct excerpt occurs in retrieved content, explicitly names the expected Supervisor, and passes type-specific deterministic checks |
| Verification | Identity, current institution and department, plus research interest or publication are mandatory |
| Partial work | Separate `SupervisorVerificationRecord`; partial records never masquerade as Verified Supervisors |
| Availability | Explicit name-bound evidence with deterministically matched polarity only; absence remains `not_stated` |
| Conflicts | Both affiliation claims and cross-referenced evidence IDs are preserved |
| Retry | One deterministic alternate official-source search and extraction pass |
| Network isolation | Default tests use fixed pages and fakes; `live` is excluded by default |
| Observability | `graph-version:m6`, prompt versions, allowlisted metadata, hidden inputs and outputs |
| Human authority | Candidate approval remains mandatory before Shortlisted status |
| Research Fit | Still fixture-backed; no M6 scoring model or arithmetic added |

## Runtime and verification commands

From `projects/scholar-path`:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]" --config-settings editable_mode=strict
cp .env.example .env

ruff format --check .
ruff check .
mypy src tests
pytest -m "not live"
```

The production CLI path now requires the planning and discovery credentials and, when
evidence processing begins, the evidence boundaries:

```bash
# Set OPENAI_API_KEY, YDC_API_KEY, and TAVILY_API_KEY in ignored .env first.
python -m scholarpath.cli
```

Optional provider smoke tests require both their credential and explicit opt-in:

```bash
SCHOLARPATH_RUN_LIVE_TESTS=true \
pytest -o addopts='' -q -m live tests/integration/test_openai_planning_live.py

SCHOLARPATH_RUN_LIVE_TESTS=true \
pytest -o addopts='' -q -m live tests/integration/test_you_search_live.py

SCHOLARPATH_RUN_LIVE_TESTS=true \
pytest -o addopts='' -q -m live tests/integration/test_tavily_search_live.py

SCHOLARPATH_RUN_LIVE_TESTS=true \
pytest -o addopts='' -q -m live tests/integration/test_tavily_extraction_live.py
```

The Tavily extraction smoke test retrieves one bounded public documentation page and
asserts normalized non-empty content, HTTPS provenance, the content cap, and an aware
retrieval timestamp. Default test runs skip it and make no network call.

## Deferred beyond M6

- Real Research Fit calculation, scoring policy, and score calibration
- Independent evidence and fit review through Nebius
- Multi-source freshness and source-authority weighting beyond one alternate page
- Deterministic conflict adjudication with an explicit policy and Candidate visibility
- Concurrent or batched extraction, caching, quotas, rate limiting, and circuit breakers
- Per-Supervisor durable checkpoints inside a long extraction node
- An async provider-port variant for already-running event loops
- Real Candidate interruption, rejection feedback, and workflow resumption
- Streamlit user experience
- Mem0 preference learning
- LangSmith evaluation datasets, scoring, dashboards, and alerting
