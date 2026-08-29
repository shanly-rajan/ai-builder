# Milestone M4 prompt: You.com Supervisor discovery

Implement ScholarPath Milestone M4: You.com Supervisor discovery.

Replace only the fixture implementation of `discover_prospective_supervisors`.

Create:

- `SupervisorSearchPort`
- `YouSearchAdapter`
- `SearchResult` domain model
- `SupervisorDiscoveryAgent`
- Structured `SupervisorDiscoveryResult` output

The `YouSearchAdapter` must:

- Receive one search query at a time.
- Call the current official You.com Web Search API.
- Apply configured timeout and result-count limits.
- Return normalized `SearchResult` objects.
- Preserve URL, title, description, publication date when present, and originating query.
- Contain no domain-specific reasoning.

The Supervisor Discovery Agent must:

- Consume the `SearchPlan` and `SearchResult` objects.
- Identify people who appear to be academics or researchers.
- Produce `ProspectiveSupervisor` objects.
- Retain the exact discovery source and query.
- Exclude results that do not contain a plausible person name and institution.
- Avoid scoring Research Fit.
- Avoid asserting that anyone is accepting doctoral Candidates.

Implement deterministic deduplication using normalized name, institution, and
canonical profile URL. Merge provenance when the same Supervisor is discovered
through multiple queries.

Add tests for:

1. You.com request construction using mocked HTTP.
2. Timeouts and non-success responses mapped to typed errors.
3. Search-result normalization.
4. Empty result sets.
5. Duplicate Prospective Supervisors merged correctly.
6. One Supervisor retaining multiple discovery queries.
7. Non-person results being excluded.
8. No Research Fit Score produced during discovery.
9. No availability inference.
10. One optional live You.com smoke test behind `pytest.mark.live`.

Update the graph to use `YouSearchAdapter` in production and a fake adapter in tests.
Do not add Tavily yet.
