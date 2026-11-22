from __future__ import annotations

import pytest
from pydantic import JsonValue, TypeAdapter

from veupathdb.domain.parameters import (
    FilterFacets,
    FilterProposals,
    FilterValue,
    HeldValue,
    KeptValue,
    ParamValue,
    StatedValuesError,
    from_wire,
    stated_form,
)
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberRangeValue,
    NumberValue,
    SinglePickValue,
    StringValue,
    TimestampValue,
)
from veupathdb.wdk.wdk_parameters import WDKParameter

_PARAM: TypeAdapter[WDKParameter] = TypeAdapter(WDKParameter)
_VALUE: TypeAdapter[ParamValue] = TypeAdapter(ParamValue)

_FACETS: list[JsonValue] = [
    {"term": "sex", "display": "Sex", "type": "string"},
    {"term": "age", "display": "Age", "type": "number", "isRange": True},
    {"term": "count", "display": "Count", "type": "number"},
    {"term": "collected", "display": "Collected", "type": "date", "isRange": True},
    {"term": "group", "display": "Group", "type": "multiFilter"},
]

_DECLARED: dict[str, JsonValue] = {
    "text": {"name": "text", "type": "string"},
    "cutoff": {"name": "cutoff", "type": "string", "isNumber": True},
    "count": {"name": "count", "type": "number", "min": 0, "max": 100},
    "span": {"name": "span", "type": "number-range", "min": 0, "max": 100},
    "open_span": {"name": "open_span", "type": "number-range"},
    "day": {"name": "day", "type": "date"},
    "days": {"name": "days", "type": "date-range"},
    "stamp": {"name": "stamp", "type": "timestamp"},
    "pick": {
        "name": "pick",
        "type": "single-pick-vocabulary",
        "vocabulary": [["a", "A", None], ["b", "B", None]],
    },
    "picks": {
        "name": "picks",
        "type": "multi-pick-vocabulary",
        "vocabulary": [["a", "A", None], ["b", "B", None]],
    },
    "optional_picks": {
        "name": "optional_picks",
        "type": "multi-pick-vocabulary",
        "allowEmptyValue": True,
        "vocabulary": [["a", "A", None], ["b", "B", None]],
    },
    "optional_count": {
        "name": "optional_count",
        "type": "number",
        "allowEmptyValue": True,
    },
    "samples": {
        "name": "samples",
        "type": "filter",
        "ontology": _FACETS,
        "values": {"sex": ["female", "male"], "count": ["1", "2", "3"]},
    },
    "optional_samples": {
        "name": "optional_samples",
        "type": "filter",
        "allowEmptyValue": True,
        "ontology": _FACETS,
        "values": {"sex": ["female", "male"]},
    },
    "ids": {"name": "ids", "type": "input-dataset"},
    "step": {"name": "step", "type": "input-step"},
}


def _param(name: str) -> WDKParameter:
    return _PARAM.validate_python(_DECLARED[name])


def _read_back(name: str, value: ParamValue) -> str:
    param = _param(name)
    form = stated_form(value)
    assert not isinstance(form, KeptValue)
    read = param.read_stated(form)
    match read:
        case FilterProposals():
            return FilterFacets.of(param).bind(read).to_wire()
        case _:
            return _VALUE.validate_python(read).to_wire()


_STATEABLE: list[tuple[str, ParamValue]] = [
    ("text", StringValue(value="kinase")),
    ("cutoff", StringValue(value="0.5")),
    ("count", NumberValue(value=3)),
    ("count", NumberValue(value=2.5)),
    ("optional_count", NumberValue(value=None)),
    ("span", NumberRangeValue(min=1, max=20)),
    ("day", DateValue(value="2024-03-01")),
    ("days", DateRangeValue(min="2024-01-01", max="2024-02-01")),
    ("stamp", TimestampValue(value="2024-01-01T00:00:00")),
    ("pick", SinglePickValue(value="b")),
    ("picks", MultiPickValue(values=["a", "b"])),
    ("optional_picks", MultiPickValue(values=[])),
    ("ids", InputDatasetValue(dataset_id="123")),
    ("step", InputStepValue(step_id="42")),
    ("optional_samples", from_wire("filter", "")),
]

_HELD_WIRES: list[tuple[str, str]] = [
    (
        "samples",
        '{"filters": [{"field": "sex", "type": "string", "isRange": false, "includeUnknown": false, "value": ["female"]}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "age", "type": "number", "isRange": true, "includeUnknown": true, "value": {"min": 1.0, "max": 5.0}}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "age", "type": "number", "isRange": true, "includeUnknown": false, "value": {"min": 1.0}}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "count", "type": "number", "isRange": false, "includeUnknown": false, "value": [1.0, 3.0]}]}',
    ),
    (
        "samples",
        '{"filters": [{"field": "collected", "type": "date", "isRange": true, "includeUnknown": false, "value": {"min": "2020-01-01", "max": "2021-01-01"}}]}',
    ),
    ("span", '{"min": 0.0, "max": 100.0}'),
    ("picks", '["b"]'),
]


@pytest.mark.parametrize(("name", "value"), _STATEABLE)
def test_a_value_reads_back_to_its_own_wire(name: str, value: ParamValue) -> None:
    assert _read_back(name, value) == value.to_wire()


@pytest.mark.parametrize(("name", "wire"), _HELD_WIRES)
def test_a_value_wdk_holds_reads_back_to_its_wire(name: str, wire: str) -> None:
    value = from_wire(_param(name).type, wire)

    assert _read_back(name, value) == value.to_wire()


def test_a_filter_is_stated_as_its_clauses() -> None:
    value = from_wire(
        "filter",
        '{"filters": [{"field": "total_variants", "type": "number", "isRange": true, '
        '"includeUnknown": false, "value": {"min": 1.0}}]}',
    )

    assert stated_form(value) == [{"field": "total_variants", "value": {"min": 1.0}}]


def test_a_pick_is_stated_as_its_terms() -> None:
    value = from_wire("multi-pick-vocabulary", '["Plasmodium falciparum 3D7"]')

    assert stated_form(value) == ["Plasmodium falciparum 3D7"]


def test_a_held_value_is_kept() -> None:
    assert stated_form(HeldValue(wire="x,y")) == KeptValue(wire="x,y")


def test_a_filter_with_no_clause_is_kept() -> None:
    assert stated_form(FilterValue()) == KeptValue(wire='{"filters": []}')


def test_a_multi_filter_clause_is_kept() -> None:
    wire = (
        '{"filters": [{"field": "group", "type": "multiFilter", "isRange": false, '
        '"includeUnknown": false, "value": {"operation": "union", "filters": '
        '[{"field": "sex", "type": "string", "isRange": false, '
        '"includeUnknown": false, "value": ["female"]}]}}]}'
    )

    assert stated_form(from_wire("filter", wire)) == KeptValue(wire=wire)


def test_a_range_is_read_with_both_bounds() -> None:
    read = _param("span").read_stated({"min": 5})

    assert read == NumberRangeValue(min=5, max=100)


def test_a_range_with_no_declared_bound_states_both() -> None:
    with pytest.raises(StatedValuesError):
        _param("open_span").read_stated({"min": 5})


def test_an_empty_filter_list_names_a_non_empty_list() -> None:
    with pytest.raises(StatedValuesError) as refusal:
        _param("samples").read_stated([])

    assert "takes a non-empty list of" in str(refusal.value)
