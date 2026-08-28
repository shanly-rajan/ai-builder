"""Global pytest safety controls for ScholarPath's offline default suite."""

import socket
from collections.abc import Iterator
from typing import Never

import pytest


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
