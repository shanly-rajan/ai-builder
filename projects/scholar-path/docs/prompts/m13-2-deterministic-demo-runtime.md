# Milestone M13.2 Prompt: Deterministic Streamlit demonstration runtime

Implement one bounded runtime-composition repair so the complete Streamlit journey can be
demonstrated deterministically without provider credentials or network calls.

The normal application currently composes provider-backed adapters and durable local SQLite.
Keep that behavior as the default `live` runtime profile. Add a separate, explicit
`deterministic_demo` profile for fixed synthetic demonstrations; do not silently fall back from
live providers to demonstration data.

Implement only this repair:

- Add a typed `RuntimeProfile` with exactly `live` and `deterministic_demo`, loaded from
  `SCHOLARPATH_RUNTIME_PROFILE` with `live` as the default.
- Keep `live` composition provider-backed and unchanged. The profile name does not make the
  trusted-local application production-ready.
- Compose `deterministic_demo` from fixed synthetic planning, discovery, content extraction,
  evidence, Research Fit, independent-review, and memory adapters. It must make no external
  provider call and require no provider credential.
- Use an in-memory checkpointer for `deterministic_demo` and force tracing off in that
  composition, even if tracing is enabled elsewhere in the environment.
- Reject `deterministic_demo` whenever `SCHOLARPATH_ENVIRONMENT=production`; never expose a
  production path that can present synthetic results as live results.
- Render a persistent, non-dismissible Streamlit warning in `deterministic_demo` on every stage
  and rerun. It must identify the results as fixed synthetic demonstration data, not live
  Supervisor research.
- Resolve the profile when the cached Streamlit application service is constructed. Document
  that switching profiles requires fully stopping and restarting the Streamlit server; a browser
  refresh or rerun is insufficient, and in-memory demonstration threads do not survive restart.
- Preserve the same LangGraph topology and deterministic domain policies in both profiles. Do
  not weaken Supervisor identity, evidence grounding, verification requirements, the
  five-Supervisor minimum, the one alternate-source retry, availability semantics, Research Fit,
  independent review, Candidate approval, or lifecycle transitions.
- Do not add a runtime toggle to the Candidate form, infer a profile from missing credentials,
  persist synthetic mode in production state, or allow demonstration adapters to call live
  services.

Add fixed offline tests for settings defaults and validation, production rejection, deterministic
composition without credentials or network, forced tracing disablement, in-memory checkpoint
behavior, the persistent warning, default-live regression, and unchanged verification and
approval contracts. Update `.env.example`, README, architecture, the five-minute demonstration,
the build journal, and repository contracts. Run focused tests and every repository quality gate
separately. Do not call live providers, inspect secrets, or use real Candidate or Supervisor data.
