"""What ``fixtures vendor`` writes, measured against a fake upstream."""

from __future__ import annotations

import datetime
import hashlib
import shutil
from collections.abc import Callable, Coroutine
from pathlib import Path
from typing import Any

import pytest

from veupathdb.devtools import fixtures
from veupathdb.devtools.fixtures import (
    SchemaPin,
    load_schema_pin,
    schema_pin_drift,
    vendor_schemas,
)

_ASKED = "includes/string-array.json"


@pytest.fixture
def vendored(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, dict[str, bytes]]:
    """A copy of the vendored tree and its pin, plus the bytes upstream serves."""
    schema_dir = tmp_path / "schema"
    shutil.copytree(fixtures.SCHEMA_DIR, schema_dir)
    pin_file = tmp_path / "schema-pin.json"
    pin_file.write_bytes(fixtures.SCHEMA_PIN_FILE.read_bytes())
    upstream = {
        relative: (fixtures.SCHEMA_DIR / relative).read_bytes()
        for relative in load_schema_pin().files
    }
    monkeypatch.setattr(fixtures, "SCHEMA_DIR", schema_dir)
    monkeypatch.setattr(fixtures, "SCHEMA_PIN_FILE", pin_file)
    return schema_dir, pin_file, upstream


def _fetcher(
    upstream: dict[str, bytes], asked: list[str]
) -> Callable[[str], Coroutine[Any, Any, bytes]]:
    base = load_schema_pin().base_url

    async def fetch(url: str) -> bytes:
        relative = url.removeprefix(base)
        asked.append(relative)
        return upstream[relative]

    return fetch


@pytest.mark.asyncio
async def test_the_fetcher_is_asked_for_the_whole_pinned_closure(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    _, _, upstream = vendored
    asked: list[str] = []

    count = await vendor_schemas(_fetcher(upstream, asked))

    assert count == len(upstream)
    assert set(asked) == set(upstream)


@pytest.mark.asyncio
async def test_unchanged_bytes_leave_the_pin_untouched(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    schema_dir, pin_file, upstream = vendored
    before = pin_file.read_bytes()

    await vendor_schemas(_fetcher(upstream, []))

    assert pin_file.read_bytes() == before
    assert schema_pin_drift(load_schema_pin()) == ()
    assert (schema_dir / _ASKED).read_bytes() == upstream[_ASKED]


@pytest.mark.asyncio
async def test_a_changed_byte_is_written_and_repinned(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    schema_dir, pin_file, upstream = vendored
    upstream[_ASKED] = upstream[_ASKED] + b"\n"

    await vendor_schemas(_fetcher(upstream, []))

    refreshed = SchemaPin.model_validate_json(pin_file.read_text())
    assert (schema_dir / _ASKED).read_bytes() == upstream[_ASKED]
    assert refreshed.files[_ASKED] == hashlib.sha256(upstream[_ASKED]).hexdigest()
    assert (
        refreshed.vendored_at
        == datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    )
    assert schema_pin_drift(refreshed) == ()


@pytest.mark.asyncio
async def test_a_file_outside_the_closure_is_deleted_without_repinning(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    schema_dir, pin_file, upstream = vendored
    stray = schema_dir / "wdk" / "not-in-the-closure.json"
    stray.write_text("{}\n")
    before = pin_file.read_bytes()

    await vendor_schemas(_fetcher(upstream, []))

    assert not stray.exists()
    assert pin_file.read_bytes() == before


def test_an_edited_vendored_file_is_reported_as_drift(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    schema_dir, _, _ = vendored
    (schema_dir / _ASKED).write_text("{}\n")

    assert schema_pin_drift(load_schema_pin()) == (
        f"{_ASKED}: differs from the pinned upstream bytes",
    )


def test_a_file_the_pin_does_not_name_is_reported_as_drift(
    vendored: tuple[Path, Path, dict[str, bytes]],
) -> None:
    schema_dir, _, _ = vendored
    (schema_dir / "wdk" / "stray.json").write_text("{}\n")

    assert schema_pin_drift(load_schema_pin()) == (
        "wdk/stray.json: vendored but not pinned",
    )
