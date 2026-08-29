# ScholarPath M11 Discovery-Quality Repair Prompt

Proceed with the recommended repair after a traced Streamlit run showed that Supervisor
discovery stopped after You.com returned no results and Tavily returned raw results from
which no Prospective Supervisors were retained.

Implement only this bounded M11 repair:

1. Add deterministic, provider-portable query-shape guardrails. Reject over-constrained
   planning output such as queries containing multiple `site:` filters, excessive Boolean
   operators, or excessive quoted phrases through the existing one-retry planning policy.
2. Version the Research Planning Agent prompt and instruct it to emit concise, independent
   searches rather than combining several domains and exact phrases in one query.
3. Preserve bounded You.com snippets as typed `SearchResult` context. Do not retrieve or
   retain full page content at discovery time.
4. Improve deterministic Supervisor identification for realistic search-result titles and
   snippets while continuing to require a plausible person name, academic context, and an
   institution. Do not infer availability or calculate Research Fit.
5. Preserve discovery provenance and deterministic deduplication.
6. Add privacy-safe discovery diagnostics to LangSmith and Streamlit containing only:
   provider, attempt number, result count, plausible Supervisor count, error category,
   fallback usage, and deterministic route. Do not expose query text, Candidate research
   content, raw search results, names, URLs, API keys, or full pages in trace metadata.
7. Replace misleading partial-result UI wording when provider results were returned but zero
   Prospective Supervisors were retained.
8. Honor the configured LangSmith regional endpoint and optional workspace ID from `.env`.
9. Keep default tests fully offline. Add regression, graph, UI, trace, contract, and
   integration coverage appropriate to the repair.

Do not implement evidence, Research Fit, review, memory, or outreach changes in this repair.
