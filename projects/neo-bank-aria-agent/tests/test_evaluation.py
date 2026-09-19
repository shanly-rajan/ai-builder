from __future__ import annotations

from pathlib import Path

from evaluation.reporting import load_json, render_report, validate, validate_evidence_files

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_every_required_attack_family_has_a_case() -> None:
    payload = load_json(PROJECT_ROOT / "evaluation" / "test_cases.json")
    families = {case["attack_family"] for case in payload["cases"]}

    assert {
        "Jailbreaking",
        "Obfuscation",
        "Prompt Injection",
        "Red Teaming",
        "Crescendo",
        "PII Extraction",
        "Social Engineering",
    } <= families


def test_initial_result_ledger_is_structurally_valid() -> None:
    test_cases = load_json(PROJECT_ROOT / "evaluation" / "test_cases.json")
    results = load_json(PROJECT_ROOT / "evaluation" / "results.json")

    assert validate(test_cases, results, require_complete=False) == []


def test_breaking_suite_covers_every_security_category() -> None:
    test_cases = load_json(PROJECT_ROOT / "evaluation" / "breaking_test_cases.json")
    results = load_json(PROJECT_ROOT / "evaluation" / "breaking_results.json")
    families = {case["attack_family"] for case in test_cases["cases"]}

    assert families == {
        "Jailbreaking",
        "Obfuscation",
        "Sensitive Data Exposure",
        "Prompt Injection",
        "Red Teaming",
        "Crescendo",
        "PII Extraction",
        "Social Engineering",
    }
    assert validate(test_cases, results, require_complete=False) == []


def test_breaking_suite_cases_are_executable_and_unscored_until_run() -> None:
    test_cases = load_json(PROJECT_ROOT / "evaluation" / "breaking_test_cases.json")
    results = load_json(PROJECT_ROOT / "evaluation" / "breaking_results.json")

    assert len(test_cases["cases"]) == 8
    assert all(case["id"].endswith("-02") for case in test_cases["cases"])
    assert all(case.get("session") in {"fresh_chat", "same_chat_all_turns", "same_chat_variants"} for case in test_cases["cases"])
    assert all(case.get("break_condition") for case in test_cases["cases"])
    assert validate(test_cases, results, require_complete=True) == []
    assert all(result["outcome"] != "NOT_RUN" for result in results["results"])


def test_submission_evidence_files_exist() -> None:
    test_cases = load_json(PROJECT_ROOT / "evaluation" / "test_cases.json")
    results = load_json(PROJECT_ROOT / "evaluation" / "results.json")

    result_errors = validate(test_cases, results, require_complete=True)
    evidence_errors = validate_evidence_files(results, PROJECT_ROOT)

    assert result_errors == []
    assert evidence_errors == []


def test_report_contains_each_case_and_submission_sections() -> None:
    test_cases = load_json(PROJECT_ROOT / "evaluation" / "test_cases.json")
    results = load_json(PROJECT_ROOT / "evaluation" / "results.json")

    report = render_report(test_cases, results)

    assert "## Findings" in report
    assert "## Defense-in-depth recommendation" in report
    assert "## Submission checklist" in report
    assert all(case["id"] in report for case in test_cases["cases"])
