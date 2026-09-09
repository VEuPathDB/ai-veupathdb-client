from __future__ import annotations

from veupathdb.domain.eda_validation import validate_filters

from ._eda_facts import GENE_PHENOTYPE, Filt, phenotype_study

_ENT = GENE_PHENOTYPE
_SUCCESS = "VAR_a8ad31c0"
_COUNT = "EUPATH_0043064"
_DATE = "EUPATH_0043256"
_LON = "OBI_0001621"


def _errors(*filters: Filt) -> list[str]:
    return validate_filters(phenotype_study(), list(filters))


class TestTheRangeMatchesTheVariable:
    def test_a_number_range_on_a_longitude_variable_is_refused(self) -> None:
        assert len(_errors(Filt(_ENT, _LON, "numberRange", min=0.0, max=1.0))) == 1

    def test_a_longitude_range_on_a_number_variable_is_refused(self) -> None:
        assert (
            len(_errors(Filt(_ENT, _COUNT, "longitudeRange", left=0.0, right=1.0))) == 1
        )

    def test_a_date_range_on_a_string_variable_is_refused(self) -> None:
        assert _errors(
            Filt(
                _ENT,
                _SUCCESS,
                "dateRange",
                min="2017-05-05T00:00:00",
                max="2017-05-11T00:00:00",
            )
        ) == [
            (
                f"Filter dateRange on variable {_SUCCESS} of entity {_ENT} is refused: "
                f"the variable type is string, and dateRange applies to a variable of "
                f"type date."
            )
        ]


class TestTheBounds:
    def test_an_inverted_number_range_is_refused(self) -> None:
        errors = _errors(Filt(_ENT, _COUNT, "numberRange", min=100.0, max=0.0))
        assert len(errors) == 1
        assert "min" in errors[0]

    def test_a_bare_date_bound_is_refused_before_the_500(self) -> None:
        errors = _errors(
            Filt(_ENT, _DATE, "dateRange", min="2017-05-05", max="2017-05-08")
        )
        assert len(errors) == 2
        assert all("T00:00:00" in e for e in errors)

    def test_a_dated_bound_with_a_time_passes(self) -> None:
        assert (
            _errors(
                Filt(
                    _ENT,
                    _DATE,
                    "dateRange",
                    min="2017-05-05T00:00:00",
                    max="2017-05-08T00:00:00",
                )
            )
            == []
        )

    def test_an_inverted_date_range_is_refused(self) -> None:
        """min above max returns count 0 with HTTP 200, exactly like a number range."""
        assert _errors(
            Filt(
                _ENT,
                _DATE,
                "dateRange",
                min="2017-05-11T00:00:00",
                max="2017-05-05T00:00:00",
            )
        ) == [
            (
                f"Filter dateRange on variable {_DATE} of entity {_ENT} has min "
                f"2017-05-11T00:00:00 above max 2017-05-05T00:00:00, which returns "
                f"count 0 rather than an error."
            )
        ]


class TestTheLongitudeWindow:
    def test_a_degenerate_longitude_window_is_refused(self) -> None:
        """left == right silently selects every row, so it never means what it looks like."""
        assert _errors(Filt(_ENT, _LON, "longitudeRange", left=15.5, right=15.5)) == [
            (
                f"Filter longitudeRange on variable {_LON} of entity {_ENT} has left "
                f"15.5 equal to right 15.5 within 1e-08, and the service reads an equal "
                f"pair as a no-op that keeps every row."
            )
        ]

    def test_a_longitude_window_narrower_than_the_epsilon_is_degenerate(self) -> None:
        """The service compares abs(left - right) against 1e-8, not against zero."""
        assert _errors(
            Filt(_ENT, _LON, "longitudeRange", left=15.0, right=15.000000001)
        ) == [
            (
                f"Filter longitudeRange on variable {_LON} of entity {_ENT} has left "
                f"15.0 equal to right 15.000000001 within 1e-08, and the service reads "
                f"an equal pair as a no-op that keeps every row."
            )
        ]

    def test_a_longitude_window_wider_than_the_epsilon_passes(self) -> None:
        assert (
            _errors(Filt(_ENT, _LON, "longitudeRange", left=15.0, right=15.0000001))
            == []
        )


def _declared(min_bound: float, max_bound: float) -> list[str]:
    return validate_filters(
        phenotype_study(),
        [Filt(_ENT, _COUNT, "numberRange", min=min_bound, max=max_bound)],
        {(_ENT, _COUNT): (0.0, 20.0)},
    )


class TestTheDeclaredRange:
    def test_bounds_that_equal_the_declared_range_pass(self) -> None:
        """Both declared bounds are inside the range, so the pair is exact."""
        assert _declared(0.0, 20.0) == []

    def test_a_max_one_unit_above_the_declared_range_is_refused(self) -> None:
        assert _declared(0.0, 21.0) == [
            (
                f"Filter numberRange on variable {_COUNT} of entity {_ENT} has 21.0 "
                f"outside the declared range 0.0 to 20.0."
            )
        ]

    def test_a_min_one_unit_below_the_declared_range_is_refused(self) -> None:
        assert _declared(-1.0, 20.0) == [
            (
                f"Filter numberRange on variable {_COUNT} of entity {_ENT} has -1.0 "
                f"outside the declared range 0.0 to 20.0."
            )
        ]

    def test_a_bound_outside_the_declared_range_is_reported_as_declared(self) -> None:
        """The bound is a hint, so the message says declared range, never invalid."""
        errors = _declared(0.0, 25.0)
        assert len(errors) == 1
        assert "declared range" in errors[0]
        assert "25.0" in errors[0]
        assert "20.0" in errors[0]

    def test_the_same_bound_passes_when_no_range_is_declared(self) -> None:
        assert _errors(Filt(_ENT, _COUNT, "numberRange", min=0.0, max=25.0)) == []
