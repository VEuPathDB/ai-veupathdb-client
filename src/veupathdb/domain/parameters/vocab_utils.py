"""Numeric equivalence between a stated value and a vocabulary term."""

import math

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


def looks_numeric(value: str) -> bool:
    """Quick check if a string could plausibly be a number."""
    try:
        float(value)
    except ValueError:
        return False
    else:
        return True
