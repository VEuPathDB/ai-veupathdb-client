"""Conversion between a typed ``ParamValue`` and WDK's wire and decoded forms."""

from collections.abc import Callable, Mapping

from pydantic import JsonValue, TypeAdapter

from veupathdb.domain.parameters.filter_clause import FilterValue
from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    InputDatasetValue,
    InputStepValue,
    MultiPickValue,
    NumberRangeValue,
    NumberValue,
    ParamKind,
    ParamValue,
    SinglePickValue,
    StringValue,
    TimestampValue,
)

_PARAM_KIND_ADAPTER: TypeAdapter[ParamKind] = TypeAdapter(ParamKind)


def as_param_kind(raw: str) -> ParamKind:
    return _PARAM_KIND_ADAPTER.validate_python(raw)


_READERS: dict[ParamKind, Callable[[str], ParamValue]] = {
    "string": StringValue.from_wire,
    "number": NumberValue.from_wire,
    "number-range": NumberRangeValue.from_wire,
    "date": DateValue.from_wire,
    "date-range": DateRangeValue.from_wire,
    "timestamp": TimestampValue.from_wire,
    "single-pick-vocabulary": SinglePickValue.from_wire,
    "multi-pick-vocabulary": MultiPickValue.from_wire,
    "filter": FilterValue.from_wire,
    "input-dataset": InputDatasetValue.from_wire,
    "input-step": InputStepValue.from_wire,
}


def from_wire(kind: ParamKind, wire: str) -> ParamValue:
    return _READERS[as_param_kind(kind)](wire)


def to_wire(value: ParamValue) -> str:
    return value.to_wire()


def wire_map(values: Mapping[str, ParamValue]) -> dict[str, str]:
    return {name: to_wire(v) for name, v in values.items()}


def to_decoded(value: ParamValue) -> JsonValue:
    return value.to_decoded()


def to_decoded_map(values: dict[str, ParamValue]) -> dict[str, JsonValue]:
    return {name: v.to_decoded() for name, v in values.items()}
