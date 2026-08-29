"""Provider-neutral contracts for retrieving content from one known web URL."""

from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Protocol, runtime_checkable

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    HttpUrl,
    StrictBool,
    StringConstraints,
    field_validator,
)

NonEmptyContent = Annotated[str, StringConstraints(min_length=1)]


class ExtractedContent(BaseModel):
    """Normalized content retrieved from one exact source URL."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)

    source_url: HttpUrl
    content: NonEmptyContent
    retrieved_at: AwareDatetime
    content_truncated: StrictBool = False

    @field_validator("content")
    @classmethod
    def content_must_not_be_blank(cls, value: str) -> str:
        """Reject whitespace-only pages without altering exact retrieved content."""
        if not value.strip():
            raise ValueError("Extracted content must not be blank")
        return value


@runtime_checkable
class ContentExtractionPort(Protocol):
    """Retrieve normalized content for exactly one known URL."""

    def extract(self, source_url: str | HttpUrl) -> ExtractedContent:
        """Extract one page without applying Supervisor-domain reasoning."""
        ...


class ContentExtractionProvider(StrEnum):
    """External providers available behind the extraction port."""

    TAVILY = "tavily"


class ContentExtractionErrorCategory(StrEnum):
    """Sanitized extraction failures used by deterministic retry routing."""

    TIMEOUT = "timeout"
    TRANSPORT = "transport"
    AUTHENTICATION = "authentication"
    RATE_LIMIT = "rate_limit"
    QUOTA = "quota"
    INVALID_REQUEST = "invalid_request"
    PROVIDER = "provider"
    RESPONSE_CONTRACT = "response_contract"
    EXTRACTION_FAILED = "extraction_failed"


class ContentExtractionError(RuntimeError):
    """Sanitized typed failure raised by a content-extraction adapter."""

    def __init__(
        self,
        message: str,
        *,
        provider: ContentExtractionProvider,
        category: ContentExtractionErrorCategory,
        retryable: bool,
        source_url: str | None = None,
        status_code: int | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.category = category
        self.retryable = retryable
        self.source_url = source_url
        self.status_code = status_code
