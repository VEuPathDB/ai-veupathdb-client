from __future__ import annotations

import hashlib
import json
import re

from veupathdb.json_types import JSONValue

FAKE_USER_ID = 900000001

_UUID = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_DATETIME = re.compile(
    r"\b\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?"
)
_BOUNDARY = re.compile(rb"\A--([!-~]{1,70})\r\n")


def _constant(value: JSONValue) -> JSONValue:
    match value:
        case str():
            return _DATETIME.sub("<datetime>", _UUID.sub("<uuid>", value))
        case list():
            return [_constant(item) for item in value]
        case dict():
            return {key: _constant(item) for key, item in value.items()}
        case _:
            return value


def canonical_body(body: bytes) -> str:
    if not body:
        return ""
    boundary = _BOUNDARY.match(body)
    if boundary is not None:
        body = body.replace(boundary.group(1), b"<boundary>")
    text = body.decode("utf-8", errors="replace")
    try:
        parsed: JSONValue = json.loads(text)
    except ValueError:
        return text
    return json.dumps(_constant(parsed), sort_keys=True, separators=(",", ":"))


def exchange_key(
    host: str, method: str, path: str, query: list[tuple[str, str]], body: bytes
) -> str:
    canonical_query = "&".join(f"{name}={value}" for name, value in sorted(query))
    digest = hashlib.sha256(canonical_body(body).encode()).hexdigest()
    return f"{host.lower()}|{method.upper()}|{path}|{canonical_query}|{digest}"
