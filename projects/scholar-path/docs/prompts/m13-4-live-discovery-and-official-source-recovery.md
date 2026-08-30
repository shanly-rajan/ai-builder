# Milestone M13.4 Prompt: Live discovery identity and official-source recovery

Implement one bounded repair after a provider-backed Streamlit run found Prospective Supervisors
for a broad artificial-intelligence and software-engineering research profile but completed zero
Supervisor verifications.

The current privacy-safe diagnostics identify two interpretation bottlenecks:

- discovery retained organization or department titles as people, repeated a person's exact name
  and trailing role in one identity, or retained an incomplete institution such as
  `University of St`;
- alternate official-source searches returned results, but deterministic selection rejected them
  before a stronger official profile could be retrieved.

Implement only this repair:

1. Keep discovery deterministic and provider-neutral. Reject organization and department titles
   that do not establish a person, including a department name shaped like a proper noun.
2. Treat a terminal `University of St` or `University of Saint` as incomplete while preserving
   complete institutions such as `University of St Andrews`.
3. Canonicalize a malformed title such as `Prof. Yan Liu Yan Liu Director` only when an explicit
   academic prefix is followed by the same exact two-or-more-token person name twice and then a
   bounded trailing academic role. Retain `Prof. Yan Liu` and preserve the exact discovery URL,
   provider, and query. Do not introduce general fuzzy name repair.
4. Preserve every existing conservative person, academic-context, institution, topic, provenance,
   rejection-taxonomy, and deduplication boundary for all other results.
5. Keep the existing alternate-source query, provider budget, and one-retry limit. Extend only the
   deterministic institution-correlation gate so an alternate result can proceed when either:
   - the exact normalized institution phrase occurs in the result title or description; or
   - a controlled academic hostname strongly correlates to the expected institution through an
     exact meaningful-label concatenation, exact institution token, or exact acronym, and the
     result title contains no explicit conflicting University, College, or Institute. A weak
     hostname prefix is insufficient.
6. Preserve the remaining selector order: query binding, primary-URL difference, HTTPS and valid
   host, exact normalized person text, institution correlation, singular person-profile route
   bound to that person or an opaque numeric identifier, academic-host validation, and supported
   official source kind.
7. Search titles, descriptions, snippets, and hostnames may select a URL only. They must never
   become Supervisor evidence or establish affiliation, research interests, publications,
   availability, or Research Fit. Retrieved page claims must still satisfy the authoritative
   evidence-grounding and verification rules.
8. Keep every alternate result assigned to exactly one existing first-failed selector category.
   Preserve aggregate-only diagnostics, exact result accounting, replay safety, and checkpoint
   compatibility; add no identity, query, URL, content, or credential to the diagnostic view.
9. Do not add a provider, search call, model call, retry, graph edge, runtime profile, or
   configuration switch. Do not lower the five-Verified-Supervisor minimum or one-alternate-source
   retry. Do not advance a partially verified Supervisor to Research Fit or Candidate review.
10. Keep availability separate, prohibit admission probability, and preserve explicit Candidate
    approval before shortlist persistence or outreach drafting.

Add fixed offline regressions for organization-title rejection, exact duplicated-name repair,
near-match and non-academic negative cases, incomplete versus complete `St` institution names,
exact-phrase and host-correlated alternate-source selection, explicit institution conflict,
wrong-person and collection-page rejection, first-failed result accounting, graph continuation,
unchanged verification thresholds, terminology, documentation, and repository contracts.

Update the active README, architecture, saved prompt, and build journal. Run formatting, linting,
type checking, the focused offline regressions, and the complete non-live test suite. Do not call
live providers, inspect secrets, introduce an exploratory runtime profile, or tune the
verification minimum in this milestone.
