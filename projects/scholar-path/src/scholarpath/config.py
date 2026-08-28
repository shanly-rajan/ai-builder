"""Typed application settings with deferred provider credential validation."""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Supported ScholarPath runtime environments."""

    DEVELOPMENT = "development"
    TEST = "test"
    PRODUCTION = "production"


class LogLevel(StrEnum):
    """Supported application log levels."""

    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class ProviderConfigurationError(ValueError):
    """Raised when a requested provider lacks valid credentials."""


class ProviderConfiguration(BaseModel):
    """Validated credentials passed to a future provider adapter."""

    model_config = ConfigDict(frozen=True, hide_input_in_errors=True)

    provider: str = Field(min_length=1)
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject blank secrets at the provider activation boundary."""
        if not value.get_secret_value().strip():
            raise ValueError("API key must not be blank")
        return value


class ApplicationSettings(BaseSettings):
    """Non-secret defaults plus optional, lazily validated provider credentials."""

    model_config = SettingsConfigDict(
        env_prefix="SCHOLARPATH_",
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_name: str = "ScholarPath"
    environment: Environment = Environment.DEVELOPMENT
    log_level: LogLevel = LogLevel.INFO
    provider_api_keys: dict[str, SecretStr] = Field(default_factory=dict, repr=False)

    def for_provider(self, provider: str) -> ProviderConfiguration:
        """Return validated credentials only when a provider is explicitly requested."""
        normalized_provider = provider.strip().casefold()
        if not normalized_provider:
            raise ProviderConfigurationError("Provider name must not be blank.")

        normalized_keys = {
            name.strip().casefold(): api_key for name, api_key in self.provider_api_keys.items()
        }
        api_key = normalized_keys.get(normalized_provider)
        if api_key is None or not api_key.get_secret_value().strip():
            raise ProviderConfigurationError(
                f"Missing API key for provider '{normalized_provider}'."
            )

        return ProviderConfiguration(provider=normalized_provider, api_key=api_key)


def load_settings() -> ApplicationSettings:
    """Load settings without constructing or validating any provider integration."""
    return ApplicationSettings()
