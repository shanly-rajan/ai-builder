# Milestone M13.5 Prompt: Privacy-safe graph execution logging

The attached provider-backed LangSmith trace stops after the second
`supervisor_evidence_sufficient` node. Confirm whether that run reached Nebius, then add simple
application logging for every ScholarPath graph node, node input, node output, and state
transition.

Implement only this bounded observability repair:

1. Explain from the canonical route that Nebius is not invoked unless the graph reaches
   `evaluate_research_fit`, then `review_fit_assessments`. A real Nebius call must be distinguishable
   from an injected fake through adapter-level provider events.
2. Use Python standard logging and the existing `SCHOLARPATH_LOG_LEVEL`. Add no logging vendor,
   provider call, graph node, graph edge, retry, or model invocation.
3. Instrument all canonical LangGraph nodes with a shared wrapper that logs a node-input event
   before invocation and a node-output event after a successful return.
4. Log every direct and conditional graph transition, including START and END. Preserve the exact
   router return value and do not use logging to influence routing.
5. Treat a Candidate-review interrupt explicitly: log a safe interruption event, re-raise the
   LangGraph interrupt unchanged, and log the resumed node output only when it returns.
6. Inputs and outputs must be privacy-safe projections, never raw state dumps. Include channel
   presence, updated channel names, collection counts, enum outcomes, bounded retry values,
   discovery round, fallback use, error codes, and recoverability where useful.
7. Never log Candidate or thread identifiers, research statements, topics, preferences, feedback
   reasons, search queries or returned text, Supervisor names, institutions, URLs, page content,
   evidence claims or excerpts, Research Fit rationales, review critiques, shortlist briefing,
   prompts, credentials, secret values, checkpoint tokens, raw exception messages, or tracebacks.
8. At the actual `NebiusReviewModelAdapter` boundary, log only safe provider-call start,
   completion, and failure-category events. A successful completion may include the structured
   decision, confidence, and counts of unsupported or overlooked references. It must not include
   critique text, evidence identifiers, Candidate content, or credentials. Fakes must not be
   labelled as Nebius.
9. Logging must be observational only: do not mutate graph state, persisted checkpoints,
   execution order, lifecycle state, evidence, Research Fit, review reconciliation, or Candidate
   decisions. Logging failure must not create a new workflow route.
10. Keep the five-Verified-Supervisor minimum, one alternate-source retry, availability semantics,
    prohibition on admission probability, and explicit Candidate approval before shortlist
    persistence or outreach drafting unchanged.

Add fixed offline tests for safe state and update projection, sentinel redaction, stable structured
serialization, every canonical node wrapper, direct and conditional transitions, interrupt and
resume behavior, unchanged graph results, Nebius adapter start/success/failure events, absence of
Nebius labels from fake review paths, log-level configuration, terminology, documentation, and
repository contracts.

Update the active README, architecture, reliability review, saved prompt, and build journal. Run
formatting, linting, strict type checking, focused regressions, the complete non-live suite, and
the offline evaluation baseline. Do not call live providers or inspect secrets. Commit this
milestone separately and stop.
