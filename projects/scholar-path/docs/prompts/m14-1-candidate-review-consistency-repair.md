# ScholarPath M14.1: Candidate review consistency repair

## User prompt

> Once i reject a supervisor, that name should not be present in the approvers list. Can we fix
> this bug.
> Also while I was doing the demo when I proceed with approved, instead of displaying approved
> list, it stayed at Verified Supervisors

## Bounded interpretation

Repair only the Candidate-review consistency boundary:

1. Treat a rejected Supervisor as the same person across deterministic provider identity aliases,
   without using name-only matching or an LLM.
2. Exclude rejected Supervisors during discovery, shortlist synthesis, and Candidate-facing review
   projection.
3. Reset review-form values whenever the persisted review checkpoint changes so stale selections
   cannot survive a rejection/refinement cycle.
4. After approval, render the persisted Supervisor shortlist as the primary active stage instead
   of repeating earlier Prospective and Verified Supervisor sections above it.
5. Preserve thread-scoped persistence, explicit Candidate approval, evidence provenance, bounded
   routing, and sanitized error handling.
6. Add unit, graph, and Streamlit regression tests; do not add or change providers, scoring,
   verification policy, memory policy, or outreach behavior.

