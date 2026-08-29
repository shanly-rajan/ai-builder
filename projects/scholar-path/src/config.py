"""Typed application and provider settings with deferred credential validation."""

from enum import StrEnum
from typing import Annotated, Literal, Self

from pydantic import (
    AliasChoices,
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    SecretStr,
    field_validator,
    model_validator,
)
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


class DiscoveryFailureMode(StrEnum):
    """Deterministic provider failures available for local routing demonstrations."""

    OFF = "off"
    YOU_TIMEOUT_ONCE = "you_timeout_once"
    YOU_RETRYABLE_ERROR = "you_retryable_error"
    BOTH_PROVIDERS_RETRYABLE_ERROR = "both_providers_retryable_error"


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

    api_key: Annotated[SecretStr | None, Field(repr=False)] = None
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


class OpenAIEvidenceConfiguration(BaseModel):
    """Validated settings passed only to the OpenAI evidence adapter."""

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
        """Reject blank OpenAI credentials at evidence-adapter activation."""
        if not value.get_secret_value().strip():
            raise ValueError("OpenAI API key must not be blank")
        return value


class OpenAIEvidenceSettings(BaseSettings):
    """OpenAI evidence settings that remain inert until verification is requested."""

    model_config = SettingsConfigDict(
        env_prefix="OPENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: Annotated[SecretStr | None, Field(repr=False)] = None
    evidence_model: str = "gpt-5.4-mini"
    evidence_timeout_seconds: float = Field(default=60.0, gt=0)

    def for_evidence_model(self) -> OpenAIEvidenceConfiguration:
        """Validate credentials only when the evidence model is requested."""
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Missing API key for provider 'openai'.")
        return OpenAIEvidenceConfiguration(
            api_key=self.api_key,
            model=self.evidence_model,
            timeout_seconds=self.evidence_timeout_seconds,
        )


class OpenAIResearchFitConfiguration(BaseModel):
    """Validated settings passed only to the OpenAI Research Fit adapter."""

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
        """Reject blank OpenAI credentials at Research Fit adapter activation."""
        if not value.get_secret_value().strip():
            raise ValueError("OpenAI API key must not be blank")
        return value


class OpenAIResearchFitSettings(BaseSettings):
    """OpenAI Research Fit settings that remain inert until evaluation is requested."""

    model_config = SettingsConfigDict(
        env_prefix="OPENAI_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: Annotated[SecretStr | None, Field(repr=False)] = None
    research_fit_model: str = "gpt-5.4-mini"
    research_fit_timeout_seconds: float = Field(default=60.0, gt=0)

    def for_research_fit_model(self) -> OpenAIResearchFitConfiguration:
        """Validate credentials only when the Research Fit adapter is requested."""
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Missing API key for provider 'openai'.")
        return OpenAIResearchFitConfiguration(
            api_key=self.api_key,
            model=self.research_fit_model,
            timeout_seconds=self.research_fit_timeout_seconds,
        )


class NebiusReviewConfiguration(BaseModel):
    """Validated settings passed only to the Nebius independent-review adapter."""

    model_config = ConfigDict(
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: SecretStr
    model: str = Field(min_length=1)
    endpoint: HttpUrl
    timeout_seconds: float = Field(gt=0)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject blank Nebius credentials at independent-review activation."""
        if not value.get_secret_value().strip():
            raise ValueError("Nebius API key must not be blank")
        return value

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_use_https(cls, value: HttpUrl) -> HttpUrl:
        """Prevent a Nebius credential from being sent over an insecure connection."""
        if value.scheme != "https":
            raise ValueError("Nebius endpoint must use HTTPS")
        return value


class NebiusReviewSettings(BaseSettings):
    """Nebius settings that remain inert until independent review is requested."""

    model_config = SettingsConfigDict(
        env_prefix="NEBIUS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: Annotated[SecretStr | None, Field(repr=False)] = None
    review_model: str = "Qwen/Qwen3-235B-A22B"
    endpoint: HttpUrl = HttpUrl("https://api.tokenfactory.nebius.com/v1/")
    review_timeout_seconds: float = Field(default=60.0, gt=0)

    def for_review_model(self) -> NebiusReviewConfiguration:
        """Validate credentials only when the Nebius reviewer is requested."""
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Missing API key for provider 'nebius'.")
        return NebiusReviewConfiguration(
            api_key=self.api_key,
            model=self.review_model,
            endpoint=self.endpoint,
            timeout_seconds=self.review_timeout_seconds,
        )


class YouSearchConfiguration(BaseModel):
    """Validated settings passed only to the You.com Web Search adapter."""

    model_config = ConfigDict(
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: SecretStr
    endpoint: HttpUrl
    timeout_seconds: float = Field(gt=0)
    result_count: int = Field(ge=1, le=100)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject blank You.com credentials at adapter activation."""
        if not value.get_secret_value().strip():
            raise ValueError("You.com API key must not be blank")
        return value

    @field_validator("endpoint")
    @classmethod
    def endpoint_must_use_https(cls, value: HttpUrl) -> HttpUrl:
        """Prevent an API key from being sent over an unencrypted connection."""
        if value.scheme != "https":
            raise ValueError("You.com search endpoint must use HTTPS")
        return value


class YouSearchSettings(BaseSettings):
    """You.com settings that remain inert until the search adapter is requested."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    api_key: Annotated[
        SecretStr | None,
        Field(
            repr=False,
            validation_alias=AliasChoices("YDC_API_KEY", "YOU_API_KEY"),
        ),
    ] = None
    endpoint: HttpUrl = Field(
        default=HttpUrl("https://ydc-index.io/v1/search"),
        validation_alias="YOU_SEARCH_ENDPOINT",
    )
    timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        validation_alias="YOU_SEARCH_TIMEOUT_SECONDS",
    )
    result_count: int = Field(
        default=10,
        ge=1,
        le=100,
        validation_alias="YOU_SEARCH_RESULT_COUNT",
    )

    def for_search_adapter(self) -> YouSearchConfiguration:
        """Validate credentials only when the You.com adapter is requested."""
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Missing API key for provider 'you.com'.")
        return YouSearchConfiguration(
            api_key=self.api_key,
            endpoint=self.endpoint,
            timeout_seconds=self.timeout_seconds,
            result_count=self.result_count,
        )


class TavilySearchConfiguration(BaseModel):
    """Validated settings passed only to the official Tavily search adapter."""

    model_config = ConfigDict(
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: SecretStr
    timeout_seconds: float = Field(gt=0, le=60)
    result_count: int = Field(ge=1, le=20)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject blank Tavily credentials at adapter activation."""
        if not value.get_secret_value().strip():
            raise ValueError("Tavily API key must not be blank")
        return value


class TavilySearchSettings(BaseSettings):
    """Tavily settings that remain inert until fallback search is requested."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    api_key: Annotated[
        SecretStr | None,
        Field(repr=False, validation_alias="TAVILY_API_KEY"),
    ] = None
    timeout_seconds: float = Field(
        default=20.0,
        gt=0,
        le=60,
        validation_alias="TAVILY_SEARCH_TIMEOUT_SECONDS",
    )
    result_count: int = Field(
        default=10,
        ge=1,
        le=20,
        validation_alias="TAVILY_SEARCH_RESULT_COUNT",
    )

    def for_search_adapter(self) -> TavilySearchConfiguration:
        """Validate credentials only when the Tavily fallback is requested."""
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Missing API key for provider 'tavily'.")
        return TavilySearchConfiguration(
            api_key=self.api_key,
            timeout_seconds=self.timeout_seconds,
            result_count=self.result_count,
        )


class TavilyExtractionConfiguration(BaseModel):
    """Validated settings passed only to the official Tavily Extract adapter."""

    model_config = ConfigDict(
        frozen=True,
        hide_input_in_errors=True,
        str_strip_whitespace=True,
    )

    api_key: SecretStr
    provider_timeout_seconds: int = Field(ge=1, le=60)
    request_timeout_seconds: float = Field(gt=0, le=90)
    extract_depth: Literal["basic", "advanced"] = "advanced"
    max_content_characters: int = Field(ge=1_000, le=200_000)

    @field_validator("api_key")
    @classmethod
    def api_key_must_not_be_blank(cls, value: SecretStr) -> SecretStr:
        """Reject blank Tavily credentials at extraction-adapter activation."""
        if not value.get_secret_value().strip():
            raise ValueError("Tavily API key must not be blank")
        return value

    @model_validator(mode="after")
    def request_deadline_must_exceed_provider_timeout(self) -> Self:
        """Leave time for Tavily to return its provider-side timeout result."""
        if self.request_timeout_seconds <= self.provider_timeout_seconds:
            raise ValueError("Tavily Extract request timeout must exceed provider timeout")
        return self


class TavilyExtractionSettings(BaseSettings):
    """Tavily Extract settings that remain inert until evidence retrieval begins."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    api_key: Annotated[
        SecretStr | None,
        Field(repr=False, validation_alias="TAVILY_API_KEY"),
    ] = None
    provider_timeout_seconds: int = Field(
        default=20,
        ge=1,
        le=60,
        validation_alias="TAVILY_EXTRACT_PROVIDER_TIMEOUT_SECONDS",
    )
    request_timeout_seconds: float = Field(
        default=25.0,
        gt=0,
        le=90,
        validation_alias="TAVILY_EXTRACT_REQUEST_TIMEOUT_SECONDS",
    )
    extract_depth: Literal["basic", "advanced"] = Field(
        default="advanced",
        validation_alias="TAVILY_EXTRACT_DEPTH",
    )
    max_content_characters: int = Field(
        default=50_000,
        ge=1_000,
        le=200_000,
        validation_alias="TAVILY_EXTRACT_MAX_CONTENT_CHARACTERS",
    )

    def for_extraction_adapter(self) -> TavilyExtractionConfiguration:
        """Validate credentials only when Tavily Extract is requested."""
        if self.api_key is None or not self.api_key.get_secret_value().strip():
            raise ProviderConfigurationError("Missing API key for provider 'tavily'.")
        return TavilyExtractionConfiguration(
            api_key=self.api_key,
            provider_timeout_seconds=self.provider_timeout_seconds,
            request_timeout_seconds=self.request_timeout_seconds,
            extract_depth=self.extract_depth,
            max_content_characters=self.max_content_characters,
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
    api_key: Annotated[SecretStr | None, Field(repr=False)] = None
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
    discovery_failure_mode: DiscoveryFailureMode = DiscoveryFailureMode.OFF
    provider_api_keys: dict[str, SecretStr] = Field(default_factory=dict, repr=False)

    def for_provider(self, provider: str) -> ProviderConfiguration:
        """Return validated credentials only when a provider is explicitly requested."""
        normalized_provider = provider.strip().casefold()
        if not normalized_provider:
            raise ProviderConfigurationError("Provider name must not be blank.")

        # Pylint does not apply Pydantic's runtime field transform to this descriptor.
        provider_items = self.provider_api_keys.items()  # pylint: disable=no-member
        normalized_keys = {name.strip().casefold(): api_key for name, api_key in provider_items}
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


def load_openai_evidence_settings() -> OpenAIEvidenceSettings:
    """Load optional OpenAI evidence settings without requiring credentials."""
    return OpenAIEvidenceSettings()


def load_openai_research_fit_settings() -> OpenAIResearchFitSettings:
    """Load optional OpenAI Research Fit settings without requiring credentials."""
    return OpenAIResearchFitSettings()


def load_nebius_review_settings() -> NebiusReviewSettings:
    """Load optional Nebius review settings without requiring credentials."""
    return NebiusReviewSettings()


def load_you_search_settings() -> YouSearchSettings:
    """Load optional You.com settings without requiring credentials."""
    return YouSearchSettings()


def load_tavily_search_settings() -> TavilySearchSettings:
    """Load optional Tavily settings without requiring credentials."""
    return TavilySearchSettings()


def load_tavily_extraction_settings() -> TavilyExtractionSettings:
    """Load optional Tavily Extract settings without requiring credentials."""
    return TavilyExtractionSettings()


def load_langsmith_settings() -> LangSmithSettings:
    """Load optional LangSmith settings without activating tracing."""
    return LangSmithSettings()
