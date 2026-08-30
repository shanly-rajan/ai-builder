"""Unit contracts for selecting and constructing the M13.2 runtime profiles."""

from typing import cast

import pytest
from langgraph.checkpoint.memory import InMemorySaver

import scholarpath.ui.dependencies as ui_dependencies
import scholarpath.ui.service as ui_service
from scholarpath.config import (
    ApplicationSettings,
    Environment,
    LangSmithSettings,
    RuntimeProfile,
)
from scholarpath.evaluation.fakes import (
    InMemoryCandidatePreferenceMemory,
    ScriptedContentExtraction,
    ScriptedEvidenceModel,
    ScriptedIndependentReviewModel,
    ScriptedResearchFitModel,
    ScriptedSupervisorSearch,
    StaticPlanningModel,
)
from scholarpath.graph import GraphFixtureConfig, ScholarPathRuntime
from scholarpath.ui import ScholarPathApplicationService


def test_demo_factory_injects_only_offline_ports_and_forces_tracing_off(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    runtime_sentinel = cast(ScholarPathRuntime, object())

    def capture_runtime(
        config: GraphFixtureConfig | None = None,
        **kwargs: object,
    ) -> ScholarPathRuntime:
        captured["config"] = config
        captured.update(kwargs)
        return runtime_sentinel

    monkeypatch.setattr(ui_service, "build_scholarpath_runtime", capture_runtime)
    settings = ApplicationSettings(
        environment=Environment.TEST,
        runtime_profile=RuntimeProfile.DETERMINISTIC_DEMO,
    )

    service = ui_service.create_deterministic_demo_application_service(settings)

    assert isinstance(service, ScholarPathApplicationService)
    assert isinstance(captured["config"], GraphFixtureConfig)
    assert isinstance(captured["checkpointer"], InMemorySaver)
    assert isinstance(captured["planning_model"], StaticPlanningModel)
    assert isinstance(captured["supervisor_search"], ScriptedSupervisorSearch)
    assert isinstance(captured["tavily_search"], ScriptedSupervisorSearch)
    assert isinstance(captured["content_extractor"], ScriptedContentExtraction)
    assert isinstance(captured["evidence_model"], ScriptedEvidenceModel)
    assert isinstance(captured["research_fit_model"], ScriptedResearchFitModel)
    assert isinstance(captured["independent_review_model"], ScriptedIndependentReviewModel)
    assert isinstance(
        captured["candidate_preference_memory"],
        InMemoryCandidatePreferenceMemory,
    )
    tracing = cast(LangSmithSettings, captured["langsmith_settings"])
    assert tracing.tracing is False
    assert captured["application_settings"] is settings


def test_demo_factory_requires_explicit_demo_profile() -> None:
    with pytest.raises(ValueError, match="requires the deterministic_demo runtime profile"):
        ui_service.create_deterministic_demo_application_service(
            ApplicationSettings(environment=Environment.TEST)
        )


def test_ui_dependency_defaults_to_live_service(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApplicationSettings(environment=Environment.TEST)
    sentinel = cast(ScholarPathApplicationService, object())
    local_calls: list[ApplicationSettings] = []

    def create_local(resolved: ApplicationSettings | None = None) -> ScholarPathApplicationService:
        assert resolved is not None
        local_calls.append(resolved)
        return sentinel

    def reject_demo(
        resolved: ApplicationSettings | None = None,
    ) -> ScholarPathApplicationService:
        del resolved
        raise AssertionError("Default live composition must not construct demo adapters")

    monkeypatch.setattr(ui_dependencies, "load_settings", lambda: settings)
    monkeypatch.setattr(
        ui_dependencies, "create_local_scholarpath_application_service", create_local
    )
    monkeypatch.setattr(
        ui_dependencies,
        "create_deterministic_demo_application_service",
        reject_demo,
    )

    assert ui_dependencies.create_application_service() is sentinel
    assert local_calls == [settings]
    assert ui_dependencies.is_deterministic_demo() is False


def test_ui_dependency_selects_demo_service_only_when_explicit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = ApplicationSettings(
        environment=Environment.TEST,
        runtime_profile=RuntimeProfile.DETERMINISTIC_DEMO,
    )
    sentinel = cast(ScholarPathApplicationService, object())
    demo_calls: list[ApplicationSettings] = []

    def create_demo(resolved: ApplicationSettings | None = None) -> ScholarPathApplicationService:
        assert resolved is not None
        demo_calls.append(resolved)
        return sentinel

    def reject_local(
        resolved: ApplicationSettings | None = None,
    ) -> ScholarPathApplicationService:
        del resolved
        raise AssertionError("Demo composition must not construct live adapters")

    monkeypatch.setattr(ui_dependencies, "load_settings", lambda: settings)
    monkeypatch.setattr(
        ui_dependencies, "create_deterministic_demo_application_service", create_demo
    )
    monkeypatch.setattr(
        ui_dependencies, "create_local_scholarpath_application_service", reject_local
    )

    assert ui_dependencies.create_application_service() is sentinel
    assert demo_calls == [settings]
    assert ui_dependencies.is_deterministic_demo() is True
