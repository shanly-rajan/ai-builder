"""Hosted Mem0 adapter for exact, Candidate-scoped durable preferences."""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any, Protocol, cast

import httpx
from pydantic import ValidationError

from ..config import Mem0MemoryConfiguration
from .models import CandidateMemoryRecord, deduplicate_candidate_memories
from .ports import CandidatePreferenceMemoryError

MEMORY_SCHEMA = "scholarpath.candidate-preference.v1"


class _Mem0ClientPort(Protocol):
    """Narrow subset of the official SDK used by the adapter."""

    def get_all(self, **kwargs: object) -> dict[str, Any]: ...

    def add(self, messages: object, **kwargs: object) -> dict[str, Any]: ...


def _validated_candidate_id(candidate_id: str) -> str:
    normalized = candidate_id.strip()
    if not normalized:
        raise ValueError("candidate_id must not be empty")
    return normalized


class Mem0CandidatePreferenceAdapter:
    """Persist exact Pydantic records through the current official Mem0 SDK."""

    def __init__(
        self,
        configuration: Mem0MemoryConfiguration,
        *,
        client: _Mem0ClientPort | None = None,
    ) -> None:
        self._configuration = configuration
        self._owned_http_client: httpx.Client | None = None
        if client is not None:
            self._client = client
            return

        os.environ["MEM0_TELEMETRY"] = "true" if configuration.telemetry else "false"
        try:
            from mem0 import MemoryClient

            self._owned_http_client = httpx.Client(timeout=configuration.timeout_seconds)
            self._client = cast(
                _Mem0ClientPort,
                MemoryClient(
                    api_key=configuration.api_key.get_secret_value(),
                    client=self._owned_http_client,
                ),
            )
        except Exception as error:
            if self._owned_http_client is not None:
                self._owned_http_client.close()
            raise CandidatePreferenceMemoryError("initialization") from error

    def load(self, candidate_id: str) -> tuple[CandidateMemoryRecord, ...]:
        """Load only ScholarPath records using Mem0's required user filter."""
        scoped_candidate_id = _validated_candidate_id(candidate_id)
        try:
            response = self._client.get_all(
                filters={"user_id": scoped_candidate_id},
                page=1,
                page_size=self._configuration.memory_limit,
            )
            raw_results = response.get("results")
            if not isinstance(raw_results, list):
                raise ValueError("Mem0 returned an invalid get-all envelope")
            records = [
                record
                for item in raw_results
                if (record := self._record_from_result(item)) is not None
            ]
            return deduplicate_candidate_memories(records)
        except Exception as error:
            raise CandidatePreferenceMemoryError("load") from error

    def store(
        self,
        candidate_id: str,
        records: tuple[CandidateMemoryRecord, ...],
    ) -> tuple[CandidateMemoryRecord, ...]:
        """Skip existing semantic keys, then direct-import each exact typed record."""
        scoped_candidate_id = _validated_candidate_id(candidate_id)
        deduplicated = deduplicate_candidate_memories(records)
        if not deduplicated:
            return ()
        try:
            existing_ids = {record.memory_id for record in self.load(scoped_candidate_id)}
            stored: list[CandidateMemoryRecord] = []
            for record in deduplicated:
                if record.memory_id in existing_ids:
                    continue
                response = self._client.add(
                    [{"role": "user", "content": record.model_dump_json()}],
                    user_id=scoped_candidate_id,
                    infer=False,
                    metadata={
                        "schema": MEMORY_SCHEMA,
                        "memory_kind": record.kind.value,
                        "record_key": record.memory_id,
                        "source_action": record.source_action.value,
                    },
                )
                if not isinstance(response, Mapping):
                    raise ValueError("Mem0 returned an invalid add envelope")
                if str(response.get("status", "")).upper() == "FAILED":
                    raise ValueError("Mem0 rejected a Candidate preference memory")
                stored.append(record)
                existing_ids.add(record.memory_id)
            return tuple(stored)
        except CandidatePreferenceMemoryError:
            raise
        except Exception as error:
            raise CandidatePreferenceMemoryError("store") from error

    @staticmethod
    def _record_from_result(item: object) -> CandidateMemoryRecord | None:
        if not isinstance(item, Mapping):
            return None
        metadata = item.get("metadata")
        if not isinstance(metadata, Mapping) or metadata.get("schema") != MEMORY_SCHEMA:
            return None
        content = item.get("memory", item.get("text"))
        if not isinstance(content, str):
            return None
        try:
            record = CandidateMemoryRecord.model_validate_json(content)
        except ValidationError:
            return None
        if metadata.get("record_key") != record.memory_id:
            return None
        return record

    def close(self) -> None:
        """Release the owned HTTP connection pool when the caller controls lifecycle."""
        if self._owned_http_client is not None:
            self._owned_http_client.close()
