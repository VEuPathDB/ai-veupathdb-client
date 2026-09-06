"""Pure value-shape utilities for parameter handling.

Domain-layer SSOT for "decode this raw value into a list of typed values".
The canonicalizer and the WDK wire decoding both read it, so a JSON-encoded
list, a CSV string and a bare scalar decode the same way everywhere.
"""

import csv
from typing import cast

import json5
from pydantic import JsonValue

from veupathdb.errors import ValidationError
from veupathdb.logging import get_logger

logger = get_logger(__name__)


def parse_json5_value(raw: str) -> JsonValue | None:
    """Parse a JSON5 string into a native value, or ``None`` on failure."""
    try:
        result = json5.loads(raw)
        return cast("JsonValue", result)
    except (ValueError, TypeError) as exc:
        logger.debug("Failed to parse JSON5 value", error=str(exc))
        return None


def _decode_string_value(value: str) -> list[JsonValue]:
    """Decode a string value into a list.

    JSON5 first (handles ``[a, b]``, JSON-quoted scalars, numbers); then
    CSV fallback when JSON5 fails AND a comma is present; otherwise the
    bare string in a one-element list.
    """
    stripped = value.strip()
    if not stripped:
        return []
    parsed = parse_json5_value(stripped)
    if isinstance(parsed, list):
        return [v for v in parsed if v is not None]
    if parsed is not None:
        return [parsed]
    if "," in stripped:
        row = next(csv.reader([stripped], skipinitialspace=True))
        return [item for item in row if item is not None and str(item).strip()]
    return [stripped]


def decode_values(value: JsonValue, name: str) -> list[JsonValue]:
    """Coerce a multi-pick parameter value into a list.

    The SSOT for the multi-pick code path. Handles:
      - ``None`` → ``[]``
      - lists/tuples/sets → list (None values dropped)
      - JSON-encoded list strings (``'["a","b"]'``) → ``["a","b"]``
      - CSV strings (``"a,b,c"``) → ``["a","b","c"]``
      - bare scalars → single-element list

    Single-pick values must use :func:`decode_single_value` instead — they
    are atomic and must never be CSV-split.

    Raises ``ValidationError`` for ``dict`` because no parameter type
    accepts a dict where a list is expected.
    """
    if value is None:
        return []
    if isinstance(value, dict):
        raise ValidationError(
            title="Invalid parameter value",
            detail=f"Parameter '{name}' does not accept dictionaries.",
            errors=[{"param": name, "value": value}],
        )
    if isinstance(value, (list, tuple, set)):
        return [v for v in value if v is not None]
    if isinstance(value, str):
        return _decode_string_value(value)
    return [value]


def decode_single_value(value: JsonValue, name: str) -> list[JsonValue]:
    """Decode a single-pick value WITHOUT CSV-splitting.

    Single-pick vocabulary values are atomic and may themselves contain a
    comma (common in WDK dataset/profileset names), so a bare string is
    always one value. Only an explicit list — a Python list or a JSON-array
    string — carries more than one value (which the caller then rejects).
    """
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        parsed = parse_json5_value(stripped)
        if isinstance(parsed, list):
            return [v for v in parsed if v is not None]
        return [stripped]
    return decode_values(value, name)
