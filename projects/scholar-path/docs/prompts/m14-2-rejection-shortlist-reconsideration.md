# ScholarPath M14.2: Candidate rejection shortlist reconsideration

## User prompt

> As I was rejecting and when I switched to approvers i saw this wierd behavior

The user supplied privacy-safe application logs from the affected research run and asked Codex
to resume the existing Candidate-review repair.

## Bounded interpretation

Repair only the post-rejection route exposed by the supplied logs:

1. Correlate the node log with persisted checkpoint state before changing code.
2. After an explicit rejection, persist the Candidate preference and re-synthesize the existing
   Verified Supervisor cohort without calling planning or search providers again.
3. Exclude rejected Supervisor identities from the next proposal and approval options.
4. Keep `request_more` as the explicit action that launches another bounded planning and provider
   search round.
5. Preserve Candidate approval as mandatory before shortlist persistence.
6. Add graph, application-service, and real Streamlit regressions for reject, immediate re-review,
   approve, and final shortlist rendering.
7. Update current architecture documentation and the generated LangGraph snapshot. Do not alter
   discovery, evidence, Research Fit, independent-review, or memory-provider policies.
