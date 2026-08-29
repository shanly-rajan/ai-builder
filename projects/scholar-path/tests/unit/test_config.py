"""Tests for safe settings loading and deferred provider validation."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from scholarpath.config import (
    ApplicationSettings,
    Environment,
    LangSmithSettings,
    LogLevel,
    OpenAIPlanningSettings,
    ProviderConfiguration,
    ProviderConfigurationError,
    load_langsmith_settings,
    load_openai_planning_settings,
    load_settings,
)


def isolate_settings_environment(
    monkeypatch: pytest.MonkeyPatch, temporary_directory: Path
) -> None:
    """Remove local environment and dotenv influence from a settings test."""
    monkeypatch.chdir(temporary_directory)
    for variable_name in tuple(os.environ):
        if variable_name.startswith(("SCHOLARPATH_", "OPENAI_", "LANGSMITH_")):
            monkeypatch.delenv(variable_name, raising=False)


def test_importing_package_does_not_require_api_keys(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)

    result = subprocess.run(
        [sys.executable, "-c", "import scholarpath; print(scholarpath.__version__)"],
        cwd=tmp_path,
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "0.1.0"


def test_settings_load_non_secret_defaults(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)

    settings = load_settings()

    assert settings.app_name == "ScholarPath"
    assert settings.environment is Environment.DEVELOPMENT
    assert settings.log_level is LogLevel.INFO
    assert settings.provider_api_keys == {}


def test_missing_credentials_are_rejected_only_when_provider_is_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)

    settings = load_settings()

    with pytest.raises(ProviderConfigurationError, match="Missing API key"):
        settings.for_provider("example-provider")


def test_blank_credentials_are_rejected_only_when_provider_is_requested() -> None:
    settings = ApplicationSettings(provider_api_keys={"example-provider": SecretStr("   ")})

    with pytest.raises(ProviderConfigurationError, match="Missing API key"):
        settings.for_provider("example-provider")


def test_blank_provider_name_is_rejected_at_provider_boundary() -> None:
    settings = ApplicationSettings()

    with pytest.raises(ProviderConfigurationError, match="Provider name"):
        settings.for_provider("   ")


def test_configured_provider_returns_masked_typed_credentials() -> None:
    raw_secret = "not-a-real-secret"
    settings = ApplicationSettings(provider_api_keys={"Example-Provider": SecretStr(raw_secret)})

    provider = settings.for_provider(" example-provider ")

    assert provider.provider == "example-provider"
    assert provider.api_key.get_secret_value() == raw_secret
    assert raw_secret not in repr(provider)
    assert raw_secret not in str(provider)


def test_nested_environment_key_is_validated_only_when_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("SCHOLARPATH_PROVIDER_API_KEYS__EXAMPLE", "environment-secret")

    settings = load_settings()
    provider = settings.for_provider("example")

    assert provider.api_key.get_secret_value() == "environment-secret"


def test_typed_provider_configuration_rejects_blank_secret() -> None:
    with pytest.raises(ValidationError, match="API key must not be blank"):
        ProviderConfiguration(provider="example-provider", api_key=SecretStr("   "))


def test_openai_settings_do_not_require_a_key_until_planning_is_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)

    settings = load_openai_planning_settings()

    assert settings.api_key is None
    with pytest.raises(ProviderConfigurationError, match="provider 'openai'"):
        settings.for_planning_model()


def test_langsmith_defaults_to_disabled_without_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)

    settings = load_langsmith_settings()

    assert settings.tracing is False
    assert settings.api_key is None
    assert settings.project == "scholarpath"


def test_langsmith_uses_canonical_environment_variables(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "not-a-real-langsmith-secret")
    monkeypatch.setenv("LANGSMITH_PROJECT", "scholarpath-m3-tests")

    settings = load_langsmith_settings()

    assert settings.tracing is True
    assert settings.require_api_key().get_secret_value() == "not-a-real-langsmith-secret"
    assert settings.project == "scholarpath-m3-tests"
    assert "not-a-real-langsmith-secret" not in repr(settings)


def test_enabled_langsmith_tracing_defers_missing_key_validation() -> None:
    settings = LangSmithSettings(tracing=True)

    with pytest.raises(ProviderConfigurationError, match="provider 'langsmith'"):
        settings.require_api_key()


def test_openai_settings_return_masked_typed_planning_configuration() -> None:
    raw_api_key = "not-a-real-openai-secret"
    settings = OpenAIPlanningSettings(api_key=SecretStr(raw_api_key))

    configuration = settings.for_planning_model()

    assert configuration.api_key.get_secret_value() == raw_api_key
    assert configuration.model == settings.planning_model
    assert raw_api_key not in repr(configuration)


def test_provider_names_and_projects_reject_whitespace_only_values() -> None:
    with pytest.raises(ValidationError, match="at least 1 character"):
        OpenAIPlanningSettings(
            api_key=SecretStr("not-a-real-openai-secret"),
            planning_model="   ",
        ).for_planning_model()

    with pytest.raises(ValidationError, match="at least 1 character"):
        LangSmithSettings(project="   ")
