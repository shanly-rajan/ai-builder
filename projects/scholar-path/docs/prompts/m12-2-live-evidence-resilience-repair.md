# M12.2 Live discovery and evidence resilience repair

Repair the live ScholarPath run that retained an incomplete person identity, treated an
academic programme title as an institution, discarded complete page-level evidence when one
model claim was invalid, and failed to select plausible alternate official profiles.

Implement only this bounded repair:

- Reject a discovered person identity whose final substantive name token is only an initial.
- Reject programme, course, workshop, conference, training, and host-attribution labels as
  institutions without inferring the host as the person's affiliation.
- Preserve valid sparse official-profile layouts and legitimate standalone school names.
- Keep native typed structured output, but validate and ground every returned evidence draft
  independently so one invalid draft cannot discard unrelated valid claims.
- Never persist an ungrounded claim. Omit same-page contradictory availability drafts so the
  availability status remains `not_stated`.
- Build alternate-source queries from a title-free person name and accept only attributable
  HTTPS academic person-profile pages.
- Keep verification sufficiency, one alternate-source pass, provider budgets, provenance,
  append-only graph errors, and the Candidate approval gate unchanged.

Add fixed offline regressions for the exact observed result shape, valid-claim preservation,
same-page availability safety, alternate-profile selection, finite routing, and default
network isolation. Update the architecture, build journal, graph version, evaluation replay
identifier, and repository contracts. Run every quality gate and commit the repair separately.
