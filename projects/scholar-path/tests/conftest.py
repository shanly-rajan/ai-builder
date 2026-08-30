"""Global pytest safety controls for ScholarPath's offline default suite."""

import logging
import socket
from collections.abc import Iterator
from io import StringIO
from typing import Never

import pytest

from scholarpath.config import LogLevel
from scholarpath.observability import configure_application_logging


def _block_network(*args: object, **kwargs: object) -> Never:
    """Fail immediately if a non-live test attempts external network access."""
    del args, kwargs
    raise AssertionError("Default ScholarPath tests must not access the network")


@pytest.fixture(autouse=True)
def block_network_for_non_live_tests(
    monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest
) -> Iterator[None]:
    """Block common socket entry points unless a test is explicitly marked live."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.setattr(socket, "getaddrinfo", _block_network)
        monkeypatch.setattr(socket, "create_connection", _block_network)
        monkeypatch.setattr(socket.socket, "connect", _block_network)
    yield


@pytest.fixture
def application_log_stream() -> Iterator[StringIO]:
    """Capture ScholarPath JSON logs and restore the process-global logger afterwards."""
    logger = logging.getLogger("scholarpath")
    original_handlers = list(logger.handlers)
    original_level = logger.level
    original_propagate = logger.propagate
    logger.handlers.clear()
    stream = StringIO()
    try:
        configure_application_logging(LogLevel.INFO, stream=stream)
        yield stream
    finally:
        logger.handlers.clear()
        logger.handlers.extend(original_handlers)
        logger.setLevel(original_level)
        logger.propagate = original_propagate
