# Architecture

## Scope and context

The Cricket RAG Engine is a synchronous learning prototype. It converts one local
plain-text fixture, `data/sample/laws.txt`, into Pinecone vectors and uses retrieved
clauses to augment an OpenAI-generated response to a match scenario.

The current boundary is intentionally narrow:

```text
Input corpus: data/sample/laws.txt only
Input query:  one cricket-law question or scenario
Output:       generated verdict or operational warning, plus law references when available
Interfaces:   Python CLIs and a session-state Streamlit chat UI
```

It is not a complete laws platform, live cricket data system, deterministic rules
engine, or production API.

## Component view

```mermaid
flowchart TB
    Operator[Developer / operator]
    User[User]

    subgraph Application[Cricket RAG Engine]
        Config[src/config.py]
        Parser[src/ingestion/parser.py]
        Indexer[src/ingestion/indexer.py]
        Retriever[src/retrieval/retriever.py]
        Chain[src/generation/chain.py]
        UI[app.py conversational chat]
        Eval[src/evaluation/evaluator.py]
    end

    Corpus[(data/sample/laws.txt)]
    OpenAI[OpenAI embeddings and chat]
    Pinecone[(Pinecone Serverless index)]
    Report[(evaluation_report.md)]

    Operator --> Indexer
    Corpus --> Parser --> Indexer
    Config --> Indexer
    Indexer --> OpenAI
    Indexer --> Pinecone

    User --> UI --> Chain
    Config --> Retriever
    Chain --> Retriever
    Retriever --> OpenAI
    Retriever --> Pinecone
    Chain --> OpenAI

    Operator --> Eval --> Chain
    Eval --> Report
```

The provider integrations are direct dependencies rather than replaceable adapter
interfaces. Unit tests isolate them with mocks.

## Ingestion sequence

```mermaid
sequenceDiagram
    actor Operator
    participant I as index_documents
    participant P as parse_mcc_laws
    participant O as OpenAI Embeddings
    participant V as Pinecone

    Operator->>I: Run python -m src.ingestion.indexer
    I->>V: List indexes
    alt Configured index does not exist
        I->>V: Create cosine index (AWS us-east-1)
        loop Until ready
            I->>V: Describe index status
        end
    end
    I->>P: Parse data/sample/laws.txt
    P-->>I: 11 Documents + metadata
    loop Each document
        I->>O: Embed document text
        O-->>I: 1,536-value vector by default
    end
    I->>V: Upsert batches with law_chunk_N IDs
    V-->>I: Upsert accepted
```

Important current semantics:

- Parsing splits at `LAW` and `x.y` headings. `x.y.z` clauses remain grouped inside
  their parent section document.
- Four of the 11 documents are Law-header-only chunks.
- IDs are based on list position, not source content, so they are not durable across
  insertions or reordering.
- Re-indexing updates reused IDs but does not remove stale higher-numbered vectors.
- Existing index dimension, metric, cloud, and region are not validated.

## Query and adjudication sequence

```mermaid
sequenceDiagram
    actor User
    participant C as CLI / Streamlit chat
    participant A as CricketAdjudicationEngine
    participant R as CricketRetriever
    participant O as OpenAI
    participant V as Pinecone

    User->>C: Submit scenario and top-k
    Note over C: UI stores transcript and citations in session state
    C->>A: adjudicate(query, top_k)
    A->>R: retrieve(query, top_k)
    alt Retrieval succeeds
        R->>O: Embed query
        O-->>R: Query vector
        R->>V: top-k cosine query + metadata
        V-->>R: Matches
        Note over R: Similarity scores are discarded
        R-->>A: LangChain Documents
        A->>A: Format retrieved context
        A->>O: Invoke grounded chat prompt<br/>(max_retries=3, timeout=30s)
        alt Generation succeeds
            O-->>A: Generated adjudication
            A-->>C: Verdict + retrieved Documents
        else OpenAIError after client handling
            O--xA: Provider exception
            A->>A: Log error
            A-->>C: API warning + retrieved Documents
        else Other generation exception
            A->>A: Log exception class
            A-->>C: Engine warning + retrieved Documents
        end
    else Retrieval fails
        R--xA: Query embedding or vector-store exception
        A->>A: Log error
        A-->>C: Vector Index warning + empty Documents
    end
    C-->>User: Append answer or warning and inline citations
```

There is no relevance-score gate between retrieval and generation. The prompt asks
the model to refuse unsupported questions and cite laws, but code does not validate
the resulting claims, references, signals, or abstention.

The Streamlit transcript is presentation state only. Each submission sends the current
question and newly retrieved context to the chain; previous chat turns are displayed
but are not included in the model input. Adjudication encodes operational failures as
warning strings in the normal return tuple rather than a typed error contract.

## Data contracts

### Parsed document metadata

| Field | Meaning |
|---|---|
| `law_number` | Current Law number inferred from the latest Law heading |
| `law_title` | Current Law title |
| `section` | Section heading, or `Law <number>` for a header chunk |
| `source` | Static `MCC Laws of Cricket` label |

### Pinecone record

```text
id       = law_chunk_<ordinal>
values   = OpenAI embedding vector
metadata = parsed metadata + full chunk text under "text"
```

The retriever removes `text` from metadata and uses it as the returned Document's
`page_content`.

## Runtime and failure paths

| Failure | Current behavior | Consequence |
|---|---|---|
| Missing environment variable | Constructor raises `ValueError` | CLI or UI startup fails |
| Missing corpus file | Parser raises `FileNotFoundError` | Indexing stops |
| Provider/network/quota failure during indexing | Provider exception propagates | Indexing stops; partial writes are possible |
| Provider failure from the direct retrieval CLI | Provider exception propagates | Retrieval command fails |
| Query-embedding or Pinecone-query exception during adjudication | Broadly caught and logged; returns a `Vector Index Error` warning and an empty document list | Generation is skipped; an embedding failure may be mislabeled as a vector-index problem |
| `OpenAIError` during chat generation | `ChatOpenAI` is configured with `max_retries=3` and a 30-second timeout; final failure is logged and returned as a warning with retrieved documents | The request completes with citations available for manual review |
| Other generation exception | Logged; the warning includes the exception class and preserves retrieved documents | The request completes, but the operational error is encoded as display text |
| Pinecone index absent at adjudication time | Follows the caught retrieval-error path | No model invocation and no citations |
| Irrelevant top-k results | Results still reach the model | Unsupported or overconfident answer risk |
| Empty matches | Prompt receives fallback text | Refusal remains model-dependent |
| Partial indexing | No transaction or rollback | Index may contain an incomplete mix |

## Architecture trade-offs and NFRs

| Concern | Current choice | Trade-off / next control |
|---|---|---|
| Simplicity | Direct LangChain, OpenAI, and Pinecone integration | Fast to learn, but tightly coupled and harder to test end to end |
| Grounding | Top-k context plus prompt instructions | Add scores, a relevance threshold, claim checks, and citation validation |
| Security | Secrets loaded from ignored `.env` | Use managed secrets, least-privilege keys, rotation, and audit logging in production |
| Data governance | One committed sample file | Resolve provenance/license and record corpus version metadata |
| Latency | Sequential embedding, retrieval, then generation; retries can extend tail latency | Measure p50/p95, separate retry time, and consider batching/caching only after profiling |
| Cost | Hosted embedding, vector, and chat calls | Record tokens, vector volume, query counts, and cost per evaluation/run |
| Resilience | Chat generation has three configured retries and a 30-second timeout; adjudication translates retrieval and generation exceptions into warnings | Startup and ingestion still fail fast; add a typed error contract, consistent per-stage policies, idempotency, circuit breaking, and failover if needed |
| Scalability | Synchronous UI/CLI and one index | Add async ingestion, namespaces/tenancy, and an API only when required |
| Observability | Module-level error logging, console messages, and a generated report | Add structured logs, traces, run IDs, model/prompt versions, and metrics |

## Next architecture decisions

1. Resolve the sample corpus provenance or replace it with clearly permitted content.
2. Define a versioned canonical chunk and citation contract with content-stable IDs.
3. Retain retrieval scores and establish an evaluated abstention threshold.
4. Add semantic answer, citation, and unsupported-claim evaluation.
5. Decide whether provider ports/adapters are needed before adding another provider.
6. Define typed success/failure results and consistent retry, timeout, and
   circuit-breaker policies across provider calls.
7. Add an authenticated API, operational controls, and observability only if the
   learning prototype becomes a shared service.
