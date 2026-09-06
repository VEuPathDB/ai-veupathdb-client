"""What ``eda_schemas vendor`` writes, measured against a fake upstream."""

from __future__ import annotations

import datetime
import hashlib
import shutil
from collections.abc import Callable, Coroutine, Iterator
from pathlib import Path
from typing import Any

import pytest

from veupathdb.devtools import eda_schemas
from veupathdb.devtools.eda_schemas import (
    LIBRARY_FILE,
    VendoredRaml,
    load_pin,
    raml_pin_drift,
    reload,
    vendor_raml,
)

_INCLUDE = "hash-id.raml"


@pytest.fixture
def vendored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[Path, Path, dict[str, bytes]]]:
    """A copy of the vendored RAML and its pin, plus the bytes upstream serves."""
    upstream_dir = tmp_path / "upstream"
    shutil.copytree(eda_schemas.UPSTREAM_DIR, upstream_dir)
    pin_file = upstream_dir / "schema-pin.json"
    served = {
        relative: (eda_schemas.UPSTREAM_DIR / relative).read_bytes()
        for relative in load_pin().files
    }
    monkeypatch.setattr(eda_schemas, "UPSTREAM_DIR", upstream_dir)
    monkeypatch.setattr(eda_schemas, "SCHEMA_PIN_FILE", pin_file)
    reload()
    yield upstream_dir, pin_file, served
    reload()


def _fetcher(
    served: dict[str, bytes], asked: list[str]
) -> Callable[[str], Coroutine[Any, Any, bytes]]:
    pin = load_pin()
    by_url = {pin.base_url + LIBRARY_FILE: LIBRARY_FILE} | dict(pin.includes)

    async def fetch(url: str) -> bytes:
        relative = by_url[url]
        asked.append(relative)
        return served[relative]

    return fetch


@pytest.mark.asyncio
async def test_the_fetcher_is_asked_for_the_library_and_its_include(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    _, _, served = vendored
    asked: list[str] = []

    count = await vendor_raml(_fetcher(served, asked))

    assert count == 2
    assert asked == [LIBRARY_FILE, _INCLUDE]


@pytest.mark.asyncio
async def test_unchanged_bytes_leave_the_pin_untouched(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    upstream_dir, pin_file, served = vendored
    before = pin_file.read_bytes()

    await vendor_raml(_fetcher(served, []))

    assert pin_file.read_bytes() == before
    assert raml_pin_drift(load_pin()) == ()
    assert (upstream_dir / _INCLUDE).read_bytes() == served[_INCLUDE]


@pytest.mark.asyncio
async def test_a_changed_byte_is_written_and_repinned(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    upstream_dir, pin_file, served = vendored
    served[_INCLUDE] = served[_INCLUDE] + b"\n"

    await vendor_raml(_fetcher(served, []))

    refreshed = VendoredRaml.model_validate_json(pin_file.read_text())
    assert (upstream_dir / _INCLUDE).read_bytes() == served[_INCLUDE]
    assert refreshed.files[_INCLUDE] == hashlib.sha256(served[_INCLUDE]).hexdigest()
    assert (
        refreshed.vendored_at
        == datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    )
    assert raml_pin_drift(refreshed) == ()


@pytest.mark.asyncio
async def test_a_file_the_library_no_longer_includes_is_deleted(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    upstream_dir, pin_file, served = vendored
    stray = upstream_dir / "left-behind.raml"
    stray.write_text("#%RAML 1.0 DataType\ntype: string\n")
    before = pin_file.read_bytes()

    await vendor_raml(_fetcher(served, []))

    assert not stray.exists()
    assert pin_file.read_bytes() == before


@pytest.mark.asyncio
async def test_an_edited_vendored_file_is_reported_as_drift(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    upstream_dir, _, _ = vendored
    (upstream_dir / _INCLUDE).write_text("type: string\n")

    assert raml_pin_drift(load_pin()) == (
        f"{_INCLUDE}: differs from the pinned upstream bytes",
    )
