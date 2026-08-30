# Milestone M13.6 Prompt: Editor diagnostics repair

The newly added `src/observability/graph_logging.py` is highlighted red in the editor. Diagnose
the actual editor errors and fix only those errors.

Implement this bounded repair:

1. Reproduce the diagnostics with the project's configured Python version, a
   Pyright/Pylance-compatible checker, and the editor's Pylint checker.
2. Preserve the existing recursive JSON type aliases, privacy-safe field allowlists, event
   schema, logging behavior, graph wrappers, provider lifecycle events, public exports, and
   keyword-only provider-event API.
3. Add explicit runtime type guards only where Pyright cannot narrow an `object` through
   string-set membership.
4. Resolve Pylint maintainability diagnostics with behavior-preserving control-flow extraction;
   retain only a narrowly justified function-level suppression where the public keyword-only event
   envelope deliberately exceeds Pylint's default argument count.
5. Do not add a repository dependency, provider call, graph node, edge, state channel, retry,
   route, trace field, or log field.
6. Keep Candidate and Supervisor content, identifiers, evidence, URLs, prompts, credentials, and
   raw exceptions outside logs.
7. Verify the repaired file with Pyright, Pylint, Ruff, mypy, fixed unit tests, and the complete
   non-live suite.

Save this prompt, update `docs/build-journal.md`, commit the repair separately, and stop.
