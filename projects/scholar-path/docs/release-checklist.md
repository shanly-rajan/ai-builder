# ScholarPath `v0.1.0` Release Checklist

**Release date target:** 2026-08-30
**Release type:** trusted local-use, submission-ready initial release

Do not create the tag until every required item below is checked and the exact results are
recorded in [`build-journal.md`](build-journal.md). The optional live canary is informative;
it is not a substitute for the deterministic release gate.

## 1. Scope and safety

- [ ] The M13 diff contains reliability, tests, release documentation, and dependency/CI
  hardening only; Pinecone, Fireworks, LlamaIndex, outreach drafting, and unrelated features
  are absent.
- [ ] Canonical Candidate and Supervisor terminology passes its contract test.
- [ ] No `.env`, checkpoint database, coverage file, virtual environment, API key, or other
  local secret is tracked.
- [ ] Discovery failure injection defaults to `off` and cannot be enabled in production.
- [ ] The release notes state that authenticated Candidate-to-thread authorization is deferred
  and that `v0.1.0` is for trusted local use.

## 2. Version and documentation consistency

- [ ] `pyproject.toml` and `scholarpath.__version__` both report `0.1.0`.
- [ ] The graph trace version, evaluation baseline identifier, README, architecture review,
  evaluation baseline, saved prompt, diagrams, and build journal all identify the M13 release
  consistently.
- [ ] README links resolve to the M13 architecture, LangGraph topology, reliability review,
  five-minute demonstration, evaluation plan/baseline, terminology, and this checklist.
- [ ] The README contains the canonical one-liner, project overview, agent framework, technology
  decisions, dataset/source boundaries, test strategy, evaluation summary, limitations,
  roadmap, sample output, and exact local commands.
- [ ] No unresolved result placeholder remains in the release commit.

## 3. Reproducible installation

Create a clean Python 3.12 virtual environment, then run:

```bash
python -m pip install --upgrade "pip==26.1.2" "setuptools==84.0.0"
python -m pip install --constraint requirements.lock --no-build-isolation -e ".[dev]" \
  --config-settings editable_mode=strict
python -m pip check
python -c "import scholarpath; print(scholarpath.__version__)"
```

- [ ] Installation uses the committed exact-version `requirements.lock` constraints snapshot.
- [ ] `pip check` reports no broken requirements.
- [ ] Import succeeds without provider credentials and prints `0.1.0`.
- [ ] The lock snapshot was regenerated and reviewed after the final dependency change.
- [ ] The release notes accurately say constraints are exact-version reproducibility, not
  hash-locked supply-chain verification.

## 4. Deterministic quality gate

Run from `projects/scholar-path`:

```bash
ruff format --check .
ruff check .
mypy src tests scripts
pytest -m "not live"
python scripts/run_evals.py
git diff --check
```

- [ ] Ruff formatting passes.
- [ ] Ruff lint passes.
- [ ] Strict mypy passes across `src`, `tests`, and `scripts`.
- [ ] The complete non-live pytest suite passes with at least 90% branch coverage.
- [ ] Non-live tests retain the socket blocker and make no external request.
- [ ] The M13 fake-provider journey passes through reject, preference capture, refined search,
  approval, shortlist persistence, and final briefing.
- [ ] The local LangSmith-compatible baseline passes every applicable deterministic metric.
- [ ] Exact commands, test counts, deselected live-test count, coverage, and evaluation outcome
  are copied into `docs/build-journal.md` and `docs/evaluation-baseline.md`.

## 5. Reliability and human-control invariants

- [ ] External-service timeout settings and finite retry limits have positive and negative unit
  tests.
- [ ] Search queries, provider results, Prospective Supervisors, evidence retries, Candidate
  review iterations, and proposed recommendations all have explicit maximums.
- [ ] More valid discovery results than the retained cohort cap do not create a false
  duplicate-heavy route; truncation remains stable and deterministic.
- [ ] A later provider failure preserves earlier useful discovery and evidence work.
- [ ] Retry exhaustion ends in a typed recoverable or terminal state without a recursion error.
- [ ] SQLite state can be closed, reopened, inspected, and resumed on the same thread.
- [ ] Resume does not duplicate planning, search, learning, shortlist persistence, or briefing.
- [ ] Paused, rejected, and `request_more` states contain no Shortlisted Supervisor and execute
  no shortlist-save or briefing node.
- [ ] Only a validated approval containing IDs from the current proposal can persist a
  shortlist.
- [ ] No outreach implementation exists in the release source.

## 6. Privacy and isolation

- [ ] LangSmith metadata contains only the documented scalar allowlist.
- [ ] LangSmith graph and evaluation clients hide inputs and outputs and use finite request
  timeout/retry settings.
- [ ] UI and CLI failure paths do not print raw provider exceptions, credentials, full pages, or
  Candidate research statements.
- [ ] Mem0 reads and writes use the exact Candidate user ID and never persist Supervisor facts,
  source URLs, Research Fit Scores, or graph position.
- [ ] Separate LangGraph thread IDs do not share state; separate Streamlit sessions do not share
  Candidate data.
- [ ] The release documentation does not imply that a thread ID is an authorization credential.

## 7. Demonstration and optional canary

Run the optional one-profile canary only with all four provider credentials and the three
non-secret public target values configured:

```bash
SCHOLARPATH_RUN_LIVE_TESTS=true \
SCHOLARPATH_RUN_LIVE_CANARY=true \
LANGSMITH_TRACING=false \
pytest -o addopts='' -q -rs -m live \
  tests/integration/test_m13_live_canary.py
```

- [ ] The offline five-minute demonstration in [`five-minute-demo.md`](five-minute-demo.md)
  visibly shows the injected You.com failure, Tavily fallback, evidence, Research Fit,
  rejection, preference learning, refined search, approval, and final briefing.
- [ ] `tests/integration/test_m13_live_canary.py` is marked `live`, skipped by default, requires
  `SCHOLARPATH_RUN_LIVE_TESTS=true`, `SCHOLARPATH_RUN_LIVE_CANARY=true`, all needed keys, and
  the three non-secret public target settings.
- [ ] The one-profile live canary stays at or below nine logical provider calls and creates a
  Shortlisted Supervisor only after its explicit approval decision.
- [ ] The nine-call ceiling is two OpenAI planning attempts, one You.com search, one Tavily
  fallback search, one Tavily extraction, one OpenAI evidence call, two OpenAI Research Fit
  attempts, and one Nebius review.
- [ ] If the optional live canary or LangSmith trace was run, its date, environment, bounded
  call counts, outcome, and sanitized trace link are recorded separately from the offline
  baseline. If it was not run, that is stated explicitly.

## 8. Repository and CI

- [ ] GitHub Actions installs with the same pinned build tools and `requirements.lock`
  constraints used locally.
- [ ] CI runs Ruff formatting, Ruff lint, strict mypy for `src tests scripts`, non-live pytest,
  coverage, and `pip check` on Python 3.12.
- [ ] The workflow has read-only repository permission, a finite job timeout, and concurrency
  cancellation.
- [ ] `git status --short` contains only the intended M13 files before commit.
- [ ] The final commit passes CI on the `scholar-path` branch.

## 9. Tag decision

- [ ] A reviewer has accepted the reliability review and known limitations.
- [ ] The release commit hash and final CI run are recorded.
- [ ] The working tree is clean after the release commit.

Suggested annotated tag, after all required checks pass:

```bash
git tag -a v0.1.0 -m "ScholarPath v0.1.0"
git push origin v0.1.0
```

If a defect is found after publishing the tag, do not silently move it. Fix forward with a new
patch release and record the affected control and disposition in the build journal.
