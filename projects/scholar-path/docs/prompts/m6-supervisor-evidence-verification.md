Implement ScholarPath Milestone M6: Supervisor evidence extraction and
verification.

Replace the fixture implementations of:

- extract_supervisor_evidence
- supervisor_evidence_sufficient
- retry_alternate_evidence_source

Create:

- ContentExtractionPort
- TavilyExtractionAdapter
- EvidenceVerificationAgent
- VerificationPolicy
- Pure evidence-sufficiency routing function

For each Prospective Supervisor, gather evidence for:

1. Identity.
2. Current institution and department.
3. Stated research interests or areas of expertise.
4. Recent publication or project evidence.
5. Explicit supervision availability, only when directly stated.

Use Tavily Extract against known URLs. Where the original profile cannot be
retrieved, search for one alternate official source and retry extraction once.

Every EvidenceClaim must preserve:

- exact claim
- source URL
- source kind
- retrieval timestamp
- whether the source directly supports the claim
- confidence
- any conflicting evidence

Verification rules:

- Identity evidence is mandatory.
- Current affiliation evidence is mandatory.
- Research-interest or publication evidence is mandatory.
- Availability evidence is optional.
- Missing availability must remain not_stated.
- Conflicting affiliation must be surfaced, not silently resolved.
- Model knowledge may not be used as evidence.
- Search snippets alone must not be treated as full verification where a
  stronger page source is available.

Use structured model output to extract claims from retrieved page content.
The model may extract and classify evidence but may not invent missing facts.

Add tests using fixed HTML or Markdown fixtures for:

1. Complete official university profile.
2. Missing affiliation.
3. Missing research evidence.
4. Availability not stated.
5. Explicitly accepting doctoral Candidates.
6. Explicitly not accepting doctoral Candidates.
7. Conflicting affiliations.
8. Failed page extraction followed by an alternate source.
9. Retry exhaustion producing partially_verified rather than fabricated data.
10. Every Verified Supervisor retaining evidence IDs and source URLs.
11. No live network calls in default tests.

Do not implement Research Fit scoring yet.
