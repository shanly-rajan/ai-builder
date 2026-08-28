"""Offline integration tests for the installed ScholarPath CLI demonstration."""

import subprocess
import sys
from pathlib import Path

import pytest

from scholarpath import cli
from scholarpath.graph import build_walking_skeleton_fixtures, create_initial_state


def test_cli_prints_five_ranked_shortlisted_supervisors(
    capsys: pytest.CaptureFixture[str],
) -> None:
    exit_code = cli.main()
    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    assert exit_code == 0
    assert lines[0] == "ScholarPath Shortlist: 5 Supervisors"
    assert len(lines) == 6
    assert lines[1].startswith("1. Dr Amara Ndlovu")
    assert lines[5].startswith("5. Dr Theo Laurent")
    assert all("/100" in line for line in lines[1:])


def test_cli_returns_failure_when_no_shortlist_is_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = build_walking_skeleton_fixtures()
    incomplete_state = create_initial_state(fixtures.candidate_profile)
    monkeypatch.setattr(cli, "run_scholarpath_graph", lambda: incomplete_state)

    exit_code = cli.main()
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == "ScholarPath did not produce a completed Supervisor shortlist.\n"


def test_cli_module_runs_from_outside_the_project_directory(tmp_path: Path) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "scholarpath.cli"],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert result.stderr == ""
    assert result.stdout.count("/100") == 5
