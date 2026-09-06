"""The pinned WDK responses the hermetic lane reads, and the commands behind them.

Every fixture in the store is a response a live site returned, and every schema
under ``schema/`` is a file WDK publishes. Nothing writes either by hand:
``record`` refreshes the responses, ``vendor`` refreshes the schemas at the
commit ``schema-pin.json`` names, and ``verify`` measures one against the other
without a network or a credential.

Usage::

    python -m veupathdb.devtools.fixtures list
    python -m veupathdb.devtools.fixtures record [--only NAME ...]
    python -m veupathdb.devtools.fixtures verify
    python -m veupathdb.devtools.fixtures vendor

Recording needs ``VEUPATHDB_AUTH_TOKEN``: VEuPathDB refuses anonymous service
calls. Every request below is user-independent, so no account is addressed.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
import hashlib
import sys
from collections.abc import Awaitable, Callable, Iterator
from functools import cache
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin

import httpx
import json5
from jsonschema import Draft4Validator
from pydantic import BaseModel, ConfigDict, JsonValue, TypeAdapter
from referencing import Registry
from referencing.jsonschema import DRAFT4, Schema

from veupathdb.devtools.pins import VendoredPin, pin_drift
from veupathdb.testing.wdk_fixtures import (
    FIXTURE_DIR,
    FIXTURES,
    SCHEMA_DIR,
    SCHEMA_PIN_FILE,
    FixtureProvenance,
    FixtureRequest,
    RecordedWDKResponse,
    fixture_request,
    load_recorded,
)
from veupathdb.wdk.factory import get_wdk_client

_VENDOR_TIMEOUT_SECONDS = 30.0
_SCHEMA_ADAPTER: TypeAdapter[dict[str, JsonValue]] = TypeAdapter(dict[str, JsonValue])


ENFORCED_SCHEMAS: tuple[str, ...] = (
    "wdk.answer.answer-spec-request",
    "wdk.answer.post-request",
    "wdk.answer.post-response",
    "wdk.records.get",
    "wdk.records.name.get",
    "wdk.standard-post-response",
    "wdk.users.datasets.post-request",
    "wdk.users.datasets.post-response",
    "wdk.users.steps.id.get-response",
    "wdk.users.steps.id.patch-request",
    "wdk.users.steps.post-request",
    "wdk.users.strategies.get-response",
    "wdk.users.strategies.id.put-request",
    "wdk.users.strategies.post-request",
)
"""The schema annotations WDK binds to an endpoint PathFinder calls.

Twelve endpoints, fourteen names, and the vendored tree is their transitive
``$ref`` closure. A name here is not a promise that the live service holds to
it: ``wdk.answer.post-response`` does not, which is why no fixture binds it.
"""


class SchemaPin(VendoredPin):
    """The WDK commit the vendored JSON Schemas were copied from."""


def load_schema_pin() -> SchemaPin:
    """The pin the vendored schema tree answers to."""
    return SchemaPin.model_validate_json(SCHEMA_PIN_FILE.read_text())


def schema_file(schema_name: str) -> str:
    """The file a WDK ``@InSchema``/``@OutSchema`` value names.

    ``JsonSchemaProvider.cleanPath`` turns the dots into directory separators
    and appends the extension, so the annotation value is the path.
    """
    return schema_name.replace(".", "/") + ".json"


def _read_schema(path: Path) -> dict[str, JsonValue]:
    """Parse one vendored schema. Four files upstream carry trailing commas."""
    return _SCHEMA_ADAPTER.validate_python(json5.loads(path.read_text()))


@cache
def _schema_registry() -> Registry[Schema]:
    """Every vendored schema, keyed by the URL its relative ``$ref``s resolve against."""
    pin = load_schema_pin()
    return Registry().with_resources(
        (
            urljoin(pin.base_url, relative),
            DRAFT4.create_resource(_read_schema(SCHEMA_DIR / relative)),
        )
        for relative in pin.files
    )


def verify_body(schema_name: str, body: JsonValue) -> tuple[str, ...]:
    """Every draft-04 error the pinned schema reports for *body*."""
    pin = load_schema_pin()
    relative = schema_file(schema_name)
    if relative not in pin.files:
        msg = (
            f"{schema_name} names {relative}, which {SCHEMA_PIN_FILE.name} does not pin"
        )
        raise KeyError(msg)
    validator = Draft4Validator(
        {"$ref": urljoin(pin.base_url, relative)}, registry=_schema_registry()
    )
    return tuple(
        sorted(
            f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: "
            f"{error.message}"
            for error in validator.iter_errors(body)
        )
    )


class SchemaCheck(BaseModel):
    """One fixture body measured against the schema WDK binds to its endpoint."""

    model_config = ConfigDict(frozen=True)

    fixture: str
    direction: Literal["request", "response"]
    schema_name: str
    errors: tuple[str, ...] = ()


def schema_checks() -> tuple[SchemaCheck, ...]:
    """One check per manifest binding: request bodies in, recorded responses out."""
    checks: list[SchemaCheck] = []
    for request in FIXTURES:
        if request.in_schema is not None:
            checks.append(
                SchemaCheck(
                    fixture=request.name,
                    direction="request",
                    schema_name=request.in_schema,
                    errors=verify_body(request.in_schema, request.body),
                )
            )
        if request.out_schema is not None:
            checks.append(
                SchemaCheck(
                    fixture=request.name,
                    direction="response",
                    schema_name=request.out_schema,
                    errors=verify_body(
                        request.out_schema, load_recorded(request.name).json_body()
                    ),
                )
            )
    return tuple(checks)


def schema_pin_drift(pin: SchemaPin) -> tuple[str, ...]:
    """Every vendored schema that is missing, edited, or absent from the pin."""
    vendored = (
        path.relative_to(SCHEMA_DIR).as_posix() for path in SCHEMA_DIR.rglob("*.json")
    )
    return tuple(pin_drift(pin, SCHEMA_DIR, vendored))


def _external_refs(node: JsonValue) -> Iterator[str]:
    """Every ``$ref`` in *node* that names another file."""
    match node:
        case dict():
            for key, value in node.items():
                match value:
                    case str(ref) if key == "$ref" and not ref.startswith("#"):
                        yield ref
                    case _:
                        yield from _external_refs(value)
        case list():
            for item in node:
                yield from _external_refs(item)
        case _:
            return


def _referenced_file(pin: SchemaPin, relative: str, ref: str) -> str:
    """The vendored path a ``$ref`` inside *relative* points at."""
    resolved = urljoin(urljoin(pin.base_url, relative), ref)
    return resolved.removeprefix(pin.base_url).split("#", 1)[0]


type SchemaFetcher = Callable[[str], Awaitable[bytes]]
"""Answers one absolute schema URL with its bytes, or raises."""


async def vendor_schemas(fetch: SchemaFetcher) -> int:
    """Re-download the pinned tree, following every external ``$ref``.

    The pin is rewritten only when a byte changed, so ``vendored_at`` dates the
    content and not the run.
    """
    pin = load_schema_pin()
    digests: dict[str, str] = {}
    pending = [schema_file(name) for name in ENFORCED_SCHEMAS]
    while pending:
        relative = pending.pop()
        if relative in digests:
            continue
        content = await fetch(urljoin(pin.base_url, relative))
        target = SCHEMA_DIR / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
        digests[relative] = hashlib.sha256(content).hexdigest()
        pending.extend(
            _referenced_file(pin, relative, ref)
            for ref in _external_refs(_read_schema(target))
        )
    for path in sorted(SCHEMA_DIR.rglob("*.json")):
        if path.relative_to(SCHEMA_DIR).as_posix() not in digests:
            path.unlink()
    if digests != pin.files:
        refreshed = pin.model_copy(
            update={
                "files": dict(sorted(digests.items())),
                "vendored_at": datetime.datetime.now(tz=datetime.UTC)
                .date()
                .isoformat(),
            }
        )
        SCHEMA_PIN_FILE.write_text(refreshed.model_dump_json(indent=2) + "\n")
    return len(digests)


async def _vendor_from_upstream() -> int:
    """Vendor the tree over HTTP from the repository the pin names."""
    async with httpx.AsyncClient(timeout=_VENDOR_TIMEOUT_SECONDS) as client:

        async def fetch(url: str) -> bytes:
            response = await client.get(url)
            response.raise_for_status()
            return response.content

        return await vendor_schemas(fetch)


async def record_one(request: FixtureRequest) -> RecordedWDKResponse:
    """Ask a live site and return the response, without writing it."""
    client = get_wdk_client(request.site)
    probe = await client.probe(
        request.method, request.path, params=dict(request.params), json=request.body
    )
    parsed = probe.json_body()
    recorded = RecordedWDKResponse(
        provenance=FixtureProvenance(
            site=request.site,
            method=probe.method,
            url=probe.url,
            status=probe.status,
            content_type=probe.content_type,
            recorded_at=datetime.datetime.now(tz=datetime.UTC).date().isoformat(),
            reads=request.reads,
        ),
        body=parsed,
        text=None if parsed is not None else probe.text,
    )
    request.file.parent.mkdir(parents=True, exist_ok=True)
    request.file.write_text(
        recorded.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    return recorded


async def record_all(names: list[str]) -> int:
    """Record the named fixtures, or the whole manifest when none are named."""
    wanted = [fixture_request(name) for name in names] if names else list(FIXTURES)
    for request in wanted:
        recorded = await record_one(request)
        size = request.file.stat().st_size
        print(
            f"{request.name}: {recorded.provenance.status} "
            f"{recorded.provenance.content_type} {size}b -> {request.file}"
        )
    return len(wanted)


def _list_fixtures() -> None:
    for request in FIXTURES:
        state = "recorded" if request.file.exists() else "MISSING"
        print(f"{request.name:44} {state:9} {request.reads}")


def _verify_fixtures() -> int:
    """Print one line per fixture and return the process exit code."""
    pin = load_schema_pin()
    drift = schema_pin_drift(pin)
    for problem in drift:
        print(f"schema pin: {problem}")

    checks = schema_checks()
    failed = 0
    for request in FIXTURES:
        bound = [check for check in checks if check.fixture == request.name]
        if not bound:
            print(f"{request.name:44} ----  no WDK schema binds this endpoint")
            continue
        broken = [check for check in bound if check.errors]
        failed += len(broken)
        names = " ".join(f"{c.direction}={c.schema_name}" for c in bound)
        print(f"{request.name:44} {'FAIL' if broken else 'PASS':5} {names}")
        for check in broken:
            for error in check.errors:
                print(f"    {check.schema_name}: {error}")

    covered = {check.schema_name for check in checks}
    print(
        f"{len(FIXTURES)} fixture(s), {len(checks)} schema check(s), {failed} failed; "
        f"{len(covered)} of {len(ENFORCED_SCHEMAS)} enforced schemas checked; "
        f"{len(pin.files)} files pinned at {pin.repo}@{pin.sha[:12]}"
    )
    return 1 if failed or drift else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="wdk_fixtures", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("list", help="show the manifest and what is on disk")
    record = sub.add_parser("record", help="refresh the store from live WDK")
    record.add_argument("--only", nargs="*", default=[], metavar="NAME")
    sub.add_parser("verify", help="check every fixture against its pinned WDK schema")
    sub.add_parser("vendor", help="re-download the schema tree at the pinned commit")
    args = parser.parse_args(argv)

    if args.command == "list":
        _list_fixtures()
        return 0
    if args.command == "verify":
        return _verify_fixtures()
    if args.command == "vendor":
        count = asyncio.run(_vendor_from_upstream())
        print(f"vendored {count} schema(s) into {SCHEMA_DIR}")
        return 0
    count = asyncio.run(record_all(args.only))
    print(f"recorded {count} fixture(s) into {FIXTURE_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "ENFORCED_SCHEMAS",
    "SchemaCheck",
    "SchemaFetcher",
    "SchemaPin",
    "load_schema_pin",
    "record_all",
    "record_one",
    "schema_checks",
    "schema_file",
    "schema_pin_drift",
    "vendor_schemas",
    "verify_body",
]
