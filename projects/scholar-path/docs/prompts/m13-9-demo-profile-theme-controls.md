# ScholarPath Milestone M13.9 Prompt

## Prompt used

```text
Update tagline to "Evidence-backed supervisor discovery for postgraduate research." Update where masters and doctorate is used to reflect "postgraduate"
Build a demo slider button where the following form fields will be auto-filled so that the reviewer can hit search to see a happy path
Also a slider to toggle between light and dark mode
**Proposed research statement:** Applications of machine learning and artificial intelligence in software engineering.
**Research topics:** Machine Learning, Artificial Intelligence, Software Engineering, Data Science, Computer Science.
**Preferred regions:** *(Leave empty)*
**Study mode:** *(Default / No preference)*
**Research orientation:** No preference.
**Methodological interests:** Empirical studies, quantitative analysis, benchmark evaluation.
**Exclusions:** *(Leave empty)*
```

## Bounded interpretation

- Use the exact product tagline `Evidence-backed supervisor discovery for postgraduate research.`
- Use `postgraduate` as the active product and presentation umbrella term while preserving the
  exact degree context of retrieved evidence.
- Version the active Research Planning prompt so its product-level language uses `postgraduate`;
  preserve earlier prompt versions for trace reproducibility.
- Add an interface-only `Use demo research profile` control that fills the supplied values and
  still requires the reviewer to start the graph normally. Turning it off clears unchanged demo
  values while retaining reviewer edits.
- Add an interface-only `Light mode` control (off means dark); theme choice must not enter
  LangGraph state.
- Keep provider routing, evidence verification, Research Fit, Candidate approval, persistence,
  and all live/offline boundaries unchanged.
