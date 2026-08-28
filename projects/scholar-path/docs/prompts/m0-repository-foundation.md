# Milestone M0 Prompt: Repository Foundation and Engineering Contract

Implement ScholarPath Milestone M0: repository foundation and engineering contract.

First inspect the repository and report what already exists. Preserve any
working conventions. If the repository is empty, create a Python src-layout
project targeting Python 3.12 or the repository's existing supported version.

Create the following structure:

```text
src/scholarpath/
__init__.py
config.py
domain/
graph/
agents/
tools/
memory/
observability/
ui/

tests/
unit/
graph/
contract/
integration/
fixtures/

docs/
terminology.md
architecture.md
build-journal.md
prompts/
```

Add:

- pyproject.toml
- .env.example
- .gitignore
- README.md
- AGENTS.md using the ScholarPath Engineering Contract
- pytest configuration
- Ruff configuration
- mypy configuration
- pytest-cov configuration
- GitHub Actions workflow for lint, type checking, and non-live tests

Keep runtime dependencies minimal. Add only what M0 needs:
Pydantic, pydantic-settings, and development/test tooling.

Define application settings, but do not require API keys merely to import the
package or run unit tests. API-key validation must happen only when the
corresponding provider is instantiated.

Document the canonical Candidate and Supervisor terminology in
docs/terminology.md.

Add tests for:

1. Importing scholarpath without API keys.
2. Loading non-secret defaults.
3. Rejecting invalid configuration only when a provider is requested.
4. Detecting banned terminology such as "supervisor candidate" in src and docs.
5. Successful test discovery.

Do not add LangGraph, models, search APIs, Streamlit, or Mem0 yet.

Definition of done:

- The package installs locally.
- Linting passes.
- Type checking passes.
- All tests pass without network access.
- README contains exact setup and test commands.
