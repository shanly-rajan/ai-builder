"""Replaceable construction boundary for the single ScholarPath UI application."""

from uuid import uuid4

from ..config import ApplicationSettings, RuntimeProfile, load_settings
from .service import (
    ScholarPathApplicationPort,
    create_deterministic_demo_application_service,
    create_local_scholarpath_application_service,
)


def configured_application_settings() -> ApplicationSettings:
    """Resolve immutable process composition settings without activating a provider."""
    return load_settings()


def create_application_service(
    settings: ApplicationSettings | None = None,
) -> ScholarPathApplicationPort:
    """Select exactly one typed application composition at the outer UI boundary."""
    resolved_settings = settings or configured_application_settings()
    if resolved_settings.runtime_profile is RuntimeProfile.DETERMINISTIC_DEMO:
        return create_deterministic_demo_application_service(resolved_settings)
    return create_local_scholarpath_application_service(resolved_settings)


def is_deterministic_demo(settings: ApplicationSettings | None = None) -> bool:
    """Return whether the configured UI composition uses only synthetic offline ports."""
    resolved_settings = settings or configured_application_settings()
    return resolved_settings.runtime_profile is RuntimeProfile.DETERMINISTIC_DEMO


def new_thread_id() -> str:
    """Create an opaque identifier for one isolated LangGraph research run."""
    return f"candidate-research-{uuid4().hex}"


def new_candidate_id() -> str:
    """Create an opaque Candidate memory scope until authentication exists."""
    return f"candidate-{uuid4().hex}"
