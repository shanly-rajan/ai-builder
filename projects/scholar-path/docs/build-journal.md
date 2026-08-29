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
