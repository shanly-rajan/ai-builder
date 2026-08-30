# M12.4 Privacy-safe alternate-source diagnostics repair

Implement a bounded diagnostic repair for alternate official-source selection.

The latest persisted live run showed that primary pages were retrieved but most
partially verified Supervisors had no selected alternate official source. The existing
recoverable error did not distinguish an empty search response from a result rejected
for identity, institution, URL, host, route, or source-kind safety.

Implement only this repair:

- Add typed alternate-source attempt, outcome, and first-failed selector-gate schemas.
- Account for every returned result exactly once as eligible or rejected by its first
  failed deterministic gate.
- Distinguish `selected`, `no_results`, `rejected_all`, `provider_error`, and
  `not_configured` outcomes.
- Persist replay-safe attempt records by discovery round, bounded attempt number, and
  opaque Supervisor ID, including counts and typed provider-error category only.
- Project only current-round aggregate counts into Streamlit. Do not expose Supervisor
  identities, queries, result text, URLs, retrieved pages, Candidate research content,
  thread IDs, credentials, or provider exception text in the diagnostic view.
- Preserve the existing selector order and select the first eligible official source.
  Do not weaken exact person, exact institution, HTTPS, singular person-route,
  academic-host, or supported-source-kind checks.
- Preserve older checkpoint compatibility and idempotent resume behavior.
- Keep the existing provider choices, verification minimum, one alternate-source pass,
  evidence rules, availability status, Research Fit behavior, independent review, and
  Candidate approval gate unchanged.

Add fixed offline tests for complete result accounting, distinct outcomes, invalid
aggregate rejection, replay-safe reduction, graph routing, SQLite round trips,
current-round UI projection, legacy state, and privacy-safe Streamlit rendering. Update
the README, architecture, Mermaid diagram, build journal, graph version, evaluation
baseline identifier, and repository contracts. Run every quality gate separately. Do
not call live providers or inspect secrets.
