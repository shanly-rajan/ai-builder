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
