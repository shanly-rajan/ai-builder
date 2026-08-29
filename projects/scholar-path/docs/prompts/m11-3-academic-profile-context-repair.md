# ScholarPath M11.3 Academic-Profile Context Repair Prompt

Proceed with the next bounded repair after a live M11.2 run returned 101 raw search
results and retained zero Prospective Supervisors. All eleven provider calls succeeded;
35 results did not establish a person, 64 contained a person-like title but did not satisfy
the academic-context gate, two had identity conflicts, and none reached institution
validation.

Implement only this M11.3 repair:

1. Keep Supervisor discovery deterministic and provider-neutral. Do not add a model,
   provider, search call, retry, result, or page retrieval.
2. Preserve conservative identity parsing, but allow an untitled person name when all of
   these independent signals agree:
   - the title contains one plausible person identity;
   - the URL is a singular academic person-profile path, including `/persons/<name>`;
   - at most the first 1,000 description characters plus already bounded snippets explicitly
     and positively relate the same normalized identity to research, publications, scholarly
     work, or research-qualified expertise, interests, or projects;
   - the untitled identity is not an exact expanded research concept or contiguous phrase in
     a planned query;
   - a complete institution comes from the title or an explicit owner-linked affiliation
     clause, never a collaborator or collaboration target.
3. Do not accept a bare capitalized topic title plus a research keyword. Generic topic,
   directory, listing, news, publication, non-academic, and clinical pages must remain
   excluded unless the full conjunction above is satisfied.
4. Treat additional named academics as co-mentions when the bounded context independently
   supports the title identity. Preserve `identity_conflict` when contextual academic names
   exist but none supports the title identity.
5. Preserve common institution-first SEO titles only when a later titled identity matches
   the singular profile URL. A later different titled person must never replace or support
   the primary title identity.
6. Keep each raw result assigned to exactly one existing rejection category when excluded.
   Do not add result content, names, queries, URLs, snippets, or page text to graph audit,
   Streamlit, or LangSmith diagnostics.
7. Preserve exact provenance, deterministic deduplication, provider budgets, retry limits,
   the minimum-five gate, checkpoint compatibility, evidence rules, Research Fit,
   independent review, memory, Candidate approval, and shortlist behavior.
8. Keep all default tests offline. Add unit, graph, integration, adversarial, terminology,
   privacy, and repository-contract regressions appropriate to this repair.

Do not change Research Planning or fallback ordering in this repair. If live completion
remains weak after M11.3, evaluate source-specific query intent as a separate later repair.
