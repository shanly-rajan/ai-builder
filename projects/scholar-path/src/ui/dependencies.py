"""Replaceable construction boundary for the single ScholarPath UI application."""

from uuid import uuid4

from .service import ScholarPathApplicationPort, create_local_scholarpath_application_service


def create_application_service() -> ScholarPathApplicationPort:
    """Create the production SQLite-backed application service."""
    return create_local_scholarpath_application_service()


def new_thread_id() -> str:
    """Create an opaque identifier for one isolated LangGraph research run."""
    return f"candidate-research-{uuid4().hex}"


def new_candidate_id() -> str:
    """Create an opaque Candidate memory scope until authentication exists."""
    return f"candidate-{uuid4().hex}"
