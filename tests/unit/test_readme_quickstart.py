"""The README's quickstart is executable, and its site listing is offline."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest

from veupathdb.errors import VEuPathDBErrorCode

README = Path(__file__).resolve().parents[2] / "README.md"
_BLOCK = re.compile(r"```python\n(.*?)```", re.DOTALL)


def _quickstart() -> str:
    blocks = _BLOCK.findall(README.read_text())
    assert len(blocks) == 1
    return blocks[0]


@pytest.fixture
def quickstart() -> dict[str, Any]:
    """The README block, executed. Nothing in it opens a connection at import."""
    namespace: dict[str, Any] = {"__name__": "readme_quickstart"}
    exec(compile(_quickstart(), str(README), "exec"), namespace)  # noqa: S102
    return namespace


def test_the_quickstart_names_only_symbols_the_package_exports(
    quickstart: dict[str, Any],
) -> None:
    assert callable(quickstart["site_ids"])
    assert callable(quickstart["kinase_step"])


def test_the_quickstart_lists_the_bundled_sites(quickstart: dict[str, Any]) -> None:
    listed = quickstart["site_ids"]()

    assert "plasmodb" in listed
    assert "toxodb" in listed
    assert len(listed) >= 12


def test_the_readme_names_every_error_code() -> None:
    text = README.read_text()

    assert [code for code in VEuPathDBErrorCode if code.value not in text] == []
