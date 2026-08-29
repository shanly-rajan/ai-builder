# ScholarPath M11.2 Discovery-Completion Repair Prompt

Proceed with the next bounded repair after a live Streamlit run produced 106 raw search
results, four plausible and retained Prospective Supervisors, no provider errors, and a
recoverable stop because the minimum of five was not reached.

Implement only this M11.2 repair:

1. Reject incomplete institution fragments whose final token is a dangling connector such
   as `and`, `at`, `for`, `of`, `the`, or `with`. Continue scanning bounded result context
   for a complete institution; otherwise reject the result. The observed UEL-shaped result
   must resolve from `University of` to `University of East London` without a model call.
2. Keep the Tavily fallback budget unchanged. Order fallback queries deterministically by
   the latest current-round You.com plausible-profile count descending, with original
   SearchPlan order as the stable tie-breaker. Queries with zero plausible profiles follow
   productive queries in original order.
3. Add a typed, deterministic aggregate rejection taxonomy for search results. It must
   distinguish at least person not established, academic context not established, identity
   conflict, institution not established, and incomplete institution.
4. Persist fixed rejection counts on each successful SearchAttempt and project current-round
   aggregates into Streamlit and LangSmith diagnostics.
5. Trace and UI diagnostics may contain only fixed category counts plus the existing safe
   provider, attempt, count, error, fallback, and route fields. Never include query text,
   Candidate content, names, URLs, snippets, raw results, page content, or secrets.
6. Preserve exact discovery provenance, deterministic deduplication, retry limits, provider
   budgets, the minimum-five discovery gate, evidence rules, Research Fit, independent
   review, memory, Candidate approval, and shortlist behavior.
7. Keep all default tests offline. Add unit, graph, contract, integration, AppTest, trace,
   old-checkpoint compatibility, and adversarial regressions appropriate to this repair.

Do not add a provider, model, search call, retry, or downstream workflow change.
