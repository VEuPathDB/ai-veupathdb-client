"""The ISO local date every WDK date parameter reads."""

from __future__ import annotations

import datetime
import re
from typing import Annotated

from pydantic import AfterValidator

_ISO_LOCAL_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


def _iso_local_date(value: str) -> str:
    if _ISO_LOCAL_DATE.fullmatch(value) is None:
        msg = f"a date is yyyy-mm-dd, not {value!r}"
        raise ValueError(msg)
    try:
        datetime.date.fromisoformat(value)
    except ValueError:
        msg = f"a date is a calendar date in yyyy-mm-dd, not {value!r}"
        raise ValueError(msg) from None
    return value


ISODate = Annotated[str, AfterValidator(_iso_local_date)]
