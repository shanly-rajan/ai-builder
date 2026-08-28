"""Contract tests for ScholarPath's milestone governance artifacts."""

import unittest
from pathlib import Path

TEST_FILE = Path(__file__).resolve()
PROJECT_ROOT = TEST_FILE.parents[2]
REPOSITORY_ROOT = TEST_FILE.parents[4]
CONTRACT_FILE = PROJECT_ROOT / "AGENTS.md"
PROJECT_GITIGNORE = PROJECT_ROOT / ".gitignore"
PROMPTS_DIRECTORY = PROJECT_ROOT / "docs" / "prompts"
BUILD_JOURNAL = PROJECT_ROOT / "docs" / "build-journal.md"


class EngineeringContractTests(unittest.TestCase):
    """Verify that the standing contract and milestone audit trail exist."""

    def test_standing_contract_is_scoped_to_scholarpath(self) -> None:
        self.assertTrue(CONTRACT_FILE.is_file())
        self.assertFalse((REPOSITORY_ROOT / "AGENTS.md").exists())

    def test_standing_contract_contains_critical_guardrails(self) -> None:
        contract = CONTRACT_FILE.read_text(encoding="utf-8")

        required_guardrails = (
            "# ScholarPath Engineering Contract",
            'Never call a Supervisor a "candidate".',
            "Keep deterministic operations deterministic.",
            "Default tests must never call a live model",
            "Preserve source provenance for every factual claim about a Supervisor.",
            "Never calculate an admission probability.",
            "Candidate approval is mandatory before a Supervisor becomes shortlisted",
            "Save a copy of the milestone prompt in docs/prompts/.",
        )

        for guardrail in required_guardrails:
            with self.subTest(guardrail=guardrail):
                self.assertIn(guardrail, contract)

    def test_milestone_audit_artifacts_exist(self) -> None:
        prompt_files = tuple(PROMPTS_DIRECTORY.glob("*.md"))

        self.assertTrue(prompt_files, "At least one saved milestone prompt is required")
        self.assertTrue(BUILD_JOURNAL.is_file(), "The build journal is required")

        journal = BUILD_JOURNAL.read_text(encoding="utf-8")
        for prompt_file in prompt_files:
            with self.subTest(prompt_file=prompt_file.name):
                self.assertIn(f"(prompts/{prompt_file.name})", journal)

    def test_build_journal_records_required_sections(self) -> None:
        journal = BUILD_JOURNAL.read_text(encoding="utf-8")

        required_sections = (
            "### Milestone objective",
            "### Prompt used",
            "### Files changed",
            "### Tests added",
            "### Test results",
            "### Assumptions",
            "### Lessons learned",
            "### Remaining debt",
        )

        for section in required_sections:
            with self.subTest(section=section):
                self.assertIn(section, journal)

    def test_project_gitignore_covers_local_only_files(self) -> None:
        gitignore = PROJECT_GITIGNORE.read_text(encoding="utf-8")

        required_patterns = (
            ".env",
            ".env.*",
            "!.env.example",
            "/.venv/",
            "/venv/",
            "__pycache__/",
            ".pytest_cache/",
            ".ruff_cache/",
            ".mypy_cache/",
            ".streamlit/secrets.toml",
            "/data/private/",
            "/artifacts/",
            "*.log",
            "*.sqlite3",
        )

        for pattern in required_patterns:
            with self.subTest(pattern=pattern):
                self.assertIn(pattern, gitignore)


if __name__ == "__main__":
    unittest.main()
