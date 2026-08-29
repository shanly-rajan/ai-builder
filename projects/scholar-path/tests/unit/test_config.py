"""Tests for safe settings loading and deferred provider validation."""

import os
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr, ValidationError

from scholarpath.config import (
    ApplicationSettings,
    DiscoveryFailureMode,
    Environment,
    LangSmithSettings,
    LogLevel,
    OpenAIPlanningSettings,
    ProviderConfiguration,
    ProviderConfigurationError,
    TavilySearchConfiguration,
    TavilySearchSettings,
    YouSearchConfiguration,
    YouSearchSettings,
    load_langsmith_settings,
    load_openai_planning_settings,
    load_settings,
    load_tavily_search_settings,
    load_you_search_settings,
)


def isolate_settings_environment(
    monkeypatch: pytest.MonkeyPatch, temporary_directory: Path
) -> None:
    """Remove local environment and dotenv influence from a settings test."""
    monkeypatch.chdir(temporary_directory)
    for variable_name in tuple(os.environ):
        if variable_name.startswith(
            ("SCHOLARPATH_", "OPENAI_", "LANGSMITH_", "YDC_", "YOU_", "TAVILY_")
        ):
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
    assert settings.discovery_failure_mode is DiscoveryFailureMode.OFF
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


def test_you_search_settings_defer_credentials_until_adapter_is_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)

    settings = load_you_search_settings()

    assert settings.api_key is None
    assert str(settings.endpoint) == "https://ydc-index.io/v1/search"
    assert settings.timeout_seconds == 20.0
    assert settings.result_count == 10
    with pytest.raises(ProviderConfigurationError, match="provider 'you.com'"):
        settings.for_search_adapter()


def test_you_search_settings_use_official_credential_and_bounded_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("YDC_API_KEY", "not-a-real-you-secret")
    monkeypatch.setenv("YOU_SEARCH_TIMEOUT_SECONDS", "7.5")
    monkeypatch.setenv("YOU_SEARCH_RESULT_COUNT", "12")

    configuration = load_you_search_settings().for_search_adapter()

    assert configuration.api_key.get_secret_value() == "not-a-real-you-secret"
    assert configuration.timeout_seconds == 7.5
    assert configuration.result_count == 12
    assert "not-a-real-you-secret" not in repr(configuration)


def test_you_search_configuration_rejects_an_unencrypted_endpoint() -> None:
    with pytest.raises(ValidationError, match="must use HTTPS"):
        YouSearchConfiguration.model_validate(
            {
                "api_key": SecretStr("not-a-real-you-secret"),
                "endpoint": "http://ydc-index.io/v1/search",
                "timeout_seconds": 5,
                "result_count": 5,
            }
        )


@pytest.mark.parametrize(
    "values",
    [
        {"timeout_seconds": 0},
        {"result_count": 0},
        {"result_count": 101},
        {"endpoint": "not-a-url"},
    ],
)
def test_you_search_settings_reject_invalid_non_secret_options(
    values: dict[str, object],
) -> None:
    with pytest.raises(ValidationError):
        YouSearchSettings.model_validate(values)


def test_tavily_settings_defer_credentials_until_fallback_is_requested(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)

    settings = load_tavily_search_settings()

    assert settings.api_key is None
    assert settings.timeout_seconds == 20.0
    assert settings.result_count == 10
    with pytest.raises(ProviderConfigurationError, match="provider 'tavily'"):
        settings.for_search_adapter()


def test_tavily_settings_use_official_credential_and_bounded_options(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("TAVILY_API_KEY", "not-a-real-tavily-secret")
    monkeypatch.setenv("TAVILY_SEARCH_TIMEOUT_SECONDS", "8.5")
    monkeypatch.setenv("TAVILY_SEARCH_RESULT_COUNT", "12")

    configuration = load_tavily_search_settings().for_search_adapter()

    assert configuration.api_key.get_secret_value() == "not-a-real-tavily-secret"
    assert configuration.timeout_seconds == 8.5
    assert configuration.result_count == 12
    assert "not-a-real-tavily-secret" not in repr(configuration)


@pytest.mark.parametrize(
    "values",
    [
        {"timeout_seconds": 0},
        {"timeout_seconds": 61},
        {"result_count": 0},
        {"result_count": 21},
    ],
)
def test_tavily_search_settings_reject_invalid_options(values: dict[str, object]) -> None:
    with pytest.raises(ValidationError):
        TavilySearchSettings.model_validate(values)


def test_tavily_configuration_rejects_blank_secret() -> None:
    with pytest.raises(ValidationError, match="Tavily API key must not be blank"):
        TavilySearchConfiguration(
            api_key=SecretStr("   "),
            timeout_seconds=20,
            result_count=10,
        )


def test_failure_injection_mode_is_loaded_deterministically(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)
    monkeypatch.setenv("SCHOLARPATH_DISCOVERY_FAILURE_MODE", "you_timeout_once")

    assert load_settings().discovery_failure_mode is DiscoveryFailureMode.YOU_TIMEOUT_ONCE


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


def test_enabled_langsmith_tracing_defers_missing_key_validation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    isolate_settings_environment(monkeypatch, tmp_path)
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
