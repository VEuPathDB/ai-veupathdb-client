from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field, JsonValue, model_validator

from veupathdb.domain.parameters.date_bounds import ISODate
from veupathdb.domain.parameters.decimals import decimal_text
from veupathdb.domain.parameters.filter_clause import FilterValue
from veupathdb.model import CamelModel

ParamKind = Literal[
    "string",
    "number",
    "number-range",
    "date",
    "date-range",
    "timestamp",
    "single-pick-vocabulary",
    "multi-pick-vocabulary",
    "filter",
    "input-dataset",
    "input-step",
]


class StringValue(CamelModel):
    type: Literal["string"] = "string"
    value: str

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class NumberValue(CamelModel):
    type: Literal["number"] = "number"
    value: float | None

    def to_wire(self) -> str:
        return "" if self.value is None else decimal_text(self.value)

    def to_decoded(self) -> JsonValue:
        return "" if self.value is None else self.value


class NumberRangeValue(CamelModel):
    type: Literal["number-range"] = "number-range"
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _ordered(self) -> NumberRangeValue:
        if self.min is not None and self.max is not None and self.min > self.max:
            msg = f"number-range min ({self.min}) > max ({self.max})"
            raise ValueError(msg)
        return self

    @property
    def empty(self) -> bool:
        return self.min is None and self.max is None

    def to_wire(self) -> str:
        if self.empty:
            return ""
        payload: dict[str, float] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return json.dumps(payload)

    def to_decoded(self) -> JsonValue:
        if self.empty:
            return ""
        payload: dict[str, JsonValue] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return payload


class DateValue(CamelModel):
    type: Literal["date"] = "date"
    value: ISODate | None

    def to_wire(self) -> str:
        return self.value or ""

    def to_decoded(self) -> JsonValue:
        return self.value or ""


class DateRangeValue(CamelModel):
    type: Literal["date-range"] = "date-range"
    min: ISODate | None = None
    max: ISODate | None = None

    @property
    def empty(self) -> bool:
        return self.min is None and self.max is None

    def to_wire(self) -> str:
        if self.empty:
            return ""
        payload: dict[str, str] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return json.dumps(payload)

    def to_decoded(self) -> JsonValue:
        if self.empty:
            return ""
        payload: dict[str, JsonValue] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return payload


class TimestampValue(CamelModel):
    type: Literal["timestamp"] = "timestamp"
    value: str

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class SinglePickValue(CamelModel):
    type: Literal["single-pick-vocabulary"] = "single-pick-vocabulary"
    value: str

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class MultiPickValue(CamelModel):
    type: Literal["multi-pick-vocabulary"] = "multi-pick-vocabulary"
    # An empty list means "nothing selected", which is legal for any param
    # whose spec allows it. Forbidding it here left callers no way to express
    # an empty selection, so they sent the literal string "[]" and vocabulary
    # matching rejected it. Required-ness is enforced per spec, not per type.
    values: list[str] = Field(default_factory=list)

    def to_wire(self) -> str:
        return json.dumps(self.values)

    def to_decoded(self) -> JsonValue:
        return list(self.values)


class InputDatasetValue(CamelModel):
    type: Literal["input-dataset"] = "input-dataset"
    dataset_id: str = Field(pattern=r"^([1-9][0-9]*)?$")

    def to_wire(self) -> str:
        return self.dataset_id

    def to_decoded(self) -> JsonValue:
        return self.dataset_id


class InputStepValue(CamelModel):
    type: Literal["input-step"] = "input-step"
    step_id: str = Field(pattern=r"^[0-9]*$")

    def to_wire(self) -> str:
        return self.step_id

    def to_decoded(self) -> JsonValue:
        return self.step_id


class HeldValue(CamelModel):
    type: Literal["held"] = "held"
    wire: str

    def to_wire(self) -> str:
        return self.wire

    def to_decoded(self) -> JsonValue:
        return self.wire


ParamValue = Annotated[
    StringValue
    | NumberValue
    | NumberRangeValue
    | DateValue
    | DateRangeValue
    | TimestampValue
    | SinglePickValue
    | MultiPickValue
    | FilterValue
    | InputDatasetValue
    | InputStepValue
    | HeldValue,
    Field(discriminator="type"),
]


_EMPTY_VALUES: dict[ParamKind, ParamValue] = {
    "string": StringValue(value=""),
    "number": NumberValue(value=None),
    "number-range": NumberRangeValue(),
    "date": DateValue(value=None),
    "date-range": DateRangeValue(),
    "timestamp": TimestampValue(value=""),
    "single-pick-vocabulary": SinglePickValue(value=""),
    "multi-pick-vocabulary": MultiPickValue(values=[]),
    "filter": FilterValue(empty=True),
    "input-dataset": InputDatasetValue(dataset_id=""),
    "input-step": InputStepValue(step_id=""),
}


def empty_value(kind: ParamKind) -> ParamValue:
    return _EMPTY_VALUES[kind]


def value_kind(value: ParamValue) -> ParamKind | None:
    match value:
        case HeldValue():
            return None
        case _:
            return value.type


def same_value(left: ParamValue, right: ParamValue) -> bool:
    match left, right:
        case MultiPickValue(values=held), MultiPickValue(values=read):
            return set(held) == set(read)
        case FilterValue(empty=False), FilterValue(empty=False):
            return left.clause_set == right.clause_set
        case _:
            return left == right
