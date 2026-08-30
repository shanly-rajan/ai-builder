# Milestone M13.3 Prompt: Academic UI and research-degree scope

Implement one bounded Streamlit presentation repair so ScholarPath's active product branding
supports Supervisor discovery for Master's and doctoral research degrees and completed runs do
not overwhelm the current decision with expanded history and diagnostics.

Implement only this repair:

- Render the exact hero title `🎓 ScholarPath` and exact subtitle
  `Evidence-backed Supervisor discovery for Master's and doctoral research.`
- Rename the first visible stage to the exact label `1. Your Research Degree Profile`.
- Use the exact form guidance `Describe your Master's or doctoral research direction and practical
  preferences that should guide Supervisor discovery.` while preserving the existing typed
  research-statement, topic, region, study-mode, orientation, method, and exclusion inputs.
- Use the exact canonical definition `Candidate: a person pursuing a research degree, such as a
  Master's degree or doctorate`. Keep **Supervisor**, **Prospective Supervisor**, **Verified Supervisor**,
  **Shortlisted Supervisor**, **Rejected Supervisor**, and **Research Fit Score** unambiguous.
- Render every Prospective Supervisor outcome card in a collapsed-by-default expander labelled
  with that Supervisor's name and institution.
- Render every Verified, Candidate-review, and Shortlisted Supervisor outcome card in a
  collapsed-by-default expander labelled with that Supervisor's name and institution, plus
  `Research Fit: N/100` when the score is present. Expanding a card must retain all current
  evidence, confidence, availability, concern, review, source-link, and action context.
- Keep canonical progress expanded while work is active, but collapse it by default after the
  run reaches a completed, stopped, review, or shortlist outcome.
- Wrap the complete existing privacy-safe panels in collapsed-by-default outer expanders with
  the exact labels `Discovery diagnostics`, `Alternate-source diagnostics`, and
  `Evidence-verification diagnostics`. Do not remove, duplicate, relabel, or expose content from
  their existing privacy-safe projections.
- Preserve the current graph topology, provider composition, typed state, checkpoints, routing,
  identity rules, evidence provenance and grounding, verification requirements, five-Supervisor
  minimum, one alternate-source retry, availability semantics, Research Fit calculation,
  independent review, Candidate approval gate, lifecycle transitions, and deterministic-demo
  safety boundary unchanged.
- Do not add a degree-type field, infer degree eligibility or Supervisor availability, calculate
  admission probability, auto-expand a Supervisor result, or treat viewing an outcome as
  approval.
- Keep historical saved prompts and build-journal entries unchanged; update only active product
  documentation and add this M13.3 prompt record.

Acceptance criteria:

1. Intake renders `🎓 ScholarPath`, the exact Master's/doctoral subtitle, the exact research-degree
   stage label, and Master's/doctoral form guidance.
2. Prospective, Verified, review, and Shortlisted cards are collapsed initially and expose their
   complete pre-existing details when expanded; applicable Verified variants include the exact
   `Research Fit: N/100` label fragment.
3. Canonical progress is open only while active and collapsed for completed outcomes.
4. All three diagnostic groups are collapsed initially under their exact outer labels, with the
   existing aggregate-only contents and privacy exclusions unchanged.
5. Candidate actions, evidence sufficiency, availability, Research Fit, independent review,
   shortlist promotion, runtime profiles, and checkpoint behavior are unchanged.
6. Fixed offline Streamlit, terminology, privacy, routing, and lifecycle regression tests pass;
   no live provider, secret, real Candidate data, or production data is used.

Update README, canonical terminology, architecture, the five-minute demonstration, repository
contracts, and the build journal. Run focused tests and every repository quality gate separately.
