"""Explicitly opted-in live smoke test for hosted Mem0 preference memory."""

import os
import time
from datetime import UTC, datetime
from importlib import import_module
from typing import Any
from uuid import uuid4

import httpx
import pytest
from pydantic import SecretStr

from scholarpath.config import Mem0MemoryConfiguration
from scholarpath.memory import (
    CandidateMemoryKind,
    CandidateMemorySourceAction,
    Mem0CandidatePreferenceAdapter,
    make_candidate_memory_record,
)


def _live_tests_enabled() -> bool:
    return os.getenv("SCHOLARPATH_RUN_LIVE_TESTS", "").strip().casefold() in {
        "1",
        "true",
        "yes",
    }


@pytest.mark.live
def test_live_mem0_candidate_scoped_round_trip_and_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Write synthetic memory, verify isolation, and delete only the UUID test scope."""
    if not _live_tests_enabled():
        pytest.skip("Set SCHOLARPATH_RUN_LIVE_TESTS=true to opt in to live tests")
    raw_api_key = os.getenv("MEM0_API_KEY", "").strip()
    if not raw_api_key:
        pytest.skip("MEM0_API_KEY is required for the live Candidate-memory smoke test")

    monkeypatch.setenv("MEM0_TELEMETRY", "false")
    try:
        mem0_module: Any = import_module("mem0")
    except ModuleNotFoundError:
        pytest.skip("Install the pinned mem0ai dependency to run the live smoke test")

    candidate_id = f"scholarpath-live-{uuid4().hex}"
    other_candidate_id = f"scholarpath-live-other-{uuid4().hex}"
    http_client = httpx.Client(timeout=20)
    try:
        client: Any = mem0_module.MemoryClient(api_key=raw_api_key, client=http_client)
    except Exception:
        http_client.close()
        raise
    adapter = Mem0CandidatePreferenceAdapter(
        Mem0MemoryConfiguration(
            api_key=SecretStr(raw_api_key),
            timeout_seconds=20,
            memory_limit=25,
            telemetry=False,
        ),
        client=client,
    )
    record = make_candidate_memory_record(
        CandidateMemoryKind.PREFERRED_RESEARCH_THEME,
        "synthetic resilient systems research",
        CandidateMemorySourceAction.DIRECT_PREFERENCE_SUBMISSION,
        datetime.now(UTC),
    )

    try:
        stored = adapter.store(candidate_id, (record,))
        assert stored in {(record,), ()}

        deadline = time.monotonic() + 20
        loaded = adapter.load(candidate_id)
        while record not in loaded and time.monotonic() < deadline:
            time.sleep(1)
            loaded = adapter.load(candidate_id)

        assert record in loaded
        assert record not in adapter.load(other_candidate_id)
    finally:
        # The UUID scope belongs only to this smoke test; never perform an unfiltered delete.
        try:
            client.delete_all(user_id=candidate_id)
        finally:
            http_client.close()
