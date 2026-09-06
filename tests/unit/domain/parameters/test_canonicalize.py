"""WDK reads both ends of a range and refuses an object missing one.

A criterion often states one bound. The other end comes from the parameter's
own declared limit rather than being invented or omitted.
"""

from __future__ import annotations

import json

import pytest

from veupathdb.domain.parameters.canonicalize import close_open_range
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.domain.parameters.values import DateRangeValue, NumberRangeValue


class TestBothEndsReachTheWire:
    def test_a_two_sided_range_is_unchanged(self) -> None:
        value = NumberRangeValue(min=20, max=100)

        assert json.loads(value.to_wire()) == {"min": 20, "max": 100}

    def test_an_open_top_takes_the_declared_maximum(self) -> None:
        closed = close_open_range(
            NumberRangeValue(min=20),
            ParamSpecNormalized(name="p", param_type="number-range", max=100),
        )

        assert json.loads(closed.to_wire()) == {"min": 20, "max": 100}

    def test_an_open_bottom_takes_the_declared_minimum(self) -> None:
        closed = close_open_range(
            NumberRangeValue(max=100),
            ParamSpecNormalized(name="p", param_type="number-range", min=0),
        )

        assert json.loads(closed.to_wire()) == {"min": 0, "max": 100}

    def test_the_stated_bound_is_never_moved(self) -> None:
        closed = close_open_range(
            NumberRangeValue(min=20),
            ParamSpecNormalized(name="p", param_type="number-range", min=0, max=100),
        )

        assert json.loads(closed.to_wire())["min"] == 20


class TestWithoutADeclaredLimit:
    def test_an_open_range_is_left_alone_to_fail_loudly(self) -> None:
        # Inventing a bound would silently change the criterion. WDK refuses
        # the one-sided object and names the parameter.
        spec = ParamSpecNormalized(name="p", param_type="number-range")

        assert close_open_range(NumberRangeValue(min=20), spec) == NumberRangeValue(
            min=20
        )

    def test_a_date_range_closes_from_its_own_limits(self) -> None:
        closed = close_open_range(
            DateRangeValue(min="2025-01-01"),
            ParamSpecNormalized(
                name="d", param_type="date-range", max_date="2025-12-31"
            ),
        )

        assert json.loads(closed.to_wire()) == {
            "min": "2025-01-01",
            "max": "2025-12-31",
        }


class TestTheValueStillRefusesNonsense:
    def test_no_endpoint_at_all_is_refused(self) -> None:
        with pytest.raises(ValueError, match="at least one"):
            NumberRangeValue()

    def test_an_inverted_range_is_refused(self) -> None:
        with pytest.raises(ValueError, match="min"):
            NumberRangeValue(min=100, max=20)
