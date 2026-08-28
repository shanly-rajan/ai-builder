"""Offline integration test for the installed ScholarPath distribution."""

from importlib.metadata import version

import scholarpath


def test_installed_distribution_matches_package_version() -> None:
    assert version("scholarpath") == scholarpath.__version__
