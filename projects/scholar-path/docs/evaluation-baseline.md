# ScholarPath M12 Evaluation Baseline

## Baseline identity

| Field | Value |
|---|---|
| Baseline identifier | `scholarpath-m12-4-fake-baseline-2026-08-30` |
| Date | 2026-08-30 |
| Dataset | `scholarpath-m12-regression-v1` |
| Dataset size | 11 curated synthetic scenarios |
| Execution mode | Direct offline fake targets and deterministic evaluators |
| LangSmith SDK | Project dependency `langsmith>=0.11.2,<1`; current environment `0.11.2` |
| External network | Prohibited for this baseline |
| Live providers | Not run |
| LLM-as-judge evaluators | Not run |
| Result status | **Accepted: 11/11 scenarios passed** |

The baseline was executed by `scripts/run_evals.py` without constructing a LangSmith client.
It is a local ScholarPath baseline identifier, not a claim that an experiment has been
uploaded to the LangSmith service. Uploading the same synthetic examples and results remains
an explicit, credentialed operation through the supported LangSmith `Client.evaluate` API.

## Version record

| Version | Recorded value |
|---|---|
| Application | `scholarpath` |
| Graph version | `m12.4` |
| Dataset schema version | `m12-scenarios-v1` |
| Research Planning prompt version | `research-planning-v2` |
| Evidence Verification prompt version | `evidence-verification-v3` |
| Research Fit prompt version | `research-fit-evaluation-v1` |
| Independent Review prompt version | `independent-review-v3` |
| Evaluation judge prompt versions | Not run |
| Research Fit rubric version | `research-fit-rubric-v1` |
| Model provider | `fake` |
| Candidate review outcomes represented | `awaiting_review`, `approve`, `reject` |
| Fallback outcomes represented | `false`, `true` |

## Metric definitions and pending observations

Boolean metrics use `0` for failure and `1` for pass. They require `1.00` on every
applicable example. `duplicate_supervisor_rate` is a lower-is-better ratio and requires
`0.00` after deterministic deduplication. A non-applicable metric returns `score=None` and
is excluded from aggregates.

| Metric | Direction | Required baseline | Observed value |
|---|---|---:|---|
| `schema_validity` | Higher is better | `1.00` for every applicable example | `11/11`, mean `1.000` |
| `canonical_terminology` | Higher is better | `1.00` for every applicable example | `11/11`, mean `1.000` |
| `evidence_id_validity` | Higher is better | `1.00` for every applicable example | `8/8`, mean `1.000` |
| `source_url_presence` | Higher is better | `1.00` for every applicable example | `10/10`, mean `1.000` |
| `score_range_and_component_totals` | Higher is better | `1.00` for every applicable example | `8/8`, mean `1.000` |
| `no_unsupported_availability_claim` | Higher is better | `1.00` for every applicable example | `10/10`, mean `1.000` |
| `no_admission_probability` | Higher is better | `1.00` for every applicable example | `11/11`, mean `1.000` |
| `correct_fallback_route` | Higher is better | `1.00` for every applicable example | `1/1`, mean `1.000` |
| `duplicate_supervisor_rate` | Lower is better | `0.00` after deduplication | `6/6`, mean `0.000` |
| `human_approval_enforcement` | Higher is better | `1.00` for every applicable example | `6/6`, mean `1.000` |

Judge metrics use a `0` to `4` scale. Their initial advisory threshold is a mean of at least
`3.0` with no applicable result below `2`. They are intentionally absent from this local
fake baseline.

| Judge metric | Advisory threshold | Observed value |
|---|---:|---|
| `llm_research_fit_relevance` | Mean `>= 3.0`, floor `2` | Not run |
| `llm_explanation_usefulness` | Mean `>= 3.0`, floor `2` | Not run |
| `llm_evidence_grounded_rationale` | Mean `>= 3.0`, floor `2` | Not run |
| `llm_shortlist_usefulness` | Mean `>= 3.0`, floor `2` | Not run |

Judge results remain advisory until they are calibrated against human ratings. They cannot
override deterministic evidence, availability, arithmetic, routing, terminology, or
approval failures.

## Scenario result record

| Scenario | Expected behavior | Local result |
|---|---|---|
| Strong research alignment | High, evidence-cited Research Fit with explicit gaps | Passed: score `87` |
| Superficial keyword overlap | Low Research Fit; shared vocabulary alone earns no points | Passed: score `0` |
| Availability not stated | `not_stated`; no inference from research activity | Passed: Verified, `not_stated` |
| Conflicting institutional affiliation | Conflict and concern retained without silent resolution | Passed: `verified_with_concerns` |
| Duplicate Supervisor through multiple queries | One Supervisor with merged provenance | Passed: eight unique, one with two provenance records |
| You.com timeout requiring Tavily fallback | Bounded retry, fallback, and finite completion | Passed: two You.com timeouts, then Tavily |
| Evidence extraction failure | Partial record without fabricated verification | Passed: one partial record and seven Verified Supervisors |
| Independent reviewer disagreement | Valid reconciliation and reduced confidence when required | Passed: revised `87` to `60`, Candidate attention set |
| Candidate rejects highly theoretical research | Feedback recorded and no shortlist persistence | Passed: one rejection, zero shortlisted |
| Candidate approval required | Pause before save; only explicit approved IDs persist | Passed: five proposed, zero shortlisted, interrupted |
| Source-diverse search planning | Distinct queries cover all required source types | Passed: typed source-diverse plan |

## Intentional failure-path coverage

The dataset deliberately exercises negative and degraded paths. These are successful
regression scenarios only when ScholarPath produces the expected safe outcome:

- superficial keyword overlap must not be promoted into a strong Research Fit;
- absent availability evidence must remain `not_stated`;
- conflicting affiliation must remain visible rather than being silently chosen;
- duplicate discovery must merge provenance without duplicate recommendations;
- a You.com timeout must use the bounded retry and Tavily policy;
- evidence extraction exhaustion must preserve partial work without fabrication;
- large independent-review disagreement must lower confidence and require Candidate
  attention when policy requires it;
- Candidate rejection must not persist a Shortlisted Supervisor; and
- a paused proposal must not cross the approval boundary before an explicit Candidate
  action.

An expected recoverable stop, partial verification, fallback, rejection, or interrupt is not
itself a baseline failure. A failure occurs when the observed output violates the reference
expectation or an applicable evaluator threshold.

## Observed failures

No deterministic baseline failures were observed. The failure-path scenarios produced their
expected safe degraded states; those states are not counted as regressions. Future failures
must record only scenario ID, evaluator key, score, a privacy-safe category, and disposition.

## Tests and commands

| Check | Result |
|---|---|
| M12 evaluator, judge, scenario, trace, runner, contract, and live-gate tests | Passed within the complete non-live suite; live execution remained deselected |
| Fake end-to-end graph regressions | Passed in the 11-scenario baseline |
| Dataset synchronization tests with a mocked client | Passed |
| Ruff formatting | Passed: 206 Python files formatted |
| Ruff linting | Passed |
| mypy | Passed: 167 source files |
| Full non-live pytest suite | Passed: 1,312 tests, eight live tests deselected, 54 terminology subtests, 90.46% branch coverage |
| Local fake evaluation | Passed: `11/11` scenarios |

The root implementation run must record exact commands, counts, coverage, and durations in
`docs/build-journal.md`. This baseline file records evaluation outcomes rather than replacing
the milestone journal.

## Live and judge execution status

- LangSmith dataset upload: **not run**.
- Uploaded LangSmith experiment: **not run**.
- Live end-to-end target: **not run**.
- OpenAI judge calls: **not run**.
- Any other model-as-judge provider: **not run**.

These omissions are intentional. Live operations require the explicit gates documented in
[`evaluation-plan.md`](evaluation-plan.md), applicable credentials, configured regional
endpoint and workspace, and a separate result record. A later live experiment must use a
different experiment identifier and must not overwrite or relabel this fake local baseline.

The first uploaded comparison remains **Pending explicit opt-in**; it is not part of the
accepted offline baseline.

## Baseline acceptance decision

**Accepted for the local fake evaluation layer.** Every applicable deterministic metric met
its threshold across all eleven scenarios, and the complete formatting, lint, type, and
non-live pytest gates passed.
