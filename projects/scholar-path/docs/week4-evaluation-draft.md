# Week 4: thirty-case evaluation draft and human review

This is the **original pre-review draft snapshot**. It supplements pytest and
preserves the original eleven-case catalog and all historical experiment records.
The [separate reviewed manifest and local baseline](week4-reviewed-baseline.md)
record subsequent approval and measurements without rewriting this snapshot.

**Review update — 6 September 2026:** the project owner approved all 30 expected
behaviors: five individually and 25 through explicit batch approval. This does not
claim individual technical-field inspection or live quality. See the
[human review ledger](week4-label-review.md) for exact responses, IDs, and scopes.
The generated inventory/CLI below remain the original pre-review snapshot with
`pending` metadata; no labels, digest, or observed failures were rewritten.

## What this step resolves

Week 4 triage priority 3 calls for 30–50 labeled happy, edge, known-failure, and
adversarial cases. This draft supplies 30 executable synthetic cases:
**15 happy, 9 edge, 4 known-failure, and 2 adversarial**. Eleven are unchanged;
nineteen add thirteen evidence variations and six graph/action/failure variations.

Each row carries an ID, target, explicit expected outcome, category, source/version,
label rationale, and pending human-review status. Inputs and expected outcomes
remain separate. Five retained starting-outcome concepts were previously
acknowledged; those are not five additional cases or thirty reviewed labels.

All names, page content, and provider responses use the existing fictional
fixture cohort and reserved `.example` URLs. No private live snippets or personal
Candidate records were copied. Failure cases reproduce engineering patterns, not
the exact contents of private provider responses.

## Inspect and check locally

From `projects/scholar-path`, with the editable installation refreshed after
adding source modules:

```bash
venv/bin/python -m pip install --no-index --no-deps --no-build-isolation -e . --config-settings editable_mode=strict
venv/bin/python scripts/review_eval_draft.py
venv/bin/python scripts/review_eval_draft.py --case draft-evidence-heading-bound-research
venv/bin/python scripts/review_eval_draft.py --format json
SCHOLARPATH_LOG_LEVEL=WARNING venv/bin/python scripts/review_eval_draft.py --check
```

Preview commands do not execute targets. JSON includes all proposed labels and
provenance. `--check` uses fake ports and explicitly disables tracing, even when
live/tracing opt-in environment variables are set. It has no live, judge, upload,
approval, or file-write switch. No credentials are required. The existing
`run_evals.py` and `create_eval_dataset.py` defaults still use the original eleven
cases; they do **not** upload this draft.

## Observed offline result — 6 September 2026

**29/30 cases passed.** The command correctly exits **1**, not 0.

| Check | Passed / applicable |
| --- | --- |
| Schema validity | 30 / 30 |
| Expected behavior | 29 / 30 |
| Canonical terminology | 30 / 30 |
| Evidence ID validity | 14 / 14 |
| Source URL presence | 29 / 29 |
| Score range and component totals | 14 / 14 |
| No unsupported availability claim | 29 / 29 |
| No admission probability | 30 / 30 |
| Correct fallback route | 1 / 1 |
| Duplicate Supervisor rate | 12 / 12 |
| Human approval enforcement | 12 / 12 |

Denominators reflect applicability, not missing tests. For example, source URLs
do not apply to the planning-only case. These are synthetic policy checks, not
measured relevance, provider accuracy, latency, tokens, cost, or live repeatability.

The check also reports fake-target runtime measurements separately. The new
two-round `request_more` case makes **76 application-port invocations**, exceeding
the existing provisional **40-call graph budget**. That budget was not raised;
this correctness-check command does not enforce it or claim performance success.
Fake invocations are not billable provider calls. The runtime budget needs explicit
review for multi-round cases before a performance pass can be claimed.

The `expected_behavior` metric checks only fields supported by its typed labels.
Germany's propagation into the next planning input and an undated publication's
unchanged `activity_year=None` are additionally asserted by unit tests, not by that
row metric. Do not interpret every prose rationale as an independently scored metric.

**Observed failure:** `draft-evidence-heading-bound-research` fails
`expected_behavior`. Its legitimate research statement sits under the correct
profile heading, but current subject binding rejects it as
`profile_subject_mismatch`. Separate publication evidence still permits overall
verification. The explicit research-claim label catches this false negative.

The scenario remains a happy-input case with a failing observed result; categories
describe inputs, not test success. Its label was not weakened and its source was
not rearranged to manufacture a pass. Production verification is unchanged.
Tests explicitly check that this gap is surfaced. Thus a green pytest suite and a
29/30 draft evaluation are consistent, but the evaluation gate is **not all green**.

Two initial draft labels were corrected against existing policy: explicitly
negative availability is `verified_with_concerns`, and missing grounded identity
leaves all three strict evidence gates missing. These are proposed policy-aligned
labels in this historical snapshot; their intended behaviors were subsequently
approved in review decisions 002 and 003.

## Original human review handoff

1. Inspect each row below; use `--case <scenario-id>` for its exact structured label.
2. Confirm or amend the intended behavior independently of the observed result.
   Pay particular attention to the heading-bound research case, source scope,
   negative availability, and rejection/approval subsets.
3. Supply explicit reviewed IDs, accepted labels or corrections, reviewer, and
   review date. Do not equate the five earlier outcome acknowledgments with full review.
4. Only after that review should a subsequent step freeze a new dataset version
   and content digest, authorize upload/baseline execution, then measure bounded
   changes against the same frozen cases. No new live canary is needed for label review.

The digest below identifies the current draft contents; it is **not** a certificate
of human review or a frozen experiment. Expected-behavior approvals and the new
local freeze are recorded separately. Remaining submission gaps include an uploaded
baseline with trace links, comparative improvements, and the report/recording.
This step does not declare Week 4 or the live workflow complete.

## Case inventory

The table below is the original pre-review snapshot, generated by
`render_review_table(build_evaluation_draft())`. Current scoped human decisions
are in the [review ledger](week4-label-review.md).
Full machine-readable labels are available through the JSON preview command.

### scholarpath-week4-30case-draft-v1

Version: week4-30case-draft-v1. Status: pending_human_review.
Content SHA-256: f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e

All detailed labels await human review. Five retained starting-outcome concepts were
previously acknowledged; that is not approval of this dataset. All inputs are synthetic.

| # | Scenario ID | Type | Origin | Proposed expected outcome |
| --- | --- | --- | --- | --- |
| 1 | strong-research-alignment | happy | retained_v1 | A directly supported applied enterprise-architecture profile should receive a strong, evidence-cited Research Fit assessment. |
| 2 | superficial-keyword-poor-fit | edge | retained_v1 | Shared generic enterprise wording must not override incompatible topics, methods, orientation, and explicit exclusions. |
| 3 | availability-not-stated | happy | retained_v1 | Complete identity, affiliation, and research evidence must verify without inventing research-degree supervision availability. |
| 4 | conflicting-institutional-affiliation | edge | retained_v1 | Two official sources assert different current affiliations and both must remain visible as a verification concern. |
| 5 | duplicate-supervisor-multiple-queries | edge | retained_v1 | One academic profile appears in two query result sets and must be retained once with both provenance records. |
| 6 | you-timeout-tavily-fallback | known_failure | retained_v1 | A primary timeout and its single retry should route to Tavily and preserve the bounded attempt history. |
| 7 | evidence-extraction-failure | known_failure | retained_v1 | One failed profile extraction must remain partially verified without fabricated evidence while the useful partial cohort continues. |
| 8 | independent-reviewer-disagreement | edge | retained_v1 | A large valid review revision must lower confidence, flag Candidate attention, and update ordering deterministically. |
| 9 | candidate-rejects-highly-theoretical | edge | retained_v1 | An explicit Supervisor-specific rejection must be recorded and route to a bounded refined proposal without persisting a shortlist. |
| 10 | approval-required-before-persistence | happy | retained_v1 | The graph must pause with a proposed set and persist no Shortlisted Supervisor until an explicit approval response is received. |
| 11 | planning-source-coverage | happy | retained_v1 | A source-complete plan must cover official profiles, departments, recent publications, and explicit research-degree supervision information. |
| 12 | draft-evidence-confirmed-accepting | happy | new_synthetic_fixture | A directly stated availability sentence permits confirmed_accepting without any admission likelihood or broader degree-scope inference. |
| 13 | draft-evidence-confirmed-not-accepting | happy | new_synthetic_fixture | Negative availability remains confirmed_not_accepting; it does not prevent identity, affiliation, and research verification, but is surfaced as a concern. |
| 14 | draft-evidence-markdown-identity | happy | new_synthetic_fixture | Markdown presentation around an exact profile name must preserve its directly supported identity and all required verification gates. |
| 15 | draft-evidence-honorific-identity | happy | new_synthetic_fixture | Canonical name matching may normalize an academic title without changing the person. |
| 16 | draft-evidence-line-wrapped-affiliation | happy | new_synthetic_fixture | Whitespace presentation must not discard an explicit name, institution, and department. |
| 17 | draft-evidence-publication-only | happy | new_synthetic_fixture | A directly supported publication satisfies the research gate even without a separate research-interest claim; no research interests are invented. |
| 18 | draft-evidence-heading-bound-research | happy | new_synthetic_fixture | A nearby profile heading may bind a self-description to its subject when existing bounded grounding checks pass; a name need not be repeated in every sentence. |
| 19 | draft-evidence-missing-identity | edge | new_synthetic_fixture | Other evidence cannot replace the mandatory identity claim. Without a grounded identity, affiliation and research claims are not directly supported either; retain a partial record with all three gates missing. |
| 20 | draft-evidence-missing-affiliation | edge | new_synthetic_fixture | An identified researcher with research evidence but no current affiliation remains partially verified under the strict standard. |
| 21 | draft-evidence-missing-research | edge | new_synthetic_fixture | Identity and affiliation alone must not satisfy strict research verification. |
| 22 | draft-evidence-publication-year-not-stated | edge | new_synthetic_fixture | A grounded undated publication can establish research activity but must not acquire an invented date or a claim of recency. |
| 23 | draft-evidence-availability-without-statement | adversarial | new_synthetic_fixture | An accepting claim lacking a direct source statement must leave availability not_stated, regardless of the model's asserted confidence. |
| 24 | draft-evidence-off-page-excerpt | adversarial | new_synthetic_fixture | Invented research quotations must not become directly supported evidence or satisfy the mandatory research gate. |
| 25 | draft-graph-approve-one | happy | new_synthetic_fixture | Persist exactly the one explicitly selected Supervisor and complete the briefing. |
| 26 | draft-graph-approve-subset | happy | new_synthetic_fixture | Persist the two selected Supervisors, not the entire proposed set. |
| 27 | draft-graph-request-more | happy | new_synthetic_fixture | Apply the Germany region revision to the next planning input, then pause for review without saving a shortlist. |
| 28 | draft-graph-reject-then-approve | happy | new_synthetic_fixture | Retain the rejection, exclude that Supervisor from the new proposal, and save only the two explicitly approved Supervisors. |
| 29 | draft-graph-review-timeout | known_failure | new_synthetic_fixture | A scripted Nebius invocation failure preserves the original score, lowers confidence, flags review unavailable, and still reaches Candidate review. |
| 30 | draft-graph-review-malformed | known_failure | new_synthetic_fixture | A scripted structured-output failure preserves the original score with reduced confidence and review unavailable; the graph must not crash. |
