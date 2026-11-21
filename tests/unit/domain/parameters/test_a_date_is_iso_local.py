from __future__ import annotations

import pytest
from pydantic import TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters import ISODate
from veupathdb.domain.parameters.values import DateRangeValue, DateValue

_ISO_DATE: TypeAdapter[str] = TypeAdapter(ISODate)


def test_an_iso_local_date_reads() -> None:
    assert _ISO_DATE.validate_python("2020-01-01") == "2020-01-01"


@pytest.mark.parametrize(
    "raw", ["20200101", "2020-W01-1", "2020-02-30", "2020-1-01", "2020-01-01T00:00"]
)
def test_another_form_is_refused(raw: str) -> None:
    with pytest.raises(PydanticValidationError, match="yyyy-mm-dd"):
        _ISO_DATE.validate_python(raw)


def test_a_date_value_is_iso_local() -> None:
    with pytest.raises(PydanticValidationError, match="yyyy-mm-dd"):
        DateValue(value="20200101")


def test_a_date_range_bound_is_iso_local() -> None:
    with pytest.raises(PydanticValidationError, match="yyyy-mm-dd"):
        DateRangeValue(min="2020-W01-1")
