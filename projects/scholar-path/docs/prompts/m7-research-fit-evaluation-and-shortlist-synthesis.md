# Milestone M7 prompt: Research Fit Evaluation and preliminary Supervisor shortlist synthesis

Implement ScholarPath Milestone M7: Research Fit Evaluation and preliminary
Supervisor shortlist synthesis.

Replace the fixture implementations of:

- `evaluate_research_fit`
- `synthesize_supervisor_shortlist`

Create:

- `ResearchFitModelPort`
- `OpenAIResearchFitAdapter`
- `ResearchFitEvaluationAgent`
- `ShortlistSynthesisAgent`
- Configurable `ResearchFitRubric`

Use the following 100-point rubric:

- Research-topic alignment: 40
- Methodological or disciplinary alignment: 20
- Applied versus theoretical orientation alignment: 15
- Recent research activity alignment: 15
- Candidate practical constraints such as region and study mode: 10

Supervisor availability must remain a separate evidence status and must not be
converted into an admission likelihood or hidden inside the Research Fit Score.

Each scoring component must reference supporting `EvidenceClaim` IDs.
If a component lacks evidence, the response must say so and lower confidence.
The model may not award points based on unstated assumptions.

The Shortlist Synthesis Agent must:

- Rank only Verified Supervisors.
- Use overall score as the primary ordering.
- Use evidence confidence as the first deterministic tie-breaker.
- Use normalized Supervisor name as the final stable tie-breaker.
- Produce at most five proposed Shortlisted Supervisors.
- Explain strengths, concerns, availability status, and evidence confidence.
- Keep the result as proposed until Candidate approval.

Add tests for:

1. Scores constrained to 0 through 100.
2. Component scores summing correctly.
3. Every scored component citing evidence IDs.
4. Unsupported claims being rejected.
5. `availability_status=not_stated` remaining unchanged.
6. No admission probability in any output.
7. Deterministic tie-breaking.
8. Unverified Supervisors excluded.
9. Five-result maximum.
10. Strong-fit, weak-fit, and superficial-keyword fixtures.
11. Fake model used by default.
12. Optional live OpenAI test separately marked.

Do not add Nebius or Candidate approval yet.
