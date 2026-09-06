"""The date form WDK's range parameter can parse."""

from __future__ import annotations

import datetime
from typing import Annotated

from pydantic import AfterValidator


def _iso_date(value: str) -> str:
    """A bound WDK's standard date format parses, or a refusal here.

    ``DateRangeParam`` does not catch its own parse failure, so a bound in
    another format is a 500 that names nothing.
    """
    datetime.date.fromisoformat(value)
    return value


WDKDateBound = Annotated[str, AfterValidator(_iso_date)]
