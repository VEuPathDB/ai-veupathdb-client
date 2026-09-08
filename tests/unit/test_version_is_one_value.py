"""The declared version and the package attribute are one value."""

from __future__ import annotations

import tomllib
from importlib.metadata import version
from pathlib import Path

import veupathdb

PYPROJECT = Path(__file__).resolve().parents[2] / "pyproject.toml"


def declared_version() -> str:
    return str(tomllib.loads(PYPROJECT.read_text())["project"]["version"])


def test_package_attribute_matches_the_declared_version() -> None:
    assert veupathdb.__version__ == declared_version()


def test_package_attribute_matches_the_installed_distribution() -> None:
    assert veupathdb.__version__ == version("veupathdb-py")
