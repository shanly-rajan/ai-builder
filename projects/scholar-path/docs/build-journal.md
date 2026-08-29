# ScholarPath Build Journal

This append-only journal records the objective, implementation evidence, and remaining
debt for each independently committed milestone.

## Milestone 0001: Standing engineering contract

**Date:** 2026-08-28

### Milestone objective

Establish a project-scoped ScholarPath engineering contract, prompt archive, build
journal, and ignore boundary for incremental, test-gated delivery without committing
local environments, secrets, caches, private data, or generated artifacts.

### Prompt used

[`docs/prompts/0001-standing-engineering-contract.md`](prompts/0001-standing-engineering-contract.md)

### Files changed

- `projects/scholar-path/AGENTS.md`
- `projects/scholar-path/.gitignore`
- `projects/scholar-path/docs/prompts/0001-standing-engineering-contract.md`
- `projects/scholar-path/docs/build-journal.md`
- `projects/scholar-path/tests/__init__.py`
- `projects/scholar-path/tests/contract/__init__.py`
- `projects/scholar-path/tests/contract/test_engineering_contract.py`

### Tests added

- Contract test that checks the standing prompt contains the critical terminology,
  deterministic-processing, provenance, safety, approval, and audit guardrails.
- Contract test that checks the prompt archive and build journal exist.
- Contract test that checks every required build-journal section is present.
- Contract placement test that requires `AGENTS.md` inside ScholarPath and rejects a
  repository-root copy.
- Ignore-policy contract test covering local environments, secrets, Python caches,
  private data, generated artifacts, logs, and local databases.

### Test results

- `venv/bin/python -m unittest discover -s tests -p 'test_*.py' -v`:
  5 tests passed after the milestone amendment.
- `venv/bin/python -m compileall -q tests`: passed.
- Ruff format check: 3 files already formatted.
- Ruff lint check: all checks passed.
- `git diff --check`: passed.
- `git check-ignore -v --no-index ...`: project-local rules matched `venv/`,
  `.venv/`, `.env`, `.ruff_cache/`, `data/private/`, and `*.sqlite3` paths.
- `git ls-files projects/scholar-path/venv`: returned no tracked files.
- The first test-discovery attempt found zero tests. Package markers were added and
  the same discovery command then found and passed the contract tests.
- A dedicated type checker is not configured and no production code exists in this
  milestone; configuring one remains explicit debt rather than an implicit tool choice.

### Assumptions

- Because this is a monorepo, ScholarPath's contract, prompt history, journal, and
  ignore policy belong inside `projects/scholar-path/` so they do not govern sibling
  experiments.
- Python's standard-library `unittest` is sufficient for this documentation-only
  milestone; choosing and installing the application test toolchain is deferred.
- Prompt archival begins with the milestone that introduced the archival rule; earlier
  conversation prompts are already represented by the committed project README.
- "Not meant to be committed" means ignored and untracked, not deleted from the
  developer's machine. The existing virtual environment remains locally available.
- `.env.example`, curated sample data, dependency lock files, and source-controlled
  evaluation fixtures must remain committable.
- The contract relocation was committed as `130a9a4`; shared history is preserved
  rather than rewritten or force-pushed as part of this documentation amendment.

### Lessons learned

- Agent responsibilities and six external platform integrations are already distinct
  in the project context, so future milestones can test those boundaries independently.
- Governance requirements are more reliable when their critical invariants are
  executable contract tests rather than documentation alone.
- Directory placement is an architectural scope boundary for repository instructions.
- Ignore behavior should be verified through Git itself as well as by checking the
  documented patterns.

### Remaining debt

- Select and configure the ScholarPath Python environment, formatter, linter, type
  checker, and primary test runner in a dedicated future milestone.
- Define the schema, source-authority rules, scoring model, graph state, retry policy,
  and data-retention policy only when explicitly requested by later milestones.
- Revisit generated-artifact paths when concrete LangGraph, LangSmith, Mem0, and
  Streamlit persistence choices are introduced.

## Milestone M0: Repository foundation and engineering contract

**Date:** 2026-08-28

### Milestone objective

Create an installable Python src-layout foundation with safe typed settings, canonical
terminology, deterministic contract checks, local quality tooling, coverage policy,
and non-live continuous integration without implementing future platform capabilities.

### Prompt used

[`docs/prompts/m0-repository-foundation.md`](prompts/m0-repository-foundation.md)

### Files changed

- Added `.github/workflows/scholarpath-ci.yml` at repository root.
- Added `projects/scholar-path/.python-version`, `.env.example`, and `pyproject.toml`.
- Updated `projects/scholar-path/README.md`.
- Confirmed the existing project-local `AGENTS.md` and `.gitignore` already satisfy
  the M0 contract and preserved them without unrelated rewrites.
- Added the `src/scholarpath/` package, `config.py`, and the requested package
  boundaries.
- Added `docs/terminology.md`, `docs/architecture.md`, and the archived M0 prompt.
- Added and expanded unit, contract, integration, discovery, and fixture test assets.
- Updated this build journal.

### Tests added

- Package import without credentials.
- Non-secret settings defaults.
- Missing, blank, and valid provider configuration at the explicit provider boundary.
- Nested environment-based provider-key loading without eager validation.
- Secret masking in typed provider configuration.
- Deterministic authored-source and documentation terminology scanning.
- Detection of case, plural, hyphen, underscore, source, and documentation violations.
- Required M0 structure and minimal runtime dependency contracts.
- Subprocess-based pytest discovery verification.
- Installed distribution metadata integration check.

### Test results

- `venv/bin/python -m pip install -e ".[dev]"`: editable package and development
  dependencies installed successfully.
- `venv/bin/python -m pip check`: no broken requirements found.
- Installed package import reported version `0.1.0` without credentials.
- `venv/bin/ruff format --check .`: 28 files already formatted.
- `venv/bin/ruff check .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 20 source files.
- `venv/bin/pytest -m "not live"`: 28 tests passed without network access.
- Coverage: 100 percent statement and branch coverage, above the 90 percent gate.
- Python 3.12.13 syntax compilation of `src` and `tests`: passed.
- The subprocess discovery contract collected the unit and contract suites
  successfully.
- `git diff --check`: passed.

### Assumptions

- Python 3.12 is the supported floor; `.python-version` preserves the repository's
  current Python 3.14.6 local convention.
- Provider configuration remains generic in M0. No provider name, SDK, client, or
  network behavior is added.
- `docs/prompts/` is immutable audit input and is excluded from terminology scanning;
  authored documentation, the project README, and all Python source remain in scope.
- Empty future package boundaries contain only module documentation and no behavior.
- Existing governance files and tests remain part of the M0 foundation rather than
  being rewritten.

### Lessons learned

- Src-layout installation tests the packaging boundary instead of relying on an
  implicit source-tree Python path.
- Optional secrets can load safely when strict credential validation is deferred to a
  typed provider activation method.
- Prompt archives require an explicit policy exception because they preserve user text
  verbatim rather than expressing authored product terminology.

### Remaining debt

- No graph state, domain schemas, agent logic, provider protocols, UI, memory service,
  or runtime observability exists yet; each requires a later explicit milestone.
- Dependency locking and an expanded Python-version test matrix remain future release
  hardening decisions.
- Live-test opt-in and provider-specific credential gates must be implemented alongside
  the first real provider adapter.

## Milestone M1: Domain models and data contracts

**Date:** 2026-08-28

### Milestone objective

Define immutable, provenance-preserving Candidate, search, Supervisor, evidence,
Research Fit, review, and shortlist contracts plus deterministic Supervisor lifecycle
rules and a realistic offline fixture cohort. No orchestration or external integration
is introduced.

### Prompt used

[`docs/prompts/m1-domain-models-and-data-contracts.md`](prompts/m1-domain-models-and-data-contracts.md)

### Files changed

- Added `src/scholarpath/domain/enums.py`, `models.py`, and `lifecycle.py`.
- Updated `src/scholarpath/domain/__init__.py` with the supported public API.
- Added deterministic factories in `tests/fixtures/`.
- Added domain unit, fixture contract, and offline integration tests.
- Updated `README.md`, `docs/architecture.md`, `docs/terminology.md`, and the fixture
  guidance.
- Archived the M1 prompt and updated this build journal.

### Tests added

- Valid construction, serialization, and JSON round trips for every M1 model.
- Invalid URL, empty required field, timezone-awareness, unknown-field, strict score,
  and score-bound checks.
- Evidence ownership, uniqueness, direct-support, sufficiency, typed availability, and
  Research Fit reference checks.
- Valid and invalid lifecycle transitions, terminal states, request-more behavior, and
  Candidate approval enforcement.
- Adversarial copy-update, availability derivation, distinct conflict-source, and
  coercive input checks.
- Exact one-to-eight-to-six-to-five fixture cardinality, relationship, timestamp,
  reserved-domain, availability, and evidence-integrity contracts.
- Offline integration coverage from verified records through Candidate approval to a
  five-record shortlist JSON round trip.

### Test results

- `venv/bin/ruff format --check .`: passed.
- `venv/bin/ruff check .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found.
- `venv/bin/pytest -m "not live"`: 149 tests passed without network access.
- Coverage: 100 percent statement and branch coverage, above the 90 percent gate.
- Python 3.12 syntax compilation of `src` and `tests`: passed.
- `venv/bin/python -m pip check`: no broken requirements found.
- `git diff --check`: passed.
- The manual lifecycle smoke demo printed `prospective -> verified -> shortlisted`
  and retained five evidence claims, `not_stated` availability, and `approve` evidence.
- The first full test run passed all domain behavior and reported one governance
  failure because the archived prompt was not yet linked. Adding this journal entry
  resolved that expected audit-trail failure.
- A final adversarial review identified direct terminal-status construction and generic
  availability claims as bypasses. Persisted Candidate decisions and typed availability
  outcomes closed both paths before the final quality run.

### Assumptions

- Evidence records factual research interests or publications; Candidate-specific
  alignment belongs in `ResearchFitAssessment`.
- A publication can satisfy the research-profile portion of verification when it is
  directly supported and belongs to the same Supervisor.
- The canonical M1 lifecycle is prospective to verified, then shortlisted or rejected;
  terminal states cannot transition again.
- `not_stated` needs no availability claim and never blocks verification. Any explicit
  availability state requires direct availability evidence.
- Fixture identities, institutions, and sources are invented; fixed timestamps and
  reserved domains keep the suite deterministic and safe.

### Lessons learned

- Separating evidence sufficiency from Research Fit scoring prevents Candidate-specific
  judgment from being stored as if it were a source fact.
- Enforcing invariants in model construction as well as lifecycle helpers prevents
  callers from bypassing verification rules through direct deserialization.
- Revalidating reconstructed frozen models and model-copy updates prevents lifecycle
  invariants from being bypassed by an unchecked status replacement.
- Candidate approval is easiest to audit when shortlist records themselves require the
  `shortlisted` lifecycle status and retain the matching review decision.

### Remaining debt

- Define source-authority, freshness, re-verification, and conflicting-evidence policy.
- Define and test the Research Fit calculation and ranking policy; M1 only validates
  externally supplied scores and breakdowns.
- Define how partial Candidate preference revisions merge into persisted preferences.
- Add graph state and orchestration behavior only in an explicitly requested future
  milestone.

## Milestone M1 amendment: Flattened physical source package

**Date:** 2026-08-28

### Milestone objective

Remove the additional physical `scholarpath/` directory beneath `src/` while
preserving the public `scholarpath` import namespace, package installation, strict type
checking, offline tests, and all M1 domain behavior.

### Prompt used

[`docs/prompts/m1-src-package-flattening.md`](prompts/m1-src-package-flattening.md)

### Files changed

- Moved the application package root, configuration, domain modules, and reserved
  component boundaries directly into `src/`.
- Updated `pyproject.toml` with an explicit logical-to-physical package mapping and a
  `py.typed` marker, plus explicit Ruff first-party import classification for the
  logical `scholarpath` package and test package.
- Updated the editable installation command in `README.md` and ScholarPath CI to use
  setuptools strict editable mode.
- Updated repository structure contracts and architecture documentation.
- Archived the adjustment prompt and updated this build journal.

### Tests added

- Contract coverage for the flattened physical directories and files.
- Contract coverage for the explicit `scholarpath` package mapping and complete package
  list.
- Contract coverage for Ruff's first-party classification under the non-standard
  physical package mapping.
- Contract coverage that rejects recreation of `src/scholarpath/`.
- Existing import, distribution metadata, domain, lifecycle, fixture, and integration
  tests continue to validate the logical public namespace.

### Test results

- `venv/bin/python -m pip install -e . --config-settings editable_mode=strict`: passed.
- After strict-editable symlink resolution, runtime imports point `scholarpath` to
  `src/__init__.py` and `scholarpath.domain` to `src/domain/__init__.py`.
- `venv/bin/ruff format --check .`: passed.
- `venv/bin/ruff check --no-cache .`: passed. The flattened-package GitHub Actions run
  exposed five import-order errors that a stale local Ruff cache had masked; declaring
  `scholarpath` and `tests` as known first-party modules resolved the clean-environment
  failure.
- `venv/bin/mypy src tests`: passed with strict checking.
- `venv/bin/pytest -m "not live"`: 150 tests passed without network access.
- Coverage remained 100 percent for statements and branches.
- Python 3.12 syntax compilation, dependency checking, and `git diff --check`: passed.

### Assumptions

- `scholarpath` remains the stable public import namespace even though it is no longer
  repeated as a physical directory beneath `src/`.
- Explicit setuptools package mapping is preferable to changing imports to `src` or
  exposing component directories as unrelated top-level packages.
- Strict editable mode is part of the development contract because it exposes the
  mapped package topology to both Python and mypy.
- Generated strict-editable build links remain ignored and are not source artifacts.

### Lessons learned

- Distribution names, import namespaces, and physical source directories are separate
  architectural concerns and can be mapped deliberately.
- Runtime import success alone is insufficient; editable installation must also expose
  the mapping to static analysis.
- Cache-free validation is important after changing source topology because cached
  lint results can conceal a changed module-classification boundary.
- A `py.typed` marker makes ScholarPath's inline types visible when mypy analyzes the
  installed logical package.

### Remaining debt

- The explicit package list must be extended when a future milestone adds another
  top-level ScholarPath subpackage.
- A future packaging milestone may evaluate whether a conventional physical package
  directory becomes preferable as distribution complexity grows.

## Milestone M2: Deterministic LangGraph walking skeleton

**Date:** 2026-08-28

### Milestone objective

Connect the M1 data contracts through a complete, typed LangGraph walking skeleton
whose 15 nodes, conditional routes, retry behavior, Candidate review gate, and final
five-record shortlist run entirely from deterministic fixtures without a model,
provider, or external network call.

### Prompt used

[`docs/prompts/m2-deterministic-langgraph-walking-skeleton.md`](prompts/m2-deterministic-langgraph-walking-skeleton.md)

### Files changed

- Added LangGraph and the minimum LangChain Core dependency to `pyproject.toml`.
- Added the typed state, reducers, fixture bundle, 15-node workflow, and public graph
  API under `src/graph/`.
- Added `src/cli.py` for the offline five-Supervisor demonstration.
- Added `tests/conftest.py` to block socket access throughout the non-live suite.
- Added M2 unit, graph, contract, and CLI integration tests and updated existing
  dependency, terminology, and package-structure contracts.
- Updated `README.md` and `docs/architecture.md`, and added the graph-derived
  `docs/m2-walking-skeleton.mmd` artifact.
- Archived the M2 prompt and updated this build journal.

### Tests added

- Exact happy-path execution-log and 15-node topology contracts.
- Insufficient discovery and evidence route tests for fallback and alternate retrieval.
- Candidate approval, rejection with replacement, and `request_more` refinement tests.
- Discovery, evidence, and review retry-exhaustion tests, including maximum configured
  retry budgets and clean terminal state assertions.
- Reducer immutability, stable Supervisor merge, initial-state, raw-result conversion,
  configuration-boundary, invalid-review-scope, partial-approval, and determinism tests.
- Runtime Supervisor-type, canonical-terminology, aggregate-consistency, JSON
  round-trip, generated-Mermaid, direct-dependency, offline-network, and CLI contracts.

### Test results

- `venv/bin/pytest --no-cov tests/graph tests/unit/graph tests/contract/test_m2_graph_contract.py tests/integration/test_cli.py -q`:
  38 focused M2 tests passed.
- `venv/bin/python -m pip install -e ".[dev]" --config-settings editable_mode=strict`:
  the package and declared dependencies installed successfully.
- `venv/bin/python -m pip check`: no broken requirements found.
- `venv/bin/ruff format --check .`: 51 files already formatted.
- `venv/bin/ruff check --no-cache .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 40 source files.
- `venv/bin/pytest -m "not live"`: 191 tests passed with 98.71 percent statement and
  branch coverage, above the 90 percent gate. Socket access was blocked by the
  non-live autouse fixture.
- Python 3.12.13 syntax compilation of `src` and `tests`: passed.
- `venv/bin/python -m scholarpath.cli`: printed five ranked Shortlisted Supervisors
  and their fixture Research Fit Scores.
- Exact generated-Mermaid comparison, terminology scan, package metadata, test
  discovery, dependency-boundary, `git diff --check`, and deterministic repeat-run
  contracts passed.
- The first strict-install attempt correctly failed because the isolated build
  environment had no sandbox network access; repeating the same declared command with
  approved PyPI access succeeded.

### Assumptions

- M2 fixture orchestration owns synthetic runtime data under `src/graph/`; production
  code never imports factories from the test suite.
- Six Verified Supervisor assessments allow a rejected top-five record to be replaced
  while every successful terminal shortlist still contains exactly five records.
- `candidate_review_gate_stub` applies configured typed decisions synchronously; graph
  interruption and a Candidate-facing interface remain outside this milestone.
- List reducers belong only on append-only history channels. Canonical entity
  collections are snapshots, while rejected records merge by stable Supervisor ID.
- Each configurable retry budget is capped at five, and the LangGraph recursion guard
  is derived above the maximum valid configured route rather than acting as normal
  workflow termination.

### Lessons learned

- A walking skeleton becomes architecturally useful when it exercises the full state
  and routing seams even though its adapters still return deterministic fixtures.
- Retry telemetry should count retries actually taken, not a denied next attempt.
- Candidate approval and shortlist cardinality are separate invariants; both must be
  checked before declaring the workflow complete.
- Generated architecture diagrams are safer when an exact offline contract detects
  node, edge, order, or duplication drift.
- Blocking socket entry points makes the default no-network promise executable rather
  than relying only on dependency inspection.

### Remaining debt

- `request_more` changes the typed SearchPlan and preference history but replays the
  same synthetic cohort; provider-backed query refinement is deferred.
- Replace fixture nodes with typed agent and tool interfaces one boundary at a time.
- Define Research Fit calculation, source-authority, freshness, and conflict policies
  before replacing the supplied fixture assessments.
- Replace the configured review stub with LangGraph interruption and Candidate resume
  behavior only in a later milestone.
- Add LangSmith tracing and evaluation without placing personal data, credentials, or
  full page content in trace metadata.

## Milestone M2 repair: Editor diagnostics

**Date:** 2026-08-28

### Milestone objective

Remove false red editor diagnostics caused by the monorepo selecting macOS Python 3.9
instead of ScholarPath's Python 3.14 virtual environment, and resolve the remaining
real Pyright errors without changing runtime behavior.

### Prompt used

[`docs/prompts/m2-editor-diagnostics-repair.md`](prompts/m2-editor-diagnostics-repair.md)

### Files changed

- Added shared Pyright analysis configuration to `pyproject.toml`.
- Replaced ambiguous dynamic test keyword arguments with typed configuration factories
  and narrowed an optional state update before accessing it.
- Added an editor-environment contract test and documented the exact VS Code
  interpreter path in `README.md`.
- Created an ignored monorepo-local `.vscode/settings.json` so the active workspace
  selects `projects/scholar-path/venv/bin/python`; it remains intentionally untracked.
- Archived the repair prompt and updated this build journal.

### Tests added

- Contract coverage for the Python version, virtual environment, analysis scope, and
  type-checking mode used by Pyright-compatible editors.
- Existing invalid-configuration cases now use statically typed factories and retain
  the same behavioral coverage.

### Test results

- The VS Code Pylance log initially showed `/usr/bin/python3` and Python 3.9.6 for the
  `ai-builder` workspace; after the local workspace setting changed, it showed
  ScholarPath's `venv/bin/python` and Python 3.14.6.
- BasedPyright analysis with the wrong environment reproduced unresolved imports and
  unsupported-syntax diagnostics.
- BasedPyright with the committed project configuration: zero errors, warnings, or
  notes at error level across `src` and `tests`.
- `venv/bin/ruff format --check .`: 52 files already formatted.
- `venv/bin/ruff check --no-cache .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 40 source files.
- `venv/bin/pytest -m "not live"`: 192 tests passed with 98.71 percent coverage.
- Python 3.12.13 syntax compilation, dependency checking, ignored-workspace-setting
  verification, and `git diff --check`: passed.

### Assumptions

- The visible red markers originate from VS Code/Pylance in the currently open
  `ai-builder` workspace; its language-server log is direct evidence of the incorrect
  interpreter selection.
- The project continues to target Python 3.12 or newer while the local virtual
  environment uses the repository's Python 3.14.6 convention.
- Editor-specific workspace state remains local and ignored; portable analysis rules
  belong in `pyproject.toml`.

### Lessons learned

- A passing runtime and mypy gate cannot prevent an IDE from using a different Python
  executable in a multi-project workspace.
- PEP 695 syntax and strict editable package mappings make an incorrect pre-3.12
  interpreter immediately visible as cascading editor diagnostics.
- Test parameterization should remain statically unambiguous across both mypy and
  Pyright-family analyzers.

### Remaining debt

- Developers using another editor must select the project virtual environment or make
  that editor honor the shared Pyright configuration.
- The ignored root workspace setting is machine-local because the monorepo contains
  sibling projects with independent Python environments.

## Milestone M3: OpenAI Research Planning Agent and baseline LangSmith observability

**Date:** 2026-08-29

### Milestone objective

Replace only the fixture-backed `plan_supervisor_searches` implementation with a typed,
dependency-injected Research Planning Agent backed by OpenAI native structured output,
while adding optional privacy-safe LangSmith graph and planning-node traces. Preserve
all downstream fixture nodes and every existing deterministic route.

### Prompt used

[`docs/prompts/m3-openai-research-planning-and-langsmith-observability.md`](prompts/m3-openai-research-planning-and-langsmith-observability.md)

### Files changed

- Added the versioned planning prompt, provider-neutral planning contracts, Research
  Planning Agent, and OpenAI adapter under `src/agents/`.
- Added provider-specific OpenAI and LangSmith settings with deferred credential
  validation in `src/config.py` and documented their variables in `.env.example`.
- Extended the domain SearchPlan with typed query purposes and target source types,
  plus deterministic count, uniqueness, and source-coverage validation.
- Replaced the graph's planning fixture with injected model composition, added the
  planning-failure route to END, and retained fixtures for the other 14 nodes.
- Added scoped LangSmith tracing, safe environment and graph-version tags, allowlisted
  metadata, and hidden trace inputs and outputs under `src/observability/`.
- Updated the CLI for lazy OpenAI composition, clean missing-key guidance, and an
  injectable offline demonstration seam.
- Added `langchain-openai` and a direct LangSmith dependency while preserving the
  existing LangGraph and LangChain Core version line.
- Updated `README.md` and `docs/architecture.md`, saved the generated M3 graph at
  `docs/m3-research-planning-graph.mmd`, and archived this milestone prompt.
- Added the tests-only `FakePlanningModel`, planning/adapter/observability tests, graph
  failure tests, contract coverage, and the explicitly gated live smoke test.

### Tests added

- Complete CandidateProfile, remembered-preference, region, and exclusion mapping into
  an identity-free typed planning input.
- Valid structured response conversion and SearchPlan JSON round trips.
- Empty, duplicated, under-specified, and source-incomplete query-plan rejection.
- Exactly one retry for malformed Pydantic or LangChain structured-parser output.
- Immediate, sanitized graph termination for provider invocation failure and terminal
  malformed output, with no downstream discovery execution.
- Default graph-route coverage through an injected recording FakePlanningModel and an
  assertion that offline tests never instantiate OpenAI.
- OpenAI adapter contracts for native strict JSON-schema output, zero provider retries,
  sanitized exceptions, and no search-tool binding or prose JSON parsing.
- Optional LangSmith activation, disabled/no-client behavior, safe tags and metadata,
  sensitive-field exclusion, and input/output payload hiding.
- Exact provider environment-variable loading and deferred secret validation.
- A `pytest.mark.live` OpenAI smoke test requiring both an API key and the explicit
  `SCHOLARPATH_RUN_LIVE_TESTS` opt-in flag.
- Current generated-Mermaid, dependencies, prompt archive, terminology, and audit
  contracts while preserving all M2 routing scenarios.

### Test results

- `venv/bin/pip install -e ".[dev]" --config-settings editable_mode=strict`: installed
  the project and the current compatible `langchain-openai` dependency successfully
  after approved package-index access.
- `venv/bin/pip check`: no broken requirements found.
- `venv/bin/ruff format --check .`: all 67 files already formatted.
- `venv/bin/ruff check --no-cache .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 54 source files.
- `venv/bin/pytest -m "not live"`: 219 tests passed, one live test was deselected,
  and total statement/branch coverage was 95.70 percent, above the 90 percent gate.
- The explicitly selected live smoke test skipped cleanly without the opt-in flag and
  API key, making no provider request.
- Python 3.12.13 and 3.14.6 syntax compilation of `src` and `tests`: passed.
- Key-free package import, generated-Mermaid equality, terminology, test discovery,
  dependency boundaries, prompt audit linkage, and `git diff --check`: passed.
- A local injected-model smoke run traversed the happy path and produced five
  Shortlisted Supervisors without network access.

### Assumptions

- `gpt-5.4-mini` is the configurable planning default for the current supported
  LangChain OpenAI integration; a deployment may select another structured-output
  capable OpenAI model through `OPENAI_PLANNING_MODEL`.
- Candidate identity is unnecessary at the model boundary. The full research statement
  is necessary for planning, is sent to OpenAI, and is hidden from LangSmith trace
  inputs and outputs.
- Malformed structured output is retryable once; provider invocation failure is not
  retried because duplicate requests would amplify outage latency and cost.
- A planning failure must terminate before discovery so stale or absent SearchPlan data
  cannot drive later nodes.
- LangGraph's normal tracing captures the graph root and its nodes, so duplicate manual
  planning spans are unnecessary.
- The live CLI intentionally requires OpenAI configuration; offline tests demonstrate
  the same orchestration through the injected fake rather than a silent runtime
  fallback.

### Lessons learned

- Separating the OpenAI-compatible transport DTO from the stricter domain SearchPlan
  keeps provider schema limitations out of domain invariants.
- Provider-internal retries and application retries must not overlap; setting OpenAI
  retries to zero makes the single malformed-output retry observable and testable.
- Current native structured-output parsing can surface malformed shape as a plain
  `ValueError`, so the adapter must classify parser failures rather than treating every
  non-Pydantic exception as a provider outage.
- Metadata allowlisting prevents accidental identity or secret fields from entering
  traces; hiding both inputs and outputs also protects Candidate state carried through
  LangGraph payloads.
- Injecting a recording fake validates semantic input mapping and graph routing without
  coupling tests to LangChain message types or external network behavior.

### Remaining debt

- Add an alternate planning provider, rate limiting, circuit breaking, and explicit
  token/cost budgets before production-scale use.
- Define OpenAI data-governance, retention, regional-processing, and model-change review
  policies for Candidate research statements.
- Add LangSmith evaluation datasets, scoring, dashboards, sampling, retention, and
  operational alerts; M3 supplies tracing only.
- Replace the remaining fixture-backed discovery, verification, Research Fit, review,
  synthesis, and persistence nodes only through later explicit milestones.
- Replace the configured Candidate review stub with an interrupt/resume interaction in
  a later milestone.

## Milestone M3 repair: Editor environment and CLI configuration

**Date:** 2026-08-29

### Milestone objective

Remove the confirmed red ScholarPath editor diagnostics without changing M3 product
scope, create a private ignored `.env` with explicit OpenAI and optional LangSmith
secret slots, and document verified offline and explicitly opted-in live CLI paths.

### Prompt used

[`docs/prompts/m3-editor-environment-and-cli-repair.md`](prompts/m3-editor-environment-and-cli-repair.md)

### Files changed

- Changed optional secret field metadata in `src/config.py` to Pydantic's `Annotated`
  form so Pylint sees the runtime `SecretStr` type, and isolated its remaining
  `default_factory` inference limitation to one documented expression.
- Changed two observability assertions to use `RunnableConfig.get`, matching
  LangChain's optional-key TypedDict contract and clearing Pyright diagnostics.
- Changed the CLI to report the actual sanitized provider configuration error instead
  of always attributing a failure to OpenAI.
- Updated CLI integration coverage and `README.md` with monorepo Pylance setup, private
  environment-file handling, offline graph execution, live graph execution, and the
  explicitly gated OpenAI smoke-test command.
- Created a blank-secret `.env` with user-only permissions and enabled Pylance nearest
  configuration discovery in the monorepo's `.vscode/settings.json`. Both are local,
  ignored files and are intentionally absent from the commit.
- Archived the repair prompt and updated this build journal.

### Tests added

- Added CLI integration coverage proving that a LangSmith configuration failure is
  reported as LangSmith rather than incorrectly as an OpenAI failure.
- Updated existing observability assertions to satisfy the external `RunnableConfig`
  TypedDict while preserving their runtime checks.
- Re-ran all existing unit, graph, contract, integration, terminology, discovery, and
  guarded-live contracts; no network-backed test was enabled.

### Test results

- VS Code logs confirmed that Pylance used the correct Python 3.14.6 virtual
  environment but scanned the 131-file monorepo because it did not discover the nested
  ScholarPath Pyright configuration.
- The VS Code Pylint extension reproduced three Pydantic `FieldInfo` `no-member`
  diagnostics in `src/config.py`; after repair, Pylint reported no errors across
  `src/`, and the focused configuration module received 10.00/10.
- BasedPyright analyzed the 54 configured files with zero errors, warnings, or notes.
- `venv/bin/ruff format --check .`: all 68 files were formatted.
- `venv/bin/ruff check --no-cache .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 54 source files.
- `venv/bin/python -m pip check`: no broken requirements found.
- The first full test run passed 220 tests and exposed only the expected missing journal
  link for this newly archived prompt. After adding this entry, the final non-live run
  passed all 220 selected tests, deselected one live test, and achieved 95.96 percent
  statement and branch coverage.
- The injected `FakePlanningModel` CLI command completed without network access and
  printed five ranked Shortlisted Supervisors.
- The live test selection skipped cleanly with its API key and explicit opt-in removed;
  no OpenAI or LangSmith request was made.
- Git confirmed `.env` and the monorepo `.vscode/settings.json` are ignored; `.env` has
  mode `0600` and contains no secret value.

### Assumptions

- The reported red project state refers to the currently active VS Code analyzers;
  their logs supplied the exact Pylint errors and Pylance workspace behavior.
- The monorepo remains the active VS Code workspace, so local nearest-configuration
  discovery is preferable to a repository-root Pyright policy that could affect
  sibling projects.
- `.env` is resolved from the process working directory by pydantic-settings, so all
  documented commands begin in `projects/scholar-path`.
- The OpenAI key is required only for a live planning invocation. The LangSmith key is
  optional while `LANGSMITH_TRACING=false`.

### Lessons learned

- Selecting the right interpreter and discovering the nearest static-analysis
  configuration are independent requirements in a nested monorepo.
- Pydantic's assignment-style `Field` descriptors can create Pylint false positives
  even when mypy, Pyright, runtime validation, and tests agree; using `Annotated`
  retains metadata while exposing the intended optional secret type.
- Provider setup errors should preserve their sanitized provider identity so operators
  fix the correct secret or feature flag.
- A live pytest module that reads `os.getenv` directly needs `.env` exported into its
  process, while the application settings classes load `.env` themselves.

### Remaining debt

- Pylance's nearest-configuration feature is experimental; developers can instead open
  `projects/scholar-path` directly if a future editor release changes its behavior.
- Pylint remains an editor-side supplementary analyzer rather than a declared CI gate;
  Ruff, strict mypy, Pyright-compatible analysis, and pytest are the documented project
  gates.
- A built-in offline `--fixture-demo` CLI option could replace the current explicit
  test-fake injection command, but that would be a separate requested milestone.
- The live OpenAI and optional LangSmith paths still require the user to add personal
  credentials and explicitly opt in; this repair deliberately made no paid or external
  request.

## Milestone M4: You.com Supervisor discovery

**Date:** 2026-08-29

### Milestone objective

Replace only the fixture-backed `discover_prospective_supervisors` implementation with
a typed You.com Web Search boundary and deterministic Supervisor Discovery Agent while
preserving the existing graph topology, bounded fallback routes, downstream fixture
nodes, canonical terminology, and Candidate approval control.

### Prompt used

[`docs/prompts/m4-you-com-supervisor-discovery.md`](prompts/m4-you-com-supervisor-discovery.md)

### Files changed

- Added the provider-neutral `SearchResult` and paired
  `SupervisorDiscoveryProvenance` domain contracts and preserved provenance through
  the existing Supervisor lifecycle models.
- Added deferred You.com settings in `src/config.py` and documented `YDC_API_KEY`, the
  official endpoint, timeout, and result-count options in `.env.example`.
- Added `SupervisorSearchPort`, typed search failures, and the transport-only
  `YouSearchAdapter` under `src/tools/`, with `httpx` as the only new runtime
  dependency.
- Added `SupervisorDiscoveryAgent`, structured `SupervisorDiscoveryResult`,
  conservative person/institution extraction, canonical URL normalization, stable
  identifiers, deterministic deduplication, and provenance merging under
  `src/agents/`.
- Replaced the graph's primary discovery fixture with injected search execution while
  retaining every existing node and edge; production lazily constructs You.com and
  default tests inject `FakeSupervisorSearch`.
- Updated the CLI injection seam, graph-version trace tag, graph fixtures, state
  projection, exports, README, and architecture documentation.
- Saved the generated M4 graph in `docs/m4-you-com-discovery-graph.mmd` and archived
  this milestone prompt.
- Added domain, adapter, agent, graph, configuration, contract, and explicitly gated
  live-test coverage for M4.

### Tests added

- Official You.com POST request construction with a mocked HTTP transport, including
  exact query, API-key header, JSON count, endpoint, timeout, and secret-free URL.
- Stable web/news normalization, configured result capping, empty responses, optional
  publication timestamps, malformed-response handling, and SearchResult JSON round
  trips.
- Typed timeout, transport, non-success HTTP, rate-limit, provider, and response-schema
  errors without response-body or provider-exception leakage into graph state.
- Conservative academic-person and institution extraction, non-person exclusion,
  rejection of `Dr`-only clinical profiles without academic context, normalized
  identity and canonical-URL deduplication, stable identifiers, and exact multi-query
  provenance merging.
- Structural assertions that discovery produces neither Research Fit scores nor
  availability inference, even when an input snippet mentions doctoral availability.
- Graph integration proving every planned query is called once and in order, injected
  fakes prevent You.com construction, sanitized failures exhaust cleanly, and empty
  results retain the existing fallback route.
- Deferred-key configuration, bounded timeout/count settings, transport-only adapter,
  no-Tavily, generated-Mermaid, prompt, dependency, environment, and audit contracts.
- One `pytest.mark.live` You.com smoke test requiring both `YDC_API_KEY` and explicit
  `SCHOLARPATH_RUN_LIVE_TESTS=true` opt-in.

### Test results

- `venv/bin/python -m pip install -e . --no-build-isolation --config-settings
  editable_mode=strict`: passed and refreshed the strict editable package mapping for
  the new source modules. The initial build-isolated attempt could not resolve PyPI in
  the sandbox; no new download was needed because `httpx 0.28.1` was already installed.
- Focused adapter, discovery-agent, domain, graph, and configuration run: 57 tests
  passed without coverage or network access.
- The first complete non-live run passed 266 tests and exposed only the expected
  missing prompt-journal link plus the M0 dependency allowlist that needed the explicit
  M4 `httpx` dependency. Both governance contracts were then updated.
- `venv/bin/ruff format --check .`: all files formatted.
- `venv/bin/ruff check --no-cache .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 65 source files.
- `venv/bin/pytest -m "not live"`: 272 tests passed, two live tests were deselected,
  and statement/branch coverage was 93.96 percent, above the 90 percent gate.
- `venv/bin/python -m pip check`: no broken requirements found.
- Generated-Mermaid equality, terminology, offline network blocking, test discovery,
  key-free import, dependency boundaries, prompt audit linkage, and `git diff --check`
  passed.
- The offline CLI demonstration with `FakePlanningModel` and `FakeSupervisorSearch`
  traversed the unchanged happy path and printed five Shortlisted Supervisors.
- The explicitly selected You.com live smoke test skipped cleanly when its key and
  opt-in flag were removed; no live provider call was made during milestone validation.

### Assumptions

- The current official You.com Web Search contract is `POST
  https://ydc-index.io/v1/search` with `X-API-Key`, JSON `query` and `count`, and the
  documented `YDC_API_KEY` credential convention.
- M4 authorizes a search provider, not another model-backed agent. Conservative
  deterministic extraction therefore satisfies the discovery boundary without adding
  an unrequested model port, prompt, cost, or retry policy.
- You.com's `page_age` field represents the optional publication timestamp and maps to
  `SearchResult.publication_date`; missing values remain `None`.
- The configured result count is sent to You.com and also caps the combined normalized
  web/news collection so graph state has a deterministic upper bound.
- Invented fixture records and live discoveries use the same composite hash of
  normalized name, institution, and canonical profile URL; fixture URLs use stable
  `profile-NNN` paths only as synthetic source locations.
- The existing fallback node remains fixture-backed because Tavily is explicitly
  outside M4. A production You.com result will usually stop at fixture-backed evidence
  sufficiency until evidence retrieval is replaced in a later milestone.

### Lessons learned

- A transport adapter stays reusable and testable when it normalizes provider shape but
  knows nothing about academic people, Research Fit, or availability.
- Provenance must be stored as source/query pairs; parallel source and query lists could
  silently lose their association during deduplication.
- Search-provider result limits and the normalized application-state limit are distinct
  concerns because You.com applies `count` per response section.
- Replacing one walking-skeleton node can preserve all established route tests when
  the provider is injected at the composition root and fallback behavior remains
  behind the existing edges.
- Strict editable installs must be refreshed after adding a physical module to this
  flattened package mapping; otherwise Python resolves the old symlink manifest.

### Remaining debt

- Replace the fixture fallback with Tavily only in an explicit future milestone, with
  its own typed adapter, failure policy, and live-test gate.
- Replace fixture-backed evidence retrieval before expecting arbitrary live discoveries
  to reach Research Fit evaluation or the Candidate review gate.
- Improve multilingual name, institution, department, and publication-page extraction
  recall through an explicitly designed typed model boundary or richer deterministic
  parsers; current extraction intentionally prefers precision.
- Add rate limiting, bounded concurrency, caching, circuit breaking, provider metrics,
  and explicit HTTP-client lifecycle management before production-scale use.
- Revisit web-first combined result capping if publication/news coverage is starved by
  a full web section.

## Milestone M5: Resilient Supervisor discovery with Tavily fallback

**Date:** 2026-08-29

### Milestone objective

Make Supervisor discovery resilient by retaining You.com as the primary search
provider, adding the current official Tavily integration as a bounded fallback, and
routing deterministically from typed provider attempts, partial results, and explicit
quality thresholds. Preserve all useful Prospective Supervisors across later failures,
stop safely when providers are exhausted, and leave evidence extraction unchanged.

### Prompt used

[`docs/prompts/m5-resilient-supervisor-discovery.md`](prompts/m5-resilient-supervisor-discovery.md)

### Files changed

- Added the official `langchain-tavily==0.2.17` dependency to `pyproject.toml`; this is
  the newest release compatible with the existing LangChain Core/OpenAI range.
- Added deferred Tavily settings, timeout/result limits, and the default-off
  `SCHOLARPATH_DISCOVERY_FAILURE_MODE` in `src/config.py` and `.env.example`.
- Added provider/category-aware `SearchProviderError` contracts and preserved the M4
  typed search-error subclasses in `src/tools/supervisor_search.py`.
- Added the transport-only `TavilySearchAdapter` using the official
  `langchain_tavily.TavilySearch` import and an application-enforced async deadline.
- Added deterministic, default-off provider failure injection for local routing
  demonstrations.
- Added frozen `SearchAttempt`, validated `DiscoveryPolicy`, routing enums, and pure
  `route_after_supervisor_discovery` under `src/graph/discovery.py`.
- Extended typed graph state with append-only search attempts, discovery rounds, and
  fallback activation fields; the existing retry-count keys remain stable.
- Integrated one bounded You.com timeout retry, Tavily fallback, partial-success
  retention, sanitized terminal errors, and lazy Tavily construction into the existing
  fifteen-node graph. Evidence extraction remains fixture-backed.
- Extended the CLI injection seam to accept separate primary and fallback fakes, and
  updated the LangSmith graph tag to `graph-version:m5`.
- Updated fake search scripting, configuration tests, historical milestone contracts,
  README, architecture/NFR documentation, generated Mermaid, and this journal.
- Added a local blank `TAVILY_API_KEY` slot and non-secret Tavily defaults to the
  ignored `.env` without reading, printing, or changing existing secret values.

### Tests added

- Official Tavily tool construction, exact one-query invocation, normalized URL/title/
  description/date/query fields, configured result limits, empty results, cancellation,
  malformed payloads, and sanitized HTTP/provider/transport errors.
- Pure policy validation for one You.com retry, direct fallback, timeout behavior,
  minimum unique results, duplicate-heavy results, too few plausible profiles,
  non-retryable authentication, current-round isolation, partial-success continuation,
  and recoverable Tavily exhaustion.
- Graph scenarios for successful You.com without Tavily, timeout then retry, retry
  failure then Tavily, empty results, duplicate-heavy results, immediate authentication
  stop, a retained six-Supervisor partial cohort, both providers failing, exact retry
  budgets, and persisted attempt fields.
- Lazy-boundary coverage proving a healthy You.com route neither validates a Tavily key
  nor constructs its adapter, while a missing key becomes a typed authentication
  attempt only after fallback is selected.
- Failure-injection unit coverage for `off`, `you_timeout_once`,
  `you_retryable_error`, and `both_providers_retryable_error` modes.
- Repository contracts for the official non-community import, exact dependency,
  default-off demonstration mode, new state fields, unchanged fixture evidence node,
  archived prompt, generated graph, environment example, and guarded live test.
- One optional `pytest.mark.live` Tavily smoke test requiring both `TAVILY_API_KEY` and
  explicit `SCHOLARPATH_RUN_LIVE_TESTS=true` opt-in.

### Test results

- `venv/bin/python -m pip install -e . --no-build-isolation --config-settings
  editable_mode=strict`: passed after approved package-index access and refreshed the
  flattened strict-editable mapping for the new modules.
- `venv/bin/python -m pip check`: no broken requirements found.
- Focused routing, adapter, failure-injection, and M5 graph scenarios passed without
  network access.
- The first complete run exposed 13 historical contracts that still described the M4
  no-Tavily boundary; those tests were updated to preserve their original invariants
  while recognizing the newly authorized M5 dependency and route.
- A later complete run passed all behavior and quality checks and exposed only the
  expected missing journal link for the newly archived prompt; this entry closes that
  governance check.
- `venv/bin/ruff format --check .`: all files formatted.
- `venv/bin/ruff check --no-cache .`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 74 source files.
- `SCHOLARPATH_DISCOVERY_FAILURE_MODE=both_providers_retryable_error venv/bin/pytest
  -m "not live"`: 392 tests passed, three live tests were deselected, and combined
  statement/branch coverage was 94.89 percent, above the 90 percent gate. Explicit
  test settings remained deterministic despite the process-level demonstration mode.
- Generated-Mermaid equality, terminology, prompt audit linkage, default network
  blocking, key-free import, test discovery, and `git diff --check` passed.
- The deterministic failure demonstration routed an injected You.com provider error to
  the fake Tavily port, retained typed attempt history, and completed without network
  access.
- The explicitly selected Tavily smoke test skipped cleanly without both required
  opt-ins; no live provider request was made during milestone validation.

### Assumptions

- `langchain-tavily==0.2.17` is pinned because the newer 0.2.18 release constrains
  LangChain Core to a version incompatible with the project's current
  `langchain-openai` range. The pin is deliberate dependency governance, not a
  deprecated integration choice.
- The official Tavily tool does not expose a per-call timeout option in this compatible
  release, so ScholarPath invokes its public async boundary inside `asyncio.timeout`
  and cancels the call when the application deadline expires.
- A maximum Tavily fallback count is a call budget. If it exceeds the four-to-eight
  query-plan length, fallback cycles through queries deterministically while consuming
  that finite budget.
- Search result quality is evaluated from provider result count, plausible profile
  count, and unique Prospective Supervisor count. Research Fit and doctoral
  availability remain outside discovery.
- A missing Tavily credential is non-retryable authentication configuration and stops
  only if fallback is actually required; a successful primary path requires no Tavily
  credential.
- Partial success may continue after a fallback attempt when the current-round minimum
  and quality gates are retained. It does not bypass later verification, Research Fit,
  or Candidate approval gates.

### Lessons learned

- Provider resilience is easier to reason about when attempts are immutable audit data
  and routing is a pure function rather than mixed into network adapters.
- Attempt history must be scoped by discovery round; otherwise an old outage can
  incorrectly route a later Candidate-requested refinement.
- Lazy fallback construction matters operationally: backup-provider credentials should
  not become a new startup dependency for a healthy primary route.
- Partial search success should be appended before the next call. Treating a multi-query
  search as one transaction would discard useful records when only a later query fails.
- A fallback budget larger than the query count needs explicit cycling or an exhaustion
  marker; otherwise a graph can keep revisiting a fallback node without consuming
  budget.
- Compatibility between provider packages must be verified across their complete
  dependency ranges, not inferred from package names or latest-version ordering.

### Remaining debt

- Replace fixture-backed evidence retrieval before expecting arbitrary live discoveries
  to reach Research Fit evaluation or Candidate review.
- Add source authority, freshness, page retrieval, robots/terms governance, and
  conflicting-evidence policies in the evidence milestone.
- Add rate limiting, bounded concurrency, caching, circuit breakers, provider metrics,
  and explicit reusable client lifecycle management before production-scale use.
- Add an async search-port variant before a future async UI or service invokes Tavily;
  the current synchronous port intentionally owns its event loop through `asyncio.run`.
- Tune discovery thresholds and provider budgets from LangSmith evaluation datasets;
  current defaults are deterministic engineering baselines rather than empirical
  production values.
- Improve multilingual person/institution extraction and canonical cross-provider URL
  matching while preserving source/query provenance.
- Evaluate dependency locking or constraints so the compatible Tavily/Core/OpenAI set
  cannot drift during future installs.

## Milestone M6: Supervisor evidence extraction and verification

**Date:** 2026-08-29

### Milestone objective

Replace the three fixture-backed evidence nodes with a typed, page-grounded Supervisor
verification boundary. Retrieve known pages through Tavily Extract, classify
claims through native structured model output, preserve exact provenance and conflicts,
retry one alternate official source for every partial record, and stop recoverably
without fabricating missing evidence.

### Prompt used

[`docs/prompts/m6-supervisor-evidence-verification.md`](prompts/m6-supervisor-evidence-verification.md)

### Files changed

- Added provider-neutral content extraction contracts and the official
  `TavilyExtractionAdapter` under `src/tools/`.
- Added the versioned evidence prompt, `EvidenceVerificationModelPort`, structured
  output schemas, `EvidenceVerificationAgent`, and OpenAI adapter under `src/agents/`.
- Extended domain evidence contracts with exact asserted fields, supporting excerpts,
  conflict references, project evidence, partial verification status, and a separate
  `SupervisorVerificationRecord` that cannot masquerade as a Verified Supervisor.
- Added `VerificationPolicy`, pure sufficiency routing, alternate official-source
  selection, typed extraction attempts, graph state channels, and production
  composition under `src/graph/`.
- Updated deferred OpenAI/Tavily settings, CLI injection, M6 LangSmith metadata,
  exports, `.env.example`, README, architecture documentation, and generated Mermaid.
- Added fixed HTML/Markdown evidence pages, extraction/model fakes, unit, graph,
  contract, integration, and guarded live-test coverage.
- Archived the M6 milestone prompt and updated this journal.

### Tests added

- Tavily Extract construction, one-URL requests, nested deadlines, normalization,
  content caps, redirect provenance, typed failures, malformed responses, public-URL
  safety, and the pinned official tool's public async invocation contract.
- Structured OpenAI evidence output, strict JSON schema, provider retry disabling,
  sanitized failures, and metadata that excludes page content, Candidate data, and
  secrets.
- Fixed official-profile scenarios for complete evidence, missing affiliation, missing
  research, unstated and explicit availability, conflicting affiliation, exact excerpt
  grounding, asserted-field grounding, and stable evidence identifiers.
- Adversarial regressions for same-prose/different-fact ID collisions, wrong-person
  research and availability, inverted availability polarity, dangling conflict IDs,
  same-surname alternate results, and commercial or embedded-academic host spoofs.
- Pure policy and alternate-source selection tests for one retry, retry priority,
  minimum verified cohort, source selection, snippet exclusion, attempt validation,
  and exhaustion.
- Graph scenarios for complete verification, alternate extraction, partial retention,
  recoverable below-minimum termination, conflict preservation, provenance, and
  unchanged fixture Research Fit scores rebound to current evidence IDs.
- Domain and contract coverage for partial-record separation, conflict references,
  state reducers, official imports, prompt/environment/diagram audit artifacts, and
  network-free default tests.
- One `pytest.mark.live` Tavily Extract smoke test requiring both `TAVILY_API_KEY` and
  explicit `SCHOLARPATH_RUN_LIVE_TESTS=true` opt-in.

### Test results

- Focused M6 agent, domain, graph, routing, adapter, configuration, and contract runs
  passed without network access.
- Tavily adapter audit: 47 tests passed; the guarded live test skipped.
- Structured OpenAI/configuration audit: 50 tests passed.
- Evidence and graph behavior checks passed after tightening asserted-affiliation
  grounding and preserving different affiliations as concerns rather than silently
  overwriting discovery data.
- `venv/bin/ruff format .`: 113 Python files formatted; the final check changed no
  files.
- `venv/bin/ruff check --no-cache src tests`: all checks passed.
- `venv/bin/mypy src tests`: no issues found in 90 source files.
- `venv/bin/pytest --no-cov -q`: 574 tests passed, four live tests were deselected,
  and 41 terminology subtests passed without network access.
- `venv/bin/pytest -q`: the same 574 tests passed with 92.84 percent combined
  statement/branch coverage, above the 90 percent gate.
- Strict editable installation, Python compilation, and `venv/bin/python -m pip check`
  passed; no broken requirements were found.
- Generated M6 Mermaid equality, terminology, prompt-audit, default network blocking,
  key-free import, test discovery, and `git diff --check` passed.
- Explicit live-test selection skipped all four guarded provider tests without a
  network call.
- The 60-second fake-backed CLI demonstration traversed the M6 evidence path and
  printed five ranked Shortlisted Supervisors with scores unchanged from their
  fixtures.

### Assumptions

- Current affiliation evidence must directly state an institution and department.
  Different official values are retained and surfaced as concerns rather than silently
  overwriting discovery profile fields; source-authority adjudication is deferred.
- `TavilyExtract` from the already pinned official `langchain-tavily==0.2.17` package is
  the current compatible retrieval boundary; no community or private import is used.
- Tavily-returned canonical redirect URLs are the evidence source URLs because they
  identify the page whose content was actually returned.
- Initial known URLs are classified conservatively from their exact returned URL.
  Only HTTPS results on label-valid academic domains can be selected as alternate
  official sources; source weighting beyond this admission control is deferred.
- Search snippets may help select an alternate official URL but are never submitted as
  evidence page content or persisted as claims.
- A project claim is useful retained evidence but does not replace the explicit M6 rule
  requiring research-interest or publication evidence for verification.
- Five Verified Supervisors are the minimum continuation cohort. Every partial record
  still receives its one alternate-source opportunity before that cohort is evaluated.

### Lessons learned

- Partial verification needs its own outcome contract; adding a partial status directly
  to `VerifiedSupervisor` would weaken the lifecycle invariant and downstream trust.
- System-owned IDs, source URLs, timestamps, kinds, and excerpts keep provenance out of
  model control while still allowing the model to perform bounded extraction and
  classification.
- Typed model output is necessary but not sufficient: asserted names and affiliations
  must also be grounded against exact page excerpts before direct support is accepted.
- Page-level identity is not subject binding for every nearby fact. Each direct claim
  must explicitly name the expected Supervisor, and availability polarity is verified
  deterministically rather than trusted from the model.
- An evidence identifier must cover every semantic field that merge logic treats as
  identity; otherwise a hash collision can silently erase a conflicting fact.
- Affiliation conflict detection must compare department as well as institution and
  cross-reference both retained claims rather than choosing a winner silently.
- A stronger-page retry is deterministic when search only selects a known official URL
  and Tavily Extract, rather than the search snippet, supplies the evidence content.
- URL validation at the extraction boundary reduces credential leakage and server-side
  request risk before a provider receives the target.

### Remaining debt

- Replace fixture Research Fit scoring and independent review only in their requested
  milestones; M6 merely rebinds unchanged fixture assessments to verified evidence IDs.
- Define source-authority weighting, freshness windows, re-verification schedules,
  canonical redirects, and durable evidence storage before production use.
- Add bounded concurrency, caching, rate limiting, circuit breaking, provider metrics,
  and an async extraction port before a future async UI or service runtime.
- Evaluate multilingual extraction, institution aliases, department renames, and
  structured publication identifiers without weakening exact provenance.
- Add LangSmith evaluation datasets and quality metrics for evidence precision, recall,
  conflict detection, and unsupported-claim rate.

## Milestone M7: Research Fit evaluation and preliminary Supervisor shortlist synthesis

**Date:** 2026-08-29

### Milestone objective

Replace fixture Research Fit evaluation and proposal synthesis with an evidence-cited,
structured model boundary plus deterministic validation, arithmetic, confidence
handling, ranking, and a maximum-five proposal that remains outside the shortlisted
lifecycle state until Candidate approval.

### Prompt used

[`docs/prompts/m7-research-fit-evaluation-and-shortlist-synthesis.md`](prompts/m7-research-fit-evaluation-and-shortlist-synthesis.md)

### Files changed

- Added `ResearchFitRubric`, evidence-cited component assessments, strengthened
  cross-contract citation validation, typed research `activity_year`, deterministic
  aggregate confidence, a configurable recency window, and proposal-only domain models
  under `src/domain/`.
- Added `ResearchFitModelPort`, `ResearchFitEvaluationAgent`, the versioned fit prompt,
  `OpenAIResearchFitAdapter`, and deterministic `ShortlistSynthesisAgent` under
  `src/agents/`.
- Replaced the two fixture graph nodes, added fit dependency injection and lazy
  production composition, changed `proposed_shortlist` to a typed proposal, and added
  an injectable aware-UTC proposal clock plus privacy-safe, configured-rubric-version
  LangSmith metadata under `src/graph/` and `src/observability/`.
- Added deferred OpenAI Research Fit settings, `.env.example` variables, CLI injection,
  deterministic fakes, and migrated historical fit fixtures to the component contract.
- Updated README, terminology, current architecture, the M7 Mermaid diagram, prompt
  archive, tests, and this journal.

### Tests added

- Domain tests for the 100-point rubric, component bounds, deterministic totals, exact
  citation unions, suitable direct evidence, availability exclusion, proposal
  validation, typed activity-year grounding, configurable recency, aggregate confidence,
  and lifecycle preservation.
- Agent tests for privacy-minimized inputs, strong, weak, and superficial-keyword
  outcomes, evidence gaps, unknown citations, bounded malformed-output retry, score
  caps, weakest-evidence confidence bounding, stale or missing activity years, and
  prohibited admission or availability scoring prose.
- OpenAI adapter tests for native strict JSON-schema output, disabled SDK retries,
  structured validation, sanitized errors, and safe metadata.
- Synthesis tests for score/confidence/name tie-breaking, strict Verified-only input,
  maximum-five output, strengths, concerns, separate availability, stable lifecycle,
  and missing-assessment handling.
- Graph tests for fake-only evaluation, owned citations, deterministic arithmetic,
  proposal ordering, injected aware-UTC proposal timestamps, partial model failure
  retention, and prohibited admission outputs.
- Configuration, tracing, contract, CLI, and one separately marked optional live OpenAI
  smoke test guarded by a key and explicit opt-in, including configured rubric-version
  trace metadata and network-free default-test enforcement.

### Test results

- Focused domain, Research Fit, adapter, synthesis, graph, configuration, tracing,
  terminology, and documentation-contract suites passed without network access.
- `venv/bin/ruff format --check .`: all 125 files were already formatted.
- `venv/bin/ruff check .`: all lint checks passed.
- `venv/bin/mypy src tests`: no issues found in 101 source files.
- `venv/bin/pytest`: 655 non-live tests passed, five live tests were deselected, and
  combined statement/branch coverage was 92.06 percent, above the 90 percent gate.
- Strict editable reinstallation with local build isolation disabled and `--no-deps`
  succeeded without downloading dependencies; `venv/bin/python -m pip check` reported
  no broken requirements, and importing `scholarpath` reported version `0.1.0`.
- Compilation under both the current project interpreter and Python 3.12 completed
  successfully for `src` and `tests`.
- Explicit live-test selection collected all five guarded smoke tests and skipped all
  five without credentials or a network call.
- The fake-backed CLI completed the graph and printed five Supervisors with scores
  `87`, `82`, `75`, `72`, and `68` in deterministic rank order.
- Terminology, prompt and documentation contracts, generated-diagram checks, and
  `git diff --check` passed.

### Assumptions

- The model may assess semantic alignment but may cite only evidence already verified
  for the same Supervisor; it never creates evidence or authoritative provenance.
- The model output deliberately omits an overall score. Python owns arithmetic,
  component bounds, citation validation, weakest-evidence confidence capping,
  deterministic aggregate confidence, and ranking.
- Publication or project evidence may establish recent activity only through a typed
  `activity_year` grounded in its excerpt. The configurable M7 default freshness window
  is five years from retrieval.
- M7 has no typed region or study-mode evidence category. Current-affiliation prose is
  therefore insufficient for practical points; that component remains zero and records
  the evidence gap.
- Availability remains a separate field on each recommendation. It never changes a
  component score, admission likelihood is never calculated, and `not_stated` remains
  unchanged.
- The existing configured Candidate review stub is preserved only to keep the walking
  skeleton executable. M7 does not implement a real human approval interface.
- Proposal creation uses an injected clock that must return aware UTC. Production uses
  current UTC; deterministic tests use a fixed timestamp. The configured rubric version,
  not a hard-coded default, is attached to safe Research Fit trace metadata.

### Lessons learned

- Structured output constrains shape, but deterministic cross-contract validation is
  still required to reject invented IDs, indirect claims, unsuitable evidence types,
  and component scores above the configured weight.
- Omitting the overall score from model output makes the arithmetic ownership boundary
  unambiguous and keeps repeatable operations out of probabilistic execution.
- A proposal needs its own typed aggregate. Reusing `SupervisorShortlist` before review
  would silently bypass the lifecycle meaning of a Shortlisted Supervisor.
- Evidence confidence is an auditable deterministic tie-breaker only when component
  confidence cannot exceed the weakest cited claim and the assessment aggregate is
  independently reproducible from the configured rubric.
- Freshness must be a typed, excerpt-grounded fact plus a deterministic window; prose
  such as "recent" cannot safely authorize recent-activity points.
- Injecting the proposal clock prevents fixture timestamps or wall-clock calls from
  leaking into deterministic graph tests while retaining accurate production audit time.
- Trace metadata must use the rubric version actually configured for the graph so an
  experimental rubric cannot be mislabeled as the default.
- Historical Mermaid artifacts should be tested as milestone snapshots; the current
  graph receives a new artifact when node metadata or implementation changes.

### Remaining debt

- Add Nebius independent review only in its requested milestone; M7 performs no second
  model critique or score adjustment.
- Add explicit region and study-mode evidence categories or deterministic institution
  location data before awarding practical-constraint points in production.
- Define empirical rubric calibration, inter-rater agreement, score stability,
  multilingual evaluation, production freshness calibration and re-verification, and
  LangSmith evaluation datasets.
- Add durable assessment/proposal storage, concurrency, caching, cost controls, and a
  real Candidate review interface in separately scoped milestones.

## Milestone M8: independent Research Fit review using Nebius

**Date:** 2026-08-29

### Milestone objective

Replace the fixture `review_fit_assessments` node with an injected, strict structured
Nebius review boundary plus deterministic reconciliation that preserves the original
M7 assessment, applies only valid evidence-bound revisions, degrades safely when review
is unavailable, and updates proposal order without crossing the Candidate approval gate.

### Prompt used

[`docs/prompts/m8-independent-research-fit-review-nebius.md`](prompts/m8-independent-research-fit-review-nebius.md)

### Files changed

- Added `IndependentReviewModelPort`, `IndependentReviewInput`,
  `IndependentReviewResult`, `IndependentReviewAgent`, `IndependentReviewPolicy`, typed
  model errors, and the pure reconciliation function under `src/agents/`.
- Added independent-review decision, status, and failure enums plus the immutable
  `ReconciledResearchFitAssessment` audit overlay under `src/domain/`.
- Added the versioned `independent-review-v1` prompt and
  `NebiusReviewModelAdapter`, using native strict structured output with no provider
  retries or prose JSON parsing.
- Added deferred Nebius model, HTTPS endpoint, timeout, and credential settings under
  `src/config.py` and documented their non-secret defaults in `.env.example`.
- Replaced the graph review fixture, added typed review-record state, policy and model
  injection, lazy production composition, sanitized recoverable errors, M8 LangSmith
  metadata, deterministic effective-score ranking, and effective CLI output.
- Added the M8 prompt archive, generated Mermaid snapshot, README guidance, current
  architecture, terminology, contract coverage, fakes, unit tests, graph tests, guarded
  live test, and this journal entry.

### Tests added

- Domain and agent coverage for accepted assessments, valid revisions, immutable
  initial arithmetic, unsupported evidence removal, overlooked evidence validation,
  nonexistent or unsuitable IDs, exact-threshold behavior, large-disagreement attention,
  deterministic confidence degradation, and prohibited availability or admission prose.
- Offline Nebius adapter coverage for configured base URL, model, timeout, strict native
  JSON schema, disabled SDK retries, safe metadata, timeout mapping, malformed output,
  and sanitized exception text.
- Graph coverage for fake-only review of every assessment, deterministic shortlist
  reordering after a valid revision, timeout and malformed-output continuity, recoverable
  tool errors, configurable disagreement policy, missing credentials, and state reset
  across refinement cycles.
- Contract coverage for the provider-neutral port and schema, forbidden output fields,
  configured endpoint/model ownership, prompt/environment/diagram audit artifacts, and
  the guarded live-test boundary.
- One `pytest.mark.live` Nebius smoke test requiring both `NEBIUS_API_KEY` and explicit
  `SCHOLARPATH_RUN_LIVE_TESTS=true` opt-in.

### Test results

- Parallel focused domain, adapter, configuration, graph, CLI, tracing, Ruff, mypy, and
  diff checks passed without network access.
- The integrated pre-documentation suite passed 695 tests with six live tests
  deselected and 91.02 percent combined statement/branch coverage; the remaining
  documentation-contract failure was resolved by this M8 journal and artifact update.
- `venv/bin/ruff format --check .`: all 134 Python files were already formatted after
  the final formatting pass.
- `venv/bin/ruff check --no-cache .`: all lint checks passed.
- `venv/bin/mypy src tests`: no issues found in 109 source files.
- `venv/bin/pytest -q`: 714 non-live tests passed, six live tests were deselected, 43
  terminology subtests passed, and combined statement/branch coverage was 91.06 percent,
  above the 90 percent gate.
- Strict editable installation with local build isolation disabled and `--no-deps`
  succeeded without downloading dependencies; `venv/bin/python -m pip check` reported
  no broken requirements, and importing `scholarpath` reported version `0.1.0`.
- Compilation under both the current Python 3.14.6 interpreter and Python 3.12.13,
  generated M8 Mermaid equality, prompt and terminology contracts, default network
  isolation, and `git diff --check` passed.
- Explicit live-test selection skipped all six guarded provider tests without a network
  call: 714 non-live tests were deselected and six live tests skipped.
- `.env` and `venv/` remain ignored by the project `.gitignore`; no secret file was
  staged or committed.
- The fake-backed CLI completed M8 and printed five Supervisors with effective scores
  `87`, `82`, `75`, `72`, and `68` in deterministic rank order.

### Assumptions

- The Nebius Token Factory OpenAI-compatible endpoint and a structured-output-capable
  model are configuration defaults, not business-logic constants; operators may change
  both through environment variables.
- A reviewer may identify overlooked evidence only when that exact claim already exists
  in the same Verified Supervisor evidence collection. This references existing evidence
  and never creates a factual claim.
- An overall reviewed score cannot be deterministically redistributed across the five
  M7 components because the reviewer does not return component values. The initial
  component assessment therefore remains immutable and a separate reconciled overlay
  owns the effective score and explanation.
- `accept` always preserves the original score, rationale, citations, and confidence.
  The prompt asks the reviewer to echo the initial score, but deterministic reconciliation
  ignores a contradictory recommended score rather than weakening an accepted assessment.
- A provider or output failure is recoverable for each Supervisor: the original score
  remains usable, confidence drops one level, and Candidate attention is required.

### Lessons learned

- Independent review is an audit overlay, not permission to weaken the original scoring
  contract. Keeping both views preserves component arithmetic and reviewer accountability.
- Native structured output constrains shape, but ordinary code must still validate that
  every referenced ID belongs to the exact evidence set and is safe for Research Fit.
- A reviewer can surface overlooked existing evidence without becoming an evidence
  producer; provenance remains owned by the earlier verification boundary.
- Provider failure should change confidence and audit status, not erase a usable initial
  assessment or terminate recommendations that can still reach Candidate review.
- Revised ordering remains deterministic when synthesis consumes effective score and
  confidence, then applies the existing normalized-name and stable-ID tie-breakers.
- Keeping model name and endpoint in deferred settings makes provider migration and
  regional deployment possible without contaminating domain or reconciliation logic.

### Remaining debt

- Build a LangSmith evaluation dataset for reviewer agreement, unsupported-claim
  precision, overlooked-evidence recall, revision magnitude, and safe-fallback rate.
- Calibrate the disagreement threshold and reviewer confidence against expert human
  judgments before production use.
- Add explicit provider cost, latency, rate-limit, circuit-breaker, and batch/concurrency
  controls before reviewing large Supervisor cohorts.
- Define durable versioning and persistence for paired initial and reconciled assessments,
  plus a Candidate-facing explanation of why attention is required.
- Evaluate additional structured-output-capable Nebius models and regional endpoints
  without changing the provider-neutral port or deterministic policy.
- Add a compact provider projection so the nested `VerifiedSupervisor.evidence` and
  explicit `evidence_claims` input contract do not duplicate evidence tokens on the wire.
- Evaluate false-positive rates for the deliberately conservative availability-inference
  prose guard, especially for Candidates whose research topic is doctoral supervision.

## Milestone M8 live-validation repair: current Nebius inference model

**Date:** 2026-08-29

### Milestone objective

Repair the M8 live Nebius smoke path after the configured base model returned `404`,
without changing the provider-neutral review port, deterministic reconciliation, or any
other workflow node.

### Prompt used

The archived M8 prompt remains
[`docs/prompts/m8-independent-research-fit-review-nebius.md`](prompts/m8-independent-research-fit-review-nebius.md).
This repair was triggered by the Candidate-provided live-test traceback reporting that
`Qwen/Qwen3-235B-A22B` did not exist at the configured inference endpoint.

### Files changed

- Updated the deferred Nebius review-model default in `src/config.py`, `.env.example`,
  and `README.md` to the model ID returned by the authenticated `/v1/models` catalog.
- Preserved `independent-review-v1` and added `independent-review-v2`, which explicitly
  limits critique output to at most 100 words and prevents unnecessary input restatement.
- Updated the adapter, public agent exports, observability expectations, architecture,
  generated Mermaid snapshot, configuration tests, and M8 contract assertions.
- Updated only the non-secret model value in the ignored local `.env`; the API token was
  neither printed nor added to version control.

### Tests added or updated

- Updated the configuration unit test to lock the current inference-model default.
- Updated the M8 contract test to lock the new model, prompt version, and explicit
  critique-length instruction.
- Updated observability coverage to lock `independent-review-v2` trace metadata.

### Test results

- Authenticated Nebius model discovery succeeded against the official read-only
  `/v1/models` endpoint without exposing the token.
- The first replacement-model probe reached structured output but correctly failed local
  validation because its critique exceeded 120 words; this motivated the v2 prompt.
- The repaired guarded live test passed: `1 passed in 2.98s`.
- `venv/bin/ruff format --check .`: all 134 Python files formatted.
- `venv/bin/ruff check --no-cache .`: all lint checks passed.
- `venv/bin/mypy src tests`: no issues in 109 source files.
- `venv/bin/pytest -q`: 714 non-live tests passed, six live tests were deselected, 43
  terminology subtests passed, and combined statement/branch coverage was 91.07 percent.
- `git diff --check` passed.

### Assumptions

- Nebius's authenticated model-list endpoint is the runtime source of truth for model
  availability; documentation can include fine-tuning models that are not exposed for
  serverless inference.
- `Qwen/Qwen3-235B-A22B-Instruct-2507` remains environment-overridable so an operator can
  migrate again without changing business logic.
- A 100-word prompt limit intentionally leaves safety margin beneath the immutable
  120-word domain validator.

### Lessons learned

- Authentication and endpoint correctness can be distinguished from model availability:
  a provider `404` after a valid request proves the first two boundaries are working.
- Strict JSON Schema guarantees response shape, but semantic validators such as word
  counts still require explicit prompt instructions and ordinary-code validation.
- Live provider smoke tests catch model-catalog drift that deterministic default tests
  must never discover through network calls.

### Remaining debt

- Add a read-only operational preflight that checks the configured model against the
  provider catalog before a full graph run, while keeping default tests offline.
- Evaluate a lower-cost Nebius model against the same review-quality and structured-output
  contract before changing the production default.
- Add a scheduled live compatibility check outside the default CI gate so provider model
  retirement is detected before an interactive run.

## Milestone M8 live-output stabilization

**Date:** 2026-08-29

### Milestone objective

Remove a live-test failure mode in which a structurally valid Nebius response repeated a
safe availability disclaimer that the stricter ScholarPath Research Fit prose contract
correctly excludes from score-bearing review text.

### Prompt used

The archived M8 prompt remains
[`docs/prompts/m8-independent-research-fit-review-nebius.md`](prompts/m8-independent-research-fit-review-nebius.md).
This stabilization was triggered by the Candidate-provided sanitized adapter traceback
and a clean live reproduction of the underlying structured-output validation failure.

### Files changed

- Preserved prompt versions v1 and v2 and added `independent-review-v3`, which requires
  availability and admission checks to happen silently and keeps critique text focused
  only on Research Fit evidence.
- Configured the Nebius chat adapter with temperature `0.0` to reduce avoidable output
  variance while retaining strict JSON Schema and zero SDK retries.
- Updated public exports, current architecture, Mermaid trace metadata, unit tests,
  contract tests, observability expectations, and this journal.

### Tests added or updated

- Extended the adapter unit test to require temperature `0.0`.
- Extended the M8 contract test to lock prompt v3 and its silent safety-check instruction.
- Updated the observability test to require `independent-review-v3` metadata.

### Test results

- The guarded Nebius live test passed with an explicit current model override:
  `1 passed in 2.66s`.
- `venv/bin/ruff format --check .`: all 134 Python files formatted.
- `venv/bin/ruff check --no-cache .`: all lint checks passed.
- `venv/bin/mypy src tests`: no issues in 109 source files.
- `venv/bin/pytest -q`: 714 non-live tests passed, six live tests were deselected, 43
  terminology subtests passed, and combined statement/branch coverage was 91.07 percent.
- `git diff --check` passed.

### Assumptions

- A reviewer can validate internally that availability did not influence Research Fit
  without repeating that status in its score-bearing critique.
- Temperature `0.0` reduces variance but does not replace strict ordinary-code validation
  or the existing safe graph fallback.

### Lessons learned

- A response can satisfy JSON Schema yet fail semantic domain policy; both validation
  layers are necessary.
- Safety instructions and output instructions must agree: asking a model to inspect a
  prohibited factor should explicitly state whether it may mention that check.
- Optional live tests reveal probabilistic contract mismatches that fixed fakes cannot
  reproduce unless the observed case is added to their assertions.

### Remaining debt

- Add an evaluation set of safe disclaimers and unsafe availability inferences to measure
  prompt compliance across alternative Nebius models.
- Decide whether a bounded application-level output retry is worth its additional cost;
  the current graph intentionally preserves the original assessment on invalid output.

## Milestone M9: Candidate review interrupt and durable graph persistence

**Date:** 2026-08-29

### Milestone objective

Replace the synchronous fixture review gate with a real LangGraph interrupt that presents
the complete evidence-backed Supervisor proposal, requires an explicit typed Candidate
response, persists paused state by thread ID, and resumes safely through approval or a
bounded refinement route. Add isolated in-memory checkpoints for tests and restart-safe
SQLite checkpoints for trusted local development without adding Mem0 or outreach.

### Prompt used

The exact milestone prompt is archived as
[`m9-candidate-review-interrupt-and-persistence.md`](prompts/m9-candidate-review-interrupt-and-persistence.md).

### Files changed

- Added `src/graph/review.py` with `CandidateReviewInterruptPayload`, action-specific
  approve/reject/request-more response models, JSON-safe payload projection, deterministic
  parsing, and resume-value conversion.
- Added `src/graph/persistence.py` with isolated `InMemorySaver` construction, a local
  SQLite checkpointer context manager, strict MessagePack type allowlisting, and safe URL
  serialization without pickle fallback.
- Replaced `candidate_review_gate_stub` in `src/graph/workflow.py` with the real
  `interrupt()`/`Command(resume=...)` path, explicit thread configuration, bounded invalid
  input and refinement routes, subset approval, per-Supervisor rejection reasons, and
  downstream-only shortlist persistence.
- Extended `ScholarPathState` with a review-validation error and independent invalid-input
  counter; extended `CandidatePreferenceRevision` with typed constraints.
- Added `SCHOLARPATH_CHECKPOINT_DATABASE_PATH` to typed settings and `.env.example`, ignored
  `.scholarpath/`, pinned the patched `langgraph-checkpoint-sqlite==3.1.1` package, and
  advanced safe observability metadata to `graph-version:m9`.
- Updated the public graph API and CLI so an ordinary run reports the paused payload; an
  explicit response is required before a completed shortlist can be printed.
- Updated `README.md`, `docs/architecture.md`, `docs/terminology.md`, and the generated
  [`m9-candidate-review-persistence-graph.mmd`](m9-candidate-review-persistence-graph.mmd).
- Adapted historical M2–M8 graph, CLI, configuration, and contract tests to keep old
  diagrams historical while exercising the current explicit interrupt boundary.

### Tests added

- `tests/unit/graph/test_candidate_review.py` validates all three response schemas,
  malformed and ambiguous values, JSON round trips, complete payload projection, source
  links, and redaction of full Candidate and evidence content.
- `tests/graph/test_m9_candidate_review_interrupt.py` validates pause and inspection,
  approval of an ordered subset, per-Supervisor rejection, preference refinement, thread
  isolation, no pre-approval save, invalid-ID re-prompting, bounded loops, and resume
  idempotency.
- `tests/integration/test_m9_sqlite_persistence.py` closes the first application instance,
  opens a fresh graph against the same SQLite file, inspects the paused thread, and resumes
  it to an approved shortlist.
- `tests/contract/test_m9_candidate_review_persistence_contract.py` locks the dependency,
  environment, ignore, interrupt/resume, safe serializer, prompt, diagram, graph-version,
  no-Mem0, and no-outreach boundaries.
- `tests/unit/graph/test_persistence.py` proves unregistered models and tampered model or
  enum markers are rejected instead of dynamically imported.
- Extended configuration tests for the checkpoint-path default and environment override.

### Test results

- Focused M9 graph tests: `10 passed`.
- Focused M9 response and SQLite tests: `19 passed`.
- Legacy M2–M8 adaptation suite: `92 passed`.
- `venv/bin/ruff format --check .`: all 142 Python files formatted.
- `venv/bin/ruff check --no-cache .`: all lint checks passed.
- `venv/bin/mypy src tests`: no issues in 116 source files.
- `venv/bin/pytest -q`: 753 non-live tests passed, six live tests were deselected, 44
  terminology subtests passed, and combined statement/branch coverage was 91.42 percent.
- Strict editable installation completed with the pinned SQLite checkpointer; `pip check`
  reported no broken requirements and a fresh import exposed the persistence API.
- The offline CLI persisted and paused with five fully populated review items and no
  shortlist save; a fresh Python process reopened that thread, approved one explicit ID,
  and completed with exactly that one Shortlisted Supervisor.
- The 60-second SQLite close/reopen demonstration passed: `1 passed in 0.54s`.
- `git diff --check` passed.

### Assumptions

- A thread ID is an opaque run key generated by application code; it is not a Candidate
  name, email address, authorization token, or globally reusable session identifier.
- SQLite is appropriate for trusted, local, single-process development and restart tests;
  it is not the selected horizontally scaled production checkpoint store.
- One Candidate response may approve an ordered subset of one to five current proposal
  IDs; unselected proposal records remain Verified rather than being implicitly rejected.
- Rejection routes to a fresh search-planning cycle. `request_more` appends the exact typed
  preference revision before that same bounded cycle.
- Candidate review payloads may contain public source URLs and concise concerns, but never
  full retrieved pages, API keys, email addresses, or the full research statement.

### Lessons learned

- LangGraph resumes an interrupted node from its beginning, so every operation before
  `interrupt()` must be deterministic and side-effect-free. The current node only builds
  a typed presentation payload before pausing.
- Human input needs two validation layers: action-specific Pydantic schemas validate shape,
  and deterministic proposal-scope checks validate exact Supervisor IDs.
- A checkpointer turns `thread_id` into a data-isolation boundary. The same ID must resume a
  run, while a different ID must never inherit its proposal, decisions, or lifecycle state.
- LangGraph's default MessagePack path does not directly encode Pydantic `HttpUrl` values.
  A JSON-mode model projection plus an explicit deserialization allowlist preserves typed
  state without enabling executable pickle checkpoints.
- Candidate authority is easiest to prove structurally when shortlist saving and briefing
  generation are downstream nodes that cannot run while the interrupt remains unresolved.

### Remaining debt

- Add Streamlit rendering and authenticated session-to-thread ownership without weakening
  the typed response boundary or treating display as approval.
- Define checkpoint encryption, filesystem permissions, retention, deletion, audit access,
  and backup policy before persisting real Candidate data beyond local development.
- Select a production checkpointer that supports concurrent processes, connection pooling,
  operational monitoring, and disaster recovery.
- Decide whether rejected Supervisors should be suppressed permanently, reconsidered after
  material preference changes, or offered through an explicit Candidate override policy.
- Add Mem0 behind a typed preference-memory port in a later milestone; M9 feedback remains
  only in checkpointed graph state.
- Add LangSmith evaluations for pause-to-decision latency, invalid-response rate, repeated
  refinement frequency, and premature-lifecycle-promotion regressions.

## Milestone M10: persistent Candidate preference memory

**Date:** 2026-08-29

### Milestone objective

Add persistent, Candidate-scoped preference memory through Mem0 without making memory the
source of truth for Supervisor facts or graph position. Recall permitted durable preferences
before planning; write only after an explicit Candidate action; keep viewing side-effect
free; and continue safely when long-term memory is unavailable.

### Prompt used

The exact milestone prompt is archived as
[`m10-persistent-candidate-preference-memory.md`](prompts/m10-persistent-candidate-preference-memory.md).

### Files changed

- Added `src/memory/models.py`, `ports.py`, `preference_learning.py`, and
  `mem0_adapter.py` with a finite Pydantic memory allowlist, stable semantic IDs, a typed
  `CandidatePreferenceMemoryPort`, deterministic action projection, and hosted Mem0
  direct import using `infer=False`.
- Added lazy `Mem0MemorySettings`, deferred credential validation, configured timeouts and
  record limits, telemetry-off default, `.env.example` guidance, and the current official
  `mem0ai==2.0.19` dependency.
- Extended planning input with identity-free typed recalled records and extended graph
  state with merged memory records, availability, and a processed-feedback cursor.
- Replaced fixture-only preference loading with Candidate-scoped recall and added the
  `learn_candidate_preferences` node after the durable Candidate review interrupt.
- Registered memory records with the strict checkpoint serializer, advanced trace metadata
  to `graph-version:m10`, and updated the CLI dependency-injection boundary.
- Added `FakeCandidatePreferenceMemory`, updated existing offline graph harnesses, and
  updated current architecture, README, the generated
  [`m10-candidate-preference-memory-graph.mmd`](m10-candidate-preference-memory-graph.mmd),
  historical contracts, and this journal.

### Tests added

- `tests/unit/memory/test_candidate_preference_memory.py` validates schema privacy,
  Candidate isolation, deterministic duplicates, every explicit action, and exclusion of
  Supervisor factual evidence.
- `tests/unit/memory/test_mem0_adapter.py` validates exact scoped SDK requests, untrusted
  result filtering, direct import, idempotency, and sanitized provider failures using a
  recording client.
- `tests/graph/test_m10_candidate_preference_memory.py` validates load-before-plan,
  rejection and approval writes, zero writes while viewing, planning influence, non-fatal
  read/write failures, and fake-only default execution.
- `tests/integration/test_mem0_memory_live.py` provides an explicitly opted-in, UUID-scoped
  Mem0 round trip with cross-Candidate isolation and scoped cleanup.
- `tests/contract/test_m10_candidate_preference_memory_contract.py` locks the dependency,
  typed boundary, saved prompt, current diagram, graph version, and no-outreach boundary.
- Extended configuration, initial-state, topology, interrupt-idempotency, CLI, SQLite, and
  historical milestone tests for the M10 composition.

### Test results

- Focused M10 offline memory tests: `22 passed`.
- Focused configuration and M0/M2/M9 compatibility suite: `101 passed`.
- The pinned SDK installed into the strict editable environment successfully.
- `venv/bin/ruff format --check .`: all 154 Python files formatted.
- `venv/bin/ruff check --no-cache .`: all lint checks passed.
- `venv/bin/mypy src tests`: no issues in 127 source files.
- `venv/bin/pytest -q`: 786 non-live tests passed, seven live tests were deselected, 45
  terminology subtests passed, and combined statement/branch coverage was 90.71 percent.
- The Mem0 live test skipped cleanly without explicit opt-in: `1 skipped`.
- `venv/bin/pip check` reported no broken requirements; a fresh import exposed the typed
  port and Mem0 adapter without constructing an SDK client or requiring a key.
- The current Mermaid snapshot matched the compiled sixteen-node graph exactly.
- The 60-second view/no-write plus approval/write demonstration passed: `2 passed in 0.68s`.
- `git diff --check` passed.
- Follow-up hosted validation exposed an SDK request-shape asymmetry: recall correctly uses
  `get_all(filters={"user_id": ...})`, while the V1 bulk-delete endpoint requires
  `delete_all(user_id=...)`. The live-test cleanup was corrected, protected by an offline
  contract test, and the real Mem0 round trip then passed: `1 passed in 4.03s`.

### Assumptions

- `CandidateProfile` and explicit current-run revisions remain authoritative for the
  current interaction; recalled memory enriches planning but cannot alter Supervisor facts.
- Approval of the proposed shortlist makes the current expanded search concepts a durable
  positive signal. It does not store approved Supervisor names, profiles, evidence, scores,
  or availability.
- A rejection memory may retain an opaque Supervisor ID and the Candidate-authored reason,
  because the milestone explicitly permits rejected Supervisor reasons; no factual profile
  fields accompany it.
- Hosted Mem0 is the production adapter target. Writes use its additive asynchronous API,
  so an accepted request is not treated as immediate read-after-write consistency.
- Stable `candidate_id` scopes Mem0 across research runs; LangGraph `thread_id` continues to
  isolate the position of one run and is never used as the long-term memory user key.

### Lessons learned

- Human-interrupt side effects are safest in a downstream node. The review node checkpoints
  the valid action first, so displaying or pausing cannot create memory.
- Exact typed JSON with provider inference disabled prevents a memory service from
  broadening a Candidate preference beyond what ScholarPath validated.
- External ADD-only memory needs two idempotency controls: a deterministic semantic record
  key and a scoped pre-write lookup. The graph cursor prevents normal resume replays.
- Provider memory is untrusted input. Parsing only a versioned schema and ignoring malformed
  or unrelated entries prevents arbitrary account memories from entering model input.
- Non-fatal memory must preserve both directions: current profile data survives read failure,
  and explicit Candidate action plus local graph state survives write failure.
- Provider SDK option models are not sufficient evidence of wire compatibility. The pinned
  SDK's retrieval and deletion methods use different endpoint generations, so request shapes
  must be verified at the HTTP boundary as well as through type signatures.

### Remaining debt

- Define Candidate consent, retention, deletion, export, residency, access logging, and
  incident-response controls before using Mem0 with real Candidate data.
- Add bounded polling or an event-status workflow if the product needs confirmed durable
  write acknowledgement rather than accepted asynchronous submission.
- Evaluate semantic memory relevance and limits with real opt-in Candidate feedback; M10
  intentionally loads only the bounded, versioned ScholarPath record set.
- Decide how a Candidate explicitly retracts or supersedes an older durable preference;
  M10 deduplicates additive records but does not implement deletion or conflict resolution.
- Add production metrics for memory availability, duplicate suppression, write latency,
  and the effect of recalled preferences on recommendation relevance.

## Milestone M11: Streamlit user interface

**Date:** 2026-08-29

### Milestone objective

Deliver one focused Candidate-facing Streamlit application for doctoral research-profile
intake, safe graph progress, Prospective and Verified Supervisor evidence, explicit review,
and the approved shortlist. Keep graph state in the durable checkpointer, retain only the
opaque thread ID and interface controls in Session State, and expose no hidden reasoning or
provider secrets.

### Prompt used

The exact milestone prompt is archived as
[`m11-streamlit-user-interface.md`](prompts/m11-streamlit-user-interface.md).

### Files changed

- Added the pinned `streamlit==1.62.0` runtime dependency and root `streamlit_app.py`
  entrypoint.
- Added `src/ui/models.py` with typed Candidate submission, progress, evidence, Supervisor,
  error, and safe run-projection contracts.
- Added `src/ui/controller.py` with deterministic form normalization, request-more
  construction, canonical progress allowlisting, interrupt recovery, and graph-to-UI
  projection.
- Added `src/ui/service.py` and `src/ui/dependencies.py` with the typed
  `ScholarPathApplicationPort`, start/inspect/resume operations, stale-checkpoint protection,
  SQLite-backed local composition, and opaque identifier generation.
- Added `src/ui/app.py` with the six canonical stages, profile form, safe progress status,
  evidence-backed results, approval, required-reason rejection, request-more refinement,
  recoverable error display, and thread-correct resume.
- Extracted reusable `ScholarPathRuntime` construction from `run_scholarpath_graph` so the
  UI service can compile the graph once without moving composition into Streamlit.
- Advanced safe trace metadata to `graph-version:m11`, updated public exports and historical
  dependency contracts, and added `FakeScholarPathApplication` for browser-independent UI
  tests.
- Updated `README.md`, current architecture, the
  [`m11-streamlit-interface.mmd`](m11-streamlit-interface.mmd) diagram, and this journal.

### Tests added

- `tests/unit/ui/test_controller.py` validates required form fields, deterministic list
  normalization, typed refinement, raw-update filtering, canonical progress, and privacy-safe
  Supervisor projections.
- `tests/integration/test_m11_ui_graph_service.py` runs the real graph offline with injected
  fakes and validates start, streamed progress, pause, persisted inspection, thread isolation,
  explicit approval, stale checkpoints, and wrong-thread rejection.
- `tests/integration/test_streamlit_app.py` provides thirteen AppTest cases for form rendering,
  required validation, terminology, run start, progress, verified evidence, all three review
  actions, correct-thread resume, recoverable failures, secret redaction, and session isolation.
- `tests/contract/test_m11_streamlit_ui_contract.py` locks the dependency, entrypoint,
  six-stage labels, v2 streaming allowlist, Session State boundary, archived prompt, README
  command, graph version, and no-outreach boundary.
- Historical M0, M2, and M10 contracts were advanced only where they describe the current
  dependency and graph-version composition.

### Test results

- Focused controller and real offline service tests: `16 passed`.
- Focused M11 architecture contracts: `5 passed`.
- Focused AppTest suite: `13 passed`; it executes entirely against
  `FakeScholarPathApplication`, so no provider or network is used.
- The first complete suite run passed 807 tests but correctly failed the audit link and
  coverage gates before this journal entry and the AppTest suite were finalized.
- `venv/bin/ruff format --check .`: all 167 Python files formatted.
- `venv/bin/ruff check --no-cache .`: all lint checks passed.
- `venv/bin/mypy src tests`: no issues in 138 source files.
- `venv/bin/pytest -q`: 820 non-live tests passed, seven live tests were deselected, 46
  terminology subtests passed, and combined statement/branch coverage was 90.21 percent.
- `venv/bin/pip check` reported no broken requirements; Python compilation and
  `git diff --check` passed.
- A headless `venv/bin/streamlit run streamlit_app.py` smoke test started the local server
  successfully and exited cleanly; no provider was instantiated during initial rendering.

### Assumptions

- Until authentication is introduced, the UI creates an opaque Candidate ID for each new
  research run. The opaque LangGraph thread ID is separate and remains the checkpoint key.
- A single cached local application service is suitable for trusted single-process
  development; its lock serializes the shared SQLite connection. Production requires a
  concurrent checkpoint store and authenticated ownership checks.
- Showing progress by canonical node name is sufficient for M11. Raw stream update bodies,
  model messages, and provider payloads have no Candidate-facing diagnostic value.
- Prospective and Verified Supervisor lists remain visible on the review and shortlist
  screens to preserve the requested stage progression; they are read-only projections.
- Provider setup failures are rendered as generic recoverable guidance. Detailed operational
  diagnostics belong in protected logs and traces, not the Candidate browser.

### Lessons learned

- A delivery adapter stays testable when start, inspect, and resume are a small typed port;
  AppTest can replace infrastructure without patching graph business rules.
- LangGraph v2 update events contain useful progress and sensitive state in the same envelope.
  An explicit node-name allowlist provides progress while discarding the raw delta.
- A checkpoint token complements the thread ID: the thread selects a run and the token
  prevents stale browser tabs from applying an action to a newer review checkpoint.
- Streamlit widget values are interface state, while Candidate research and Supervisor
  evidence are workflow state. Keeping that distinction prevents a browser rerun from
  becoming a second source of truth.
- Candidate approval remains structurally downstream of the interrupt; rendering, refreshing,
  or reopening a page cannot save a shortlist or create outreach.

### Remaining debt

- Add authentication and authorization that bind a verified Candidate identity to permitted
  thread IDs; opaque identifiers are isolation keys, not access control.
- Replace the single-process SQLite resource with an encrypted, concurrent production
  checkpointer with retention, deletion, backup, monitoring, and disaster recovery.
- Perform accessibility, responsive-layout, browser-security, and usability testing with
  representative Candidates and assistive technologies.
- Add cancellation, background execution, reconnect status, quotas, and backpressure for
  research runs that approach the fifteen-minute product target.
- Define protected operational logging and support correlation IDs without exposing provider
  failures, personal data, secrets, full pages, or research statements to the browser.
