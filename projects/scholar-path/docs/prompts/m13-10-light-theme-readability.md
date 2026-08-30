# M13.10 bounded repair prompt: light-theme readability

## Prompt used

> In light mode, readability should not be compromised like attached

## Bounded interpretation

- Restore readable light-theme foreground, background, border, focus, and semantic-alert pairs.
- Cover the Streamlit form, outcome, diagnostic, dropdown, and popover surfaces visible in the
  supplied screenshot.
- Keep the existing dark theme unchanged and keep theme preference in Streamlit Session State.
- Use deterministic WCAG contrast contracts and stable selectors for the pinned Streamlit version.
- Do not change graph state, provider routing, evidence policy, or Candidate approval controls.
