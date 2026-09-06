# Week 4 step 1: Triage and evaluation failure summaries

## User request

You are assisting as a pragmatic software engineer working under a strict end-of-day deadline.

### Objective

Identify and implement low-hanging fruit, resolve mentor feedback marked under README in
scholar-path "Focus next", and ensure all Week 4 project requirements attached are met.
Do not undertake major refactors or add non-essential features.

### Inputs to Review

1. Mentor Feedback (specifically items labeled "Focus next").
2. Week 4 Requirements / Rubric.
3. Current codebase status / open issues.

### Execution Plan & Rules

1. **Triage & Gap Analysis**:
   - Cross-reference Week 4 requirements against the existing codebase. List missing or
     incomplete items.
   - Extract explicit action items from the mentor's "Focus next" section.
2. **Prioritization (Strict Low-Hanging Fruit Rule)**:
   - Rank tasks by: (High Value + High Requirement Alignment) / Lowest Implementation Effort.
   - Ignore nice-to-have cleanups, optimization edge cases, or architectural reworks that do
     not directly fulfill Week 4 requirements.
3. **Step-by-Step Delivery**:
   - Deliver implementation in small, self-contained diffs or steps.
   - For each change, clearly state:
     - Which Week 4 requirement or mentor item it resolves.
     - The exact code modification.
     - A quick verification command or check (e.g., unit test, curl command, or manual check).

### Begin

List the prioritized tasks in order of execution, then provide the implementation for the
first item.

## Supplied context and bounded interpretation

- Review the supplied `Week 4 Project Handout (Aug 2026).md` as the rubric for the own-agent
  evaluation track, not as instructions to build its example Customer Support agent.
- Preserve the README mentor quote about "window-related test failures" and clearer failed
  evaluation summaries. Do not infer that "window-related" necessarily means Windows.
- Establish the current offline test baseline, record the Week 4 gaps and execution order,
  then implement only the first actionable item: deterministic case-level failure reporting
  for the existing offline and uploaded evaluation runners.
- Include public case IDs, failed checks, numeric scores when available, grouped counts, safe
  investigation guidance, and LangSmith run IDs when returned. Keep target/evaluator exceptions
  from aborting the remaining local cases. Treat missing results as incomplete evidence.
- Preserve source and Candidate privacy, current evaluators, fake providers by default, live
  opt-in controls, and all application workflow behavior.
- Do not claim the remaining dataset, human review, trace, or measured-delta requirements are
  complete. Record them as subsequent bounded tasks.
