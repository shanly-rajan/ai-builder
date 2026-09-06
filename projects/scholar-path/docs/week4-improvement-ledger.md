# Week 4 measured-improvement ledger

**2026-09-06, step 3am. Four repair records, with two different evidence strengths:**
three focused regression comparisons and one frozen, reviewed 30-case comparison.
This consolidates existing evidence; it makes no new application change.

Only **3ag** demonstrates a change on the reviewed golden dataset, confirmed by
the [LangSmith before/after comparison](week4-reviewed-langsmith-after.md).
The first three repairs already existed in that baseline. They are supporting
evidence, **not three additional golden-dataset gains**. Evidence for 3–4 separate
improvements on that frozen benchmark remains incomplete. The focused Week 4
report and recording are still required; see the [scorecard](week4-submission-readiness.md).

## Measured results and denominators

Metric: tests or cases meeting their expected behavior, divided by the size of
that row's fixed cohort. A negative-control pass means unsafe evidence was rejected,
not that a claim was accepted. Percentage-point deltas are rounded to two decimals.

| Repair | Before passed | After passed | Additional passes | Rate delta | Evidence scope |
| --- | --- | --- | --- | --- | --- |
| 3g — formatting-only excerpt context | 0/5 | 5/5 | +5 | +100.00 pp | Five positive reproductions; journal-recorded red/green and current recheck |
| 3k — section labels and academic roles | 17/30 | 30/30 | +13 | +43.33 pp | 19 agent + 11 domain tests, including negative controls; recorded red/green and current recheck |
| 3t — named academic specialisation | 42/56 | 56/56 | +14 | +25.00 pp | 56 domain cases; recorded red, original green within larger suite, standalone current recheck |
| 3ag — heading-bound research | 29/30 | 30/30 | +1 | +3.33 pp | Same frozen reviewed cases, saved local reports and LangSmith experiments |

**Do not sum these denominators or gains.** These are different, potentially
overlapping cohorts. They do not measure live Supervisor relevance or establish
four independent production success-rate improvements.

## Failure, hypothesis and exact lever

The first three hypotheses below reconstruct the intent of the recorded repairs;
they are **retrospective**, not preregistered numerical predictions.

| Repair | Failure cluster and intended effect | Exact implementation change and guardrails |
| --- | --- | --- |
| 3g | Formatting-equivalent affiliation excerpts lost their profile context. Expect fewer false rejections without accepting different wording or another person's text. | In `src/agents/evidence_verification.py`, map normalized case/whitespace matches back to original source offsets, inspect all equivalent occurrences, and require directly supported drafts before attaching context. Preserve exact excerpt, URL and retrieval time. |
| 3k | Section labels and academic roles were mistaken for people. Expect the known owner context to survive these labels while actual other people remain barriers. | Add exactly `Academic Background`, `Research Overview`, and `Research Publications` to the section allowlist; in `src/domain/models.py`, exclude whole-word `of/in` after `Prof/Professor` from titled-person matching. Names such as Ines/Ofelia and the Dr branch remain checked. |
| 3t | Explicitly named academic specialisation was not recognized as a research relation. Expect supported affirmative forms to ground without accepting generic, negated or unrelated text. | Extend the research-context subject helper in `src/domain/models.py` for the bounded specialisation form. Retain grounded identity, same-source links, eligible official profile, exact provenance and negative controls. No general natural-language interpretation added. |
| 3ag | An owner role sentence was mistaken for a different person heading, rejecting the following research claim. Expect the one failing golden case to pass, with other outcomes unchanged. | In `src/agents/evidence_verification.py`, make recognized same-owner role prose transparent to the backwards heading scan. Other-person headings, ambiguous repeats and unsupported excerpts still block grounding. See the [repair](week4-heading-grounding-repair.md). |

None of these repairs lowers the verification gate, changes Candidate approval,
rewrites source facts, or infers availability. The broader MVP policy is separate.

## Evidence provenance

| Repair | Historical record | Committed implementation and test scope |
| --- | --- | --- |
| 3g | [Journal: step 3g](build-journal.md#week-4-step-3g--consistent-profile-excerpt-grounding-2026-09-06): five failed before edits, the same five passed after. | `af115b6`; [profile-context tests](../tests/unit/agents/test_official_profile_evidence_context.py), selector `normalized_affiliation_excerpt`. The full 123-test module is not this comparison's denominator. |
| 3k | [Journal: step 3k](build-journal.md#week-4-step-3k--profile-subject-binding-repair-2026-09-06): 14/19 agent and 3/11 domain passed before edits; combined 30 passed after. | `af115b6`; [agent tests](../tests/unit/agents/test_profile_subject_binding_regressions.py) and [domain tests](../tests/unit/domain/test_academic_role_grounding.py). The larger 204-test check is not this denominator. |
| 3t | [Journal: step 3t](build-journal.md#week-4-step-3t--named-academic-specialisation-grounding-2026-09-06): 14 failed, 42 passed before edits; all 56 included in the 425-pass post-repair run. | `2fbfbeb`; [domain tests](../tests/unit/domain/test_named_specialisation_grounding.py). The additional agent tests and 425-test aggregate are not this denominator. |
| 3ag | [Saved local before](evaluation/week4-reviewed-baseline-2026-09-06.json), [local after](evaluation/week4-heading-grounding-after-2026-09-06.json), and [uploaded comparison](week4-reviewed-langsmith-after.md). | `4672168`; reviewed version `week4-30case-reviewed-v1`. Only `draft-evidence-heading-bound-research` / `expected_behavior` changed from fail to pass. |

The first three red results are **journal-recorded observations**, not failures
rerun today. Their selected test files and shared synthetic fixture factory are
unchanged since the listed commits; 3t's imported domain helpers are also unchanged.
The commits batch several steps: `af115b6` contains 3g–3p and `2fbfbeb` contains
3q–3u. There are **no isolated committed pre-repair snapshots** for those three
repairs. Current tests confirm continued passing, not independent re-execution
of each historical red revision. No private replay artifact was accessed for this ledger.

## Effort, latency and findings that did not improve

- The first three cohorts run locally with synthetic inputs and no live provider
  calls. No comparable historical application-port, token or monetary-cost delta
  was recorded for them. Their pytest duration is not production latency.
- For 3ag, every recorded case's fake application-port count is unchanged. The
  request-more workload remains **76/40**, with **zero calls saved**. Local fake
  graph p95 changed **0.067619 s → 0.072602 s**; hosted fake graph p95 changed
  **0.131363 s → 0.142125 s**. Both meet the 5-second fake-target bar; neither pair
  demonstrates a speed improvement. Keep local and hosted timing cohorts separate.
- The approved **40/80** policy distinguishes first review from interaction effort;
  it does not optimize the graph or erase the original 40-call failure. Nine
  interactions are paused within budget so far, not completed successes.
- Steps **3o** and **3s** expanded test denominators during repair (39 → 50 and
  36 → 60 respectively). Their larger green totals are not fixed-cohort rate gains
  and are excluded from the four-row comparison above.
- Diagnostics, measurement, policy clarification and the after-experiment upload
  are not additional behavior improvements. The [live-canary history](week4-live-canary.md)
  still contains a current-affiliation failure; a single isolated Nebius pass
  does not establish a repeatable live end-to-end result. Live quality/cost remain
  unmeasured by these regression cohorts.

## Reproduce the current focused checks

From `projects/scholar-path`, without credentials or network:

```bash
env SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false \
venv/bin/pytest -o addopts='' -q --tb=line --show-capture=no \
tests/unit/agents/test_official_profile_evidence_context.py -k normalized_affiliation_excerpt

env SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false \
venv/bin/pytest -o addopts='' -q --tb=line --show-capture=no \
tests/unit/agents/test_profile_subject_binding_regressions.py \
tests/unit/domain/test_academic_role_grounding.py

env SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false \
venv/bin/pytest -o addopts='' -q --tb=line --show-capture=no \
tests/unit/domain/test_named_specialisation_grounding.py
```

Observed on 2026-09-06 at checkpoint `dfd31a7`: **5 passed, 118 deselected in
0.13s**; **30 passed in 0.25s**; **56 passed in 0.10s**, all exit 0.
These are current checks, not newly measured historical before results.
The [after-experiment contracts](../tests/contract/test_week4_langsmith_after.py)
check the saved frozen comparison without uploading or calling a model.

## 60-second demonstration and next step

Open the four-row table. Explain the difference between a focused reproduction
and the reviewed benchmark. Run the five-case command, then open the linked
LangSmith comparison and show the one repaired case. Finish with **30/30 correctness,
76/40 effort still failing**, and the explicit live-evidence limits.

Next assemble the focused Week 4 report and recording around this evidence,
including the comparability gap rather than claiming every rubric item complete.
Do not add features or manufacture new failures just to reach an improvement count.
The mentor's unidentified window-related failure still needs its failing command
and runner log; passing local tests do not establish a Windows fix.
