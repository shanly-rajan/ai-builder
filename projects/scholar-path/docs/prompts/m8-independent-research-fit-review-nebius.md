# Milestone M8 Prompt: Independent Research Fit Review Using Nebius

Implement ScholarPath Milestone M8: independent Research Fit review using
Nebius.

Replace the fixture implementation of `review_fit_assessments`.

Create:

- `IndependentReviewModelPort`
- `NebiusReviewModelAdapter`
- `IndependentReviewAgent`
- `IndependentReviewResult` schema
- Deterministic assessment reconciliation function

The Independent Review Agent receives:

- `CandidateProfile`
- `VerifiedSupervisor`
- `EvidenceClaims`
- initial `ResearchFitAssessment`

It must return:

- decision: accept or revise
- recommended score
- unsupported claim IDs
- overlooked evidence IDs
- confidence
- concise critique

The reviewer must not:

- Search the web.
- Add evidence.
- Infer availability.
- Estimate admission probability.
- Change Candidate preferences.
- Directly modify the shortlist.

Reconciliation policy:

1. If accepted, preserve the original assessment.
2. If revise and all referenced evidence IDs are valid, use the reviewed score
   and explanation.
3. Remove unsupported claims.
4. If the disagreement exceeds a configurable threshold, lower confidence and
   mark the assessment as requiring Candidate attention.
5. If Nebius fails, preserve the original assessment, record review unavailable,
   and reduce confidence rather than crashing the graph.

Add tests for:

1. Accepted assessment.
2. Valid score revision.
3. Reviewer referencing nonexistent evidence.
4. Unsupported claims being removed.
5. Large disagreement lowering confidence.
6. Reviewer attempting to infer availability.
7. Nebius timeout.
8. Nebius malformed structured response.
9. Fake review model in default tests.
10. Optional live Nebius smoke test behind explicit opt-in.
11. Existing shortlist order updated deterministically after valid revisions.

Store model names and provider endpoints in configuration, not business logic.
