"""Checkpoint factories for test and trusted local ScholarPath research runs."""

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel

from ..domain import (
    CandidatePreferenceRevision,
    CandidateProfile,
    CandidateReviewDecision,
    ProposedSupervisorShortlist,
    ProspectiveSupervisor,
    ReconciledResearchFitAssessment,
    ResearchFitAssessment,
    SearchPlan,
    SupervisorShortlist,
    SupervisorVerificationRecord,
    VerifiedSupervisor,
)
from ..memory import CandidateMemoryRecord
from .discovery import SearchAttempt
from .state import RawSupervisorSearchResult, ReviewStatus, ToolErrorRecord
from .verification import AlternateSourceAttempt, EvidenceExtractionAttempt, EvidenceSourceReference

_MODEL_TYPE_FIELD = "__scholarpath_checkpoint_model__"
_ENUM_TYPE_FIELD = "__scholarpath_checkpoint_enum__"
_VALUE_FIELD = "value"

_CHECKPOINT_MODEL_TYPES: tuple[type[BaseModel], ...] = (
    CandidateProfile,
    CandidatePreferenceRevision,
    CandidateMemoryRecord,
    SearchPlan,
    ProspectiveSupervisor,
    VerifiedSupervisor,
    SupervisorVerificationRecord,
    ResearchFitAssessment,
    ReconciledResearchFitAssessment,
    ProposedSupervisorShortlist,
    CandidateReviewDecision,
    SupervisorShortlist,
    SearchAttempt,
    RawSupervisorSearchResult,
    ToolErrorRecord,
    EvidenceExtractionAttempt,
    AlternateSourceAttempt,
    EvidenceSourceReference,
)
_CHECKPOINT_MODELS = {
    f"{model_type.__module__}:{model_type.__name__}": model_type
    for model_type in _CHECKPOINT_MODEL_TYPES
}
_REVIEW_STATUS_TYPE = f"{ReviewStatus.__module__}:{ReviewStatus.__name__}"


def _model_type_key(value: BaseModel) -> str:
    return f"{value.__class__.__module__}:{value.__class__.__name__}"


def _prepare_checkpoint_value(value: Any) -> Any:
    """Project application types into safe data before MessagePack serialization."""
    if isinstance(value, BaseModel):
        model_type = _model_type_key(value)
        if model_type not in _CHECKPOINT_MODELS:
            raise TypeError(f"Checkpoint model type is not registered: {model_type}")
        return {
            _MODEL_TYPE_FIELD: model_type,
            _VALUE_FIELD: value.model_dump(mode="json"),
        }
    if isinstance(value, ReviewStatus):
        return {
            _ENUM_TYPE_FIELD: _REVIEW_STATUS_TYPE,
            _VALUE_FIELD: value.value,
        }
    if isinstance(value, dict):
        return {key: _prepare_checkpoint_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_prepare_checkpoint_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_prepare_checkpoint_value(item) for item in value)
    return value


def _restore_checkpoint_value(value: Any) -> Any:
    """Restore only explicitly registered ScholarPath types from checkpoint data."""
    if isinstance(value, dict):
        if set(value) == {_MODEL_TYPE_FIELD, _VALUE_FIELD}:
            model_type = value[_MODEL_TYPE_FIELD]
            if not isinstance(model_type, str) or model_type not in _CHECKPOINT_MODELS:
                raise TypeError("Checkpoint references an unregistered ScholarPath model")
            return _CHECKPOINT_MODELS[model_type].model_validate(value[_VALUE_FIELD])
        if set(value) == {_ENUM_TYPE_FIELD, _VALUE_FIELD}:
            if value[_ENUM_TYPE_FIELD] != _REVIEW_STATUS_TYPE:
                raise TypeError("Checkpoint references an unregistered ScholarPath enum")
            return ReviewStatus(value[_VALUE_FIELD])
        return {key: _restore_checkpoint_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_restore_checkpoint_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_restore_checkpoint_value(item) for item in value)
    return value


class _ScholarPathCheckpointSerializer(JsonPlusSerializer):
    """Strict MessagePack serializer for the finite set of persisted app contracts."""

    def __init__(self) -> None:
        super().__init__(allowed_msgpack_modules=None)

    def dumps_typed(self, obj: Any) -> tuple[str, bytes]:
        """Serialize checkpoint values without enabling unsafe pickle fallback."""
        return super().dumps_typed(_prepare_checkpoint_value(obj))

    def loads_typed(self, data: tuple[str, bytes]) -> Any:
        """Validate restored application models through the finite type registry."""
        return _restore_checkpoint_value(super().loads_typed(data))


def _checkpoint_serializer() -> JsonPlusSerializer:
    """Support Pydantic URL types within trusted ScholarPath checkpoint state."""
    return _ScholarPathCheckpointSerializer()


def create_test_checkpointer() -> InMemorySaver:
    """Return an isolated in-memory saver for deterministic unit and graph tests."""
    return InMemorySaver(serde=_checkpoint_serializer())


@contextmanager
def open_local_sqlite_checkpointer(database_path: str | Path) -> Iterator[SqliteSaver]:
    """Open a restart-safe SQLite saver for one trusted local development process."""
    resolved_path = Path(database_path).expanduser()
    if resolved_path.exists() and resolved_path.is_dir():
        raise ValueError("SQLite checkpoint path must identify a file, not a directory")
    resolved_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(resolved_path), check_same_thread=False)
    try:
        checkpointer = SqliteSaver(connection, serde=_checkpoint_serializer())
        yield checkpointer
    finally:
        connection.close()
