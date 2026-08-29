"""Offline integration tests for the installed ScholarPath CLI demonstration."""

import os
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

import pytest
from langgraph.checkpoint.base import BaseCheckpointSaver

from scholarpath import cli
from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
    ProviderConfigurationError,
)
from scholarpath.graph import (
    CandidateApproveResponse,
    CandidateReviewResponse,
    ScholarPathState,
    build_walking_skeleton_fixtures,
    create_initial_state,
    create_test_checkpointer,
    default_review_decision,
    run_scholarpath_graph,
)
from tests.fakes import (
    FakeContentExtraction,
    FakeEvidenceVerificationModel,
    FakeIndependentReviewModel,
    FakePlanningModel,
    FakeResearchFitModel,
    FakeSupervisorSearch,
)


def test_cli_prints_five_ranked_shortlisted_supervisors(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    model = FakePlanningModel()

    def run_offline_graph(
        *,
        planning_model: FakePlanningModel,
        supervisor_search: None,
        tavily_search: None,
        content_extractor: None,
        evidence_model: None,
        research_fit_model: None,
        independent_review_model: None,
        alternate_evidence_search: None,
        thread_id: str,
        candidate_review_responses: tuple[CandidateReviewResponse, ...],
        checkpointer: BaseCheckpointSaver[Any] | None,
    ) -> ScholarPathState:
        assert planning_model is model
        assert supervisor_search is None
        assert tavily_search is None
        assert content_extractor is None
        assert evidence_model is None
        assert research_fit_model is None
        assert independent_review_model is None
        assert alternate_evidence_search is None
        assert thread_id == "legacy-cli-shortlist"
        assert checkpointer is not None
        return cast(
            ScholarPathState,
            run_scholarpath_graph(
                thread_id=thread_id,
                candidate_review_responses=candidate_review_responses,
                checkpointer=checkpointer,
                planning_model=planning_model,
                supervisor_search=FakeSupervisorSearch(),
                content_extractor=FakeContentExtraction(),
                evidence_model=FakeEvidenceVerificationModel(),
                research_fit_model=FakeResearchFitModel(),
                independent_review_model=FakeIndependentReviewModel(),
                application_settings=ApplicationSettings(
                    environment=Environment.TEST,
                    discovery_failure_mode=DiscoveryFailureMode.OFF,
                ),
                langsmith_settings=LangSmithSettings(tracing=False),
            ),
        )

    monkeypatch.setattr(cli, "run_scholarpath_graph", run_offline_graph)

    approval = CandidateApproveResponse(
        action="approve",
        supervisor_ids=default_review_decision().supervisor_ids,
    )
    exit_code = cli.main(
        model,
        thread_id="legacy-cli-shortlist",
        candidate_review_responses=(approval,),
        checkpointer=create_test_checkpointer(),
    )
    captured = capsys.readouterr()
    lines = captured.out.splitlines()

    assert exit_code == 0
    assert lines[0] == "ScholarPath Shortlist: 5 Supervisors"
    assert len(lines) == 6
    assert model.call_count == 1
    assert lines[1].startswith("1. Dr Amara Ndlovu")
    assert lines[5].startswith("5. Dr Theo Laurent")
    assert all("/100" in line for line in lines[1:])


def test_cli_prints_paused_review_payload_and_opaque_thread_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    search = FakeSupervisorSearch()

    exit_code = cli.main(
        FakePlanningModel(),
        supervisor_search=search,
        tavily_search=search,
        content_extractor=FakeContentExtraction(),
        evidence_model=FakeEvidenceVerificationModel(),
        research_fit_model=FakeResearchFitModel(),
        independent_review_model=FakeIndependentReviewModel(),
        alternate_evidence_search=search,
        thread_id="candidate-research-cli-test",
        checkpointer=create_test_checkpointer(),
    )
    captured = capsys.readouterr()

    assert exit_code == 0
    assert captured.out.startswith(
        "ScholarPath paused for Candidate review.\nThread ID: candidate-research-cli-test\n"
    )
    assert '"kind": "candidate_review_required"' in captured.out
    assert '"allowed_actions"' in captured.out
    assert "ScholarPath Shortlist:" not in captured.out


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

    exit_code = cli.main(FakePlanningModel(), checkpointer=create_test_checkpointer())
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

    exit_code = cli.main(FakePlanningModel(), checkpointer=create_test_checkpointer())
    captured = capsys.readouterr()

    assert exit_code == 2
    assert captured.out == (
        "ScholarPath provider configuration error: "
        "Missing API key for provider 'langsmith' while tracing is enabled.\n"
    )
