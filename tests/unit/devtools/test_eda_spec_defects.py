"""How a recorded specification defect bends a declared type to the wire."""

from __future__ import annotations

import pytest
from pydantic import JsonValue, ValidationError

from veupathdb.devtools.eda_schemas import SpecDefect, verify_body, verify_wire_body

_CLOSED: dict[str, JsonValue] = {
    "type": "object",
    "properties": {"pvalue": {"type": "array", "items": {"type": "number"}}},
    "required": ["pvalue"],
    "additionalProperties": False,
}


def _defect(**fields: JsonValue) -> SpecDefect:
    return SpecDefect.model_validate(
        {"raml_type": "T", "measured": "m", "records": "r"} | fields
    )


def test_a_retype_without_a_wire_type_is_refused() -> None:
    with pytest.raises(ValidationError, match="only a retype names a wire type"):
        _defect(member="pvalue", kind="retyped-on-the-wire")


def test_a_wire_type_on_another_kind_is_refused() -> None:
    with pytest.raises(ValidationError, match="only a retype names a wire type"):
        _defect(
            member="pvalue", kind="required-but-absent", wire_type={"type": "number"}
        )


def test_a_retype_replaces_the_member_and_keeps_it_required() -> None:
    defect = _defect(
        member="pvalue", kind="retyped-on-the-wire", wire_type={"type": "number"}
    )

    assert defect.applied(_CLOSED) == _CLOSED | {
        "properties": {"pvalue": {"type": "number"}}
    }


def test_an_undeclared_member_of_a_closed_type_is_admitted_as_any_value() -> None:
    defect = _defect(member="min", kind="undeclared-on-the-wire")

    applied = defect.applied(_CLOSED)

    assert applied == _CLOSED | {
        "properties": {
            "pvalue": {"type": "array", "items": {"type": "number"}},
            "min": {},
        }
    }


def test_an_undeclared_member_of_an_open_type_changes_nothing() -> None:
    open_type = {k: v for k, v in _CLOSED.items() if k != "additionalProperties"}
    defect = _defect(member="min", kind="undeclared-on-the-wire")

    assert defect.applied(open_type) == open_type


def test_the_recorded_cont_table_statistics_are_numbers_on_the_wire() -> None:
    row: JsonValue = {"chisq": 0, "pvalue": 1, "degreesFreedom": 2}

    assert len(verify_body("ContTableStatsTable", row)) == 3
    assert verify_wire_body("ContTableStatsTable", row) == ()
