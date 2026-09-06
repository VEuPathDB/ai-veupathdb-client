"""Hidden required parameters and the report of what was filled.

WDK demands hidden required parameters and the model cannot see them, so their
declared defaults are supplied and named. A visible required parameter stays
the model's job: filling it masks genuinely missing input.
"""

from __future__ import annotations

from veupathdb.domain.parameters.specs import (
    ParamSpecNormalized,
    fill_hidden_required_defaults,
    filled_hidden_defaults,
)
from veupathdb.domain.parameters.values import SinglePickValue, StringValue


def _spec(
    name: str,
    *,
    visible: bool,
    default: str | None,
    allow_empty: bool = False,
) -> ParamSpecNormalized:
    return ParamSpecNormalized(
        name=name,
        param_type="string",
        is_visible=visible,
        allow_empty_value=allow_empty,
        initial_display_value=default,
    )


# ``document_type`` is hidden, required, and fixed to ``gene``. The model
# cannot see it, so the fill supplies it.
_GENES_BY_TEXT = {
    "text_expression": _spec("text_expression", visible=True, default="*reductase"),
    "document_type": _spec("document_type", visible=False, default="gene"),
}

_PROFILE = {
    "organism": _spec("organism", visible=True, default="Pf3D7"),
    "channel": _spec("channel", visible=False, default="Channel 1"),
    "profile_pattern": _spec("profile_pattern", visible=False, default="hsap=1T"),
}


class TestTheFill:
    def test_hidden_required_param_is_filled_from_its_fixed_default(self) -> None:
        filled = fill_hidden_required_defaults(
            _GENES_BY_TEXT, {"text_expression": StringValue(value="kinase")}
        )

        assert filled == {
            "text_expression": StringValue(value="kinase"),
            "document_type": StringValue(value="gene"),
        }

    def test_visible_required_param_is_not_auto_filled(self) -> None:
        # A genuinely missing VISIBLE required param must not be silently filled
        # with the form-example default.
        filled = fill_hidden_required_defaults(_GENES_BY_TEXT, {})

        assert filled == {"document_type": StringValue(value="gene")}


class TestTheFillIsNamed:
    def test_a_hidden_default_is_reported(self) -> None:
        assert filled_hidden_defaults(_PROFILE, {}) == ["channel", "profile_pattern"]

    def test_a_value_the_caller_supplied_is_not_reported(self) -> None:
        supplied = {"profile_pattern": SinglePickValue(value="%hsap:N%pfal:Y%")}

        assert filled_hidden_defaults(_PROFILE, supplied) == ["channel"]

    def test_a_visible_parameter_is_never_reported(self) -> None:
        # A visible default is the model's to see and choose.
        assert "organism" not in filled_hidden_defaults(_PROFILE, {})

    def test_nothing_to_fill_reports_nothing(self) -> None:
        supplied = {
            "channel": SinglePickValue(value="Channel 1"),
            "profile_pattern": SinglePickValue(value="%pfal:Y%"),
        }

        assert filled_hidden_defaults(_PROFILE, supplied) == []

    def test_a_hidden_param_with_no_default_is_not_reported(self) -> None:
        specs = {"secret": _spec("secret", visible=False, default=None)}

        assert filled_hidden_defaults(specs, {}) == []

    def test_a_hidden_param_that_allows_empty_is_not_reported(self) -> None:
        specs = {"opt": _spec("opt", visible=False, default="x", allow_empty=True)}

        assert filled_hidden_defaults(specs, {}) == []


class TestTheReportAgreesWithTheFill:
    def test_every_reported_name_was_actually_filled(self) -> None:
        filled = fill_hidden_required_defaults(_PROFILE, {})

        assert set(filled_hidden_defaults(_PROFILE, {})) <= set(filled)

    def test_the_report_matches_what_the_fill_added(self) -> None:
        before = {"channel": SinglePickValue(value="Channel 2")}
        filled = fill_hidden_required_defaults(_PROFILE, before)

        assert sorted(set(filled) - set(before)) == filled_hidden_defaults(
            _PROFILE, before
        )
