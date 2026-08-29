# ScholarPath M12.1 Live-result presentation repair

## Prompt used

Also fix the observed live Streamlit result where:

- a Prospective Supervisor was rendered as `Prof Margaret A Boden Prof Margaret`;
- the institution was rendered as `People : AI Research Group : University of Sussex`;
  and
- identical recoverable evidence-extraction warnings were rendered repeatedly.

Implement this as a bounded repair after M12. Preserve append-only graph error history and
all provider, retry, evidence, verification, Research Fit, review, and Candidate approval
behaviour.

Normalize repeated abbreviated academic titles deterministically. For colon-delimited title
breadcrumbs, retain the strongest institution fragment without weakening person, academic,
or institution plausibility checks. Aggregate only exact duplicate Candidate-facing errors
at the UI projection boundary, preserving code, message, recoverability, first-seen order,
and the total occurrence count.

Add focused unit, AppTest, and repository-contract regressions. Update current documentation,
the graph version, and the build journal. Run formatting, linting, strict type checking, and
the complete non-live pytest suite. Commit the repair separately.
