"""Vocabulary value matching (operates on the typed WDK vocabulary union)."""

import math
from typing import cast

from pydantic import JsonValue

from veupathdb.domain.parameters.wdk_vocab import WDKVocabulary, flatten_vocab
from veupathdb.errors import ValidationError
from veupathdb.logging import get_logger

logger = get_logger(__name__)


def numeric_equivalent(a: str | None, b: str | None) -> bool:
    """Check if two string values represent the same number.

    Handles precision differences between WDK vocab values (often floats)
    and imported strategy parameters (often full-precision decimals).
    """
    if not a or not b:
        return False
    try:
        fa = float(str(a).strip())
        fb = float(str(b).strip())
    except (ValueError, TypeError) as exc:
        logger.debug("Failed to compare numeric equivalence", error=str(exc))
        return False
    return (
        math.isfinite(fa)
        and math.isfinite(fb)
        and math.isclose(fa, fb, rel_tol=1e-9, abs_tol=1e-12)
    )


def _looks_numeric(value: str) -> bool:
    """Quick check if a string could plausibly be a number."""
    try:
        float(value)
    except ValueError:
        return False
    else:
        return True


def match_vocab_value(
    *,
    vocab: WDKVocabulary | None,
    param_name: str,
    value: str,
) -> str:
    """Match a user-supplied value against a vocabulary, returning the canonical form.

    Tries exact display match, exact value match, then numeric equivalence.
    Raises ``ValidationError`` if no match is found.
    """
    if not vocab:
        return value
    value_norm = value.strip()

    options = flatten_vocab(vocab)
    try_numeric = _looks_numeric(value_norm)
    for option in options:
        if value_norm in (option.display, option.value):
            return option.value
        if try_numeric and (
            numeric_equivalent(value_norm, option.display)
            or numeric_equivalent(value_norm, option.value)
        ):
            return option.value

    value_lower = value_norm.lower()
    suggestions: list[str] = [
        (option.value or option.display)
        for option in options
        if value_lower in option.display.lower() or value_lower in option.value.lower()
    ][:10]

    detail = f"Parameter '{param_name}' does not accept '{value}'."
    if suggestions:
        detail += f" Did you mean one of: {suggestions}"
    else:
        detail += (
            f" Do NOT guess or invent parameter values."
            f" Call get_parameter_options(search_name='<search>',"
            f" parameter_id='{param_name}', query='<keyword>')"
            f" to see valid values, then copy an EXACT value from the response."
            f" Example: if the options show"
            f" '    amastigote esmeraldo-like_Trypanosoma cruzi CL Brener Esmeraldo-like'"
            f" then pass exactly that full string as the value."
        )

    valid_options = [(option.value or option.display) for option in options][:50]
    raise ValidationError(
        title="Invalid parameter value",
        detail=detail,
        errors=[
            {
                "param": param_name,
                "value": value,
                "suggestions": ", ".join(suggestions),
                "validOptions": cast("JsonValue", valid_options),
            },
        ],
    )
