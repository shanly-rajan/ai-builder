# Week 4 step 3ag: one measured grounding repair

**The unchanged reviewed cohort now passes 30/30 correctness checks locally,
up from 29/30.** The separate fake graph invocation budget still fails at **76/40**.
This is one measured deterministic repair, not a live-quality or release claim.

## Reproduced failure and narrow change

The approved `draft-evidence-heading-bound-research` case supplies a real profile
heading, an owner role sentence, and research text that does not repeat the name:

```text
# Dr Amara Ndlovu
Dr Amara Ndlovu is Professor in [department] at [institution].
## Research interests
Research interests: enterprise architecture and responsible AI governance.
```

The example above abbreviates the synthetic affiliation for readability; the
frozen fixture itself was not edited. The old heading scan treated the entire
Dr-prefixed affiliation sentence as a person's name. Comparing that sentence with
the owner name failed, so the research claim was marked `profile_subject_mismatch`.
Publication evidence separately allowed aggregate verification, hiding the missing
research claim if only overall verification status was checked.

The only production change is in
[`evidence_verification.py`](../src/agents/evidence_verification.py): a recognized
same-owner `is [a/an] [academic modifier] Professor in/of/at ...` prose sentence is
transparent to the existing backwards heading scan. It does not become a heading.

```text
Profile heading -> same-owner role prose -> research excerpt
      |               preserves context          |
      +------------------------------------------+
                     identity evidence link
```

This remains a bounded rule, not general natural-language name extraction:

- An intervening different-person heading still wins, even if owner role prose
  follows it. Other-person prose and longer-name collisions remain blocked.
- Explicit Markdown headings, multiple sentences, compound subject clauses, and
  further person titles are not ignored by the new rule.
- Every equivalent excerpt occurrence is still checked. Text repeated under
  different people remains ambiguous.
- Grounded identity, eligible official source, singular person route, on-page
  excerpt, and the model's directly-supported flag remain mandatory.
- The exact excerpt, source URL, retrieval timestamp, and identity evidence link
  are retained. Availability, strict verification policy, scoring, and routing
  did not change.

## Comparable observations

| Item | Before | After |
| --- | --- | --- |
| Correctness | 29/30 (96.67%) | 30/30 (100%) |
| Heading case `expected_behavior` | Fail | Pass |
| Other case/metric outcomes | Baseline | Unchanged |
| Max fake graph port calls / budget | 76/40, exceeded | 76/40, exceeded |
| Live provider calls in this step | None | None |

The increase is **one case / 3.33 percentage points** on this synthetic cohort.
It is not evidence of a 100% success rate on arbitrary live searches.

- Before: [saved local baseline](evaluation/week4-reviewed-baseline-2026-09-06.json),
  `scholarpath-week4-reviewed-local-20260906T153428Z-e585120b`.
- Before, independently reproduced this step: `29/30`, CLI exit `1`,
  `scholarpath-week4-reviewed-local-20260906T161710Z-91a821b9`.
- After: [separate saved report](evaluation/week4-heading-grounding-after-2026-09-06.json),
  `scholarpath-week4-reviewed-local-20260906T162018Z-0cd79546`.
- Date: **2026-09-06 UTC**; graph version: **`m13`**; fake providers only.
- Dataset: `scholarpath-week4-30case-reviewed-v1`.
- Reviewed SHA-256: `732ad206d79f30e2f9a3c0efd89c07daf4680216754fa21ce8e4d8f7bda911d5`.
- Source draft SHA-256: `f705973c08abec07d88977873900a40af9e5835d3f02a6b010d751c5f820594e`.
- Production source at the after-run: checkpoint `4a414b6` plus this uncommitted
  grounding diff; existing additive step 3af upload/report changes were preserved.
  SHA-256 of `src/agents/evidence_verification.py`:
  `1a5ed5f2672fe4dadbcf164f40cebe20e00311802f9447396d9f0aaf7af877e2`.

Fixture recipes, expected labels, source fixtures, target functions, and evaluator
definitions are unchanged. Historical artifacts still report their original
29/30 results. The [uploaded before experiment](week4-reviewed-langsmith-baseline.md)
is historical evidence, **not** a trace of this after-run. No after-experiment has
been uploaded.

## Verification and 60-second demonstration

From `projects/scholar-path`:

```bash
SCHOLARPATH_LOG_LEVEL=WARNING LANGSMITH_TRACING=false venv/bin/python scripts/run_reviewed_evals.py --check
venv/bin/pytest -o addopts='' -q tests/unit/agents/test_heading_bound_research.py tests/unit/evaluation/test_draft_evidence.py
venv/bin/ruff format --check .
venv/bin/ruff check .
venv/bin/mypy src tests scripts
venv/bin/pytest -q --tb=short --show-capture=no
```

For the short demonstration, open the before/after table, run the first command,
and point out **30/30** alongside the still-visible **76/40** budget failure.
Show the regression test's exact excerpt and source-link assertions. Explain that
CLI exit `0` means correctness passed; runtime is independently reported, not waived.

The focused new tests protect provenance, strict verification, deterministic replay,
person boundaries, compound prose, source eligibility, and missing support. Harness
tests also preserve historical failure reporting rather than deleting exit-1 checks.
Exact full-suite results are recorded in the [build journal](build-journal.md).

Final result: **2,939 passed, 9 live tests deselected, 109 subtests passed in
50.32s; 92.53% coverage**. Ruff formatting/lint and mypy also pass.

## Remaining work

Next, inspect the **request-more budget's multi-round scope** and establish an
appropriate bounded improvement before changing behavior or its bar. The 76 calls
are fake application-port invocations, not billed requests. Cost, live relevance,
and live repeatability remain unmeasured. A comparable LangSmith after-experiment
and remaining Week 4 improvements/reporting are separate follow-ups.

Unknown role prose forms, internal abbreviations, and more complex page structures
may remain conservatively ungrounded; this repair does not promise a universal
person-context parser.
