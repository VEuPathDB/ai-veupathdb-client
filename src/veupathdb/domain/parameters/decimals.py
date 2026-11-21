"""The plain decimal text WDK reads for a number."""

from __future__ import annotations

import math
from decimal import Decimal


def decimal_text(x: float) -> str:
    if not math.isfinite(x):
        msg = f"{x!r} has no decimal text"
        raise ValueError(msg)
    return format(Decimal(repr(x)).normalize(), "f")
