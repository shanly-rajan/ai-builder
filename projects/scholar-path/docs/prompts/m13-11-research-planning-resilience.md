# M13.11 bounded repair prompt: Research Planning resilience

## Prompt used

> the MVP research run was working but now its not

The supplied screenshot showed the run stopping before discovery with:

> Research planning could not produce a valid typed SearchPlan.

## Bounded interpretation

- Diagnose and repair only the Research Planning structured-output and retry boundary.
- Keep the existing two-attempt ceiling and prohibit hidden SDK retries.
- Preserve provider-portable query limits; normalize only excess quote marks because deleting
  filters or Boolean operators can change query semantics.
- Distinguish invalid structured output from provider invocation failure without exposing content.
- Do not change MVP verification, discovery, evidence, Research Fit, memory, or approval behavior.
