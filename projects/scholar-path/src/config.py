"""Typed application and provider settings with deferred credential validation."""

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

    model_config = ConfigDict(
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    provider: str = Field(min_length=1)
    api_key: SecretStr

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject blank secrets at the provider activation boundary."""
        if not value.get_secret_value().strip():
            raise ValueError("API key must not be blank")
        return value


class OpenAIPlanningConfiguration(BaseModel):
    """Validated settings passed only to the OpenAI planning adapter."""

    model_config = ConfigDict(
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: SecretStr
    model: str = Field(min_length=1)
    timeout_seconds: float = Field(gt=0)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject blank OpenAI credentials at adapter activation."""
        if not value.get_secret_value().strip():
            raise ValueError("OpenAI API key must not be blank")
        return value


class OpenAIPlanningSettings(BaseSettings):
    """OpenAI planning settings that remain inert until an adapter is requested."""

    model_config = SettingsConfigDict(
        env_prefix="OPENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: SecretStr | None = Field(default=None, repr=False)
    planning_model: str = "gpt-5.4-mini"
    planning_timeout_seconds: float = Field(default=60.0, gt=0)

    def for_planning_model(self) -> OpenAIPlanningConfiguration:
        """Validate credentials only when the OpenAI planning adapter is requested."""
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Missing API key for provider 'openai'.")
        return OpenAIPlanningConfiguration(
            api_key=self.api_key,
            model=self.planning_model,
            timeout_seconds=self.planning_timeout_seconds,
        )


class LangSmithSettings(BaseSettings):
    """Optional LangSmith settings loaded from the provider's canonical variables."""

    model_config = SettingsConfigDict(
        env_prefix="LANGSMITH_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    tracing: bool = False
    api_key: SecretStr | None = Field(default=None, repr=False)
    project: str = Field(default="scholarpath", min_length=1)

    def require_api_key(self) -> SecretStr:
        """Return a tracing credential only when tracing is explicitly activated."""
        if not self.tracing:
            raise ProviderConfigurationError("LangSmith tracing is not enabled.")
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError(
                "Missing API key for provider 'langsmith' while tracing is enabled."
            )
        return self.api_key


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


def load_openai_planning_settings() -> OpenAIPlanningSettings:
    """Load optional OpenAI settings without requiring credentials."""
    return OpenAIPlanningSettings()


def load_langsmith_settings() -> LangSmithSettings:
    """Load optional LangSmith settings without activating tracing."""
    return LangSmithSettings()
