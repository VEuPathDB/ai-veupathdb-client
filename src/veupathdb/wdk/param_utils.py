"""Shared WDK parameter value normalization helpers.

WDK expects all parameter values as strings. Multi-pick enum params use a
JSON array string (see ``AbstractEnumParam.getExternalStableValue`` in the
WDK source). Single-pick params use a plain string value.
"""

import json

from pydantic import JsonValue


def normalize_param_value(value: JsonValue) -> str:
    """Convert a JSON parameter value to the string format WDK expects.

    :param value: Raw parameter value (str, int, float, bool, list, dict, or None).
    :returns: WDK-compatible string representation.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        result = str(value)
    elif isinstance(value, (list, dict)):
        result = json.dumps(value)
    else:
        result = str(value)
    return result
