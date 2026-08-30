# M13.1 Privacy-safe evidence-verification diagnostics repair

Implement a bounded diagnostic repair for the existing Supervisor evidence-verification
pipeline.

The current interface reports alternate-source selection separately, but it does not show
where already-selected evidence pages and their retained claims stop progressing through
retrieval, grounding, and verification. Add a deterministic, privacy-safe aggregate view so
operators can distinguish retrieval failures from missing grounded evidence without exposing
Supervisor, Candidate, source, or model content.

Implement only this repair:

- Project diagnostics only from the current discovery round's existing
  `evidence_extraction_attempts` and the current `verification_records`. Do not add graph state,
  extraction attempts, provider calls, model calls, or retries to produce diagnostics.
- Count page retrieval attempts by primary versus alternate source, then split them by successful
  versus failed retrieval. Group failed retrievals only by the existing
  `ContentExtractionErrorCategory` taxonomy.
- Count retained claims and directly supported, grounded claims for every existing
  `EvidenceClaimType`. Use the existing deterministic Supervisor-grounding rule; do not define a
  second grounding policy in the UI.
- Split verification records into completed outcomes (`verified` plus
  `verified_with_concerns`) and `partially_verified` outcomes.
- Aggregate missing verification gates only under the existing safe keys `identity`,
  `current_affiliation`, and `research_interest_or_publication`.
- Keep alternate-source result selection and first-failed selector-gate counts in the existing
  M12.4 diagnostics panel. M13.1 observes retrieval and verification after a source is selected;
  it does not duplicate or reinterpret selector diagnostics.
- Expose aggregate counts only. Omit Supervisor identifiers and names, Candidate content,
  queries, URLs, source references, snippets, claim text, supporting excerpts, page content,
  checkpoint or thread identifiers, credentials, raw provider payloads, and exception text.
- Treat model-accepted draft counts and first-failed grounding reasons as unavailable because
  the existing state does not retain them. Defer those metrics explicitly; do not infer them,
  persist new audit records for them, or relabel retained-claim counts as draft counts.
- Preserve the existing verification and grounding rules, verification minimum, one
  alternate-source retry, graph routing, provider behavior, availability semantics, Research
  Fit behavior, independent review, Candidate approval gate, checkpoint compatibility, and
  replay behavior unchanged.

Add fixed offline tests for deterministic current-round aggregation, primary/alternate and
success/failure accounting, typed retrieval-failure counts, retained and directly grounded
claim-type counts, completed/partial verification counts, missing-gate counts, legacy or early
state, invalid aggregate rejection, privacy-safe projection and rendering, documentation, and
unchanged verification policy/routing contracts. Update the architecture documentation,
Mermaid flow, build journal, and repository contract. Run the focused tests and every repository
quality gate separately. Do not call live providers, inspect secrets, or use production data.
