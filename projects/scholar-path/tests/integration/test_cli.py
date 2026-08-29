"""Offline integration tests for the installed ScholarPath CLI demonstration."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scholarpath import cli
from scholarpath.config import (
    ApplicationSettings,
    Environment,
    LangSmithSettings,
    ProviderConfigurationError,
)
from scholarpath.graph import (
    ScholarPathState,
    build_walking_skeleton_fixtures,
    create_initial_state,
    run_scholarpath_graph,
)
from tests.fakes import FakePlanningModel


def test_cli_prints_five_ranked_shortlisted_supervisors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = FakePlanningModel()

    def run_offline_graph(*, planning_model: FakePlanningModel) -> ScholarPathState:
        assert planning_model is model
        return run_scholarpath_graph(
            planning_model=planning_model,
            application_settings=ApplicationSettings(environment=Environment.TEST),
            langsmith_settings=LangSmithSettings(tracing=False),
        )

    monkeypatch.setattr(cli, "run_scholarpath_graph", run_offline_graph)

    exit_code = cli.main(model)
    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    assert exit_code == 0
    assert lines[0] == "ScholarPath Shortlist: 5 Supervisors"
    assert len(lines) == 6
    assert model.call_count == 1
    assert lines[1].startswith("1. Dr Amara Ndlovu")
    assert lines[5].startswith("5. Dr Theo Laurent")
    assert all("/100" in line for line in lines[1:])


def test_cli_returns_failure_when_no_shortlist_is_available(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    fixtures = build_walking_skeleton_fixtures()
    incomplete_state = create_initial_state(fixtures.candidate_profile)
    monkeypatch.setattr(
        cli,
        "run_scholarpath_graph",
        lambda **_kwargs: incomplete_state,
    )

    exit_code = cli.main(FakePlanningModel())
    captured = capsys.readouterr()

    assert exit_code == 1
    assert captured.out == "ScholarPath did not produce a completed Supervisor shortlist.\n"


def test_cli_module_reports_missing_openai_key_without_a_traceback(tmp_path: Path) -> None:
    environment = {
        name: value
        for name, value in os.environ.items()
        if name not in {"OPENAI_API_KEY", "LANGSMITH_API_KEY", "LANGSMITH_TRACING"}
    }
    result = subprocess.run(
        [sys.executable, "-m", "scholarpath.cli"],
        cwd=tmp_path,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 2
    assert result.stderr == ""
    assert result.stdout == (
        "ScholarPath provider configuration error: Missing API key for provider 'openai'.\n"
    )


def test_cli_reports_the_actual_provider_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fail_graph(**_kwargs: object) -> ScholarPathState:
        raise ProviderConfigurationError(
            "Missing API key for provider 'langsmith' while tracing is enabled."
        )

    monkeypatch.setattr(cli, "run_scholarpath_graph", fail_graph)

    exit_code = cli.main(FakePlanningModel())
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == (
        "ScholarPath provider configuration error: "
        "Missing API key for provider 'langsmith' while tracing is enabled.\n"
    )
