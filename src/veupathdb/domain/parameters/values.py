from __future__ import annotations

import json
from collections.abc import Hashable
from typing import Annotated, Literal, Self

from pydantic import Field, JsonValue, TypeAdapter, field_validator, model_validator

from veupathdb.domain.parameters.date_bounds import ISODate
from veupathdb.domain.parameters.decimals import decimal_text
from veupathdb.domain.parameters.filter_clause import FilterValue
from veupathdb.domain.parameters.value_base import HeldValue, KindValue

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


_ONE_TERM: TypeAdapter[list[str]] = TypeAdapter(list[str])
_Finite = Annotated[float, Field(allow_inf_nan=False)]


def _decoded_object(wire: str, kind: str) -> dict[str, JsonValue]:
    decoded: JsonValue = json.loads(wire) if wire else {}
    match decoded:
        case dict():
            return decoded
        case _:
            msg = f"{kind} wire payload must be a JSON object"
            raise TypeError(msg)


class StringValue(KindValue):
    type: Literal["string"] = "string"
    value: str

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls(value=wire)

    def identity(self) -> Hashable:
        return self.value

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class NumberValue(KindValue):
    type: Literal["number"] = "number"
    value: _Finite | None

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls(value=float(wire) if wire else None)

    def identity(self) -> Hashable:
        return self.value

    def to_wire(self) -> str:
        return "" if self.value is None else decimal_text(self.value)

    def to_decoded(self) -> JsonValue:
        return "" if self.value is None else self.value


class NumberRangeValue(KindValue):
    type: Literal["number-range"] = "number-range"
    min: _Finite | None = None
    max: _Finite | None = None

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls.model_validate(_decoded_object(wire, "number-range"))

    def identity(self) -> Hashable:
        return (self.min, self.max)

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


class DateValue(KindValue):
    type: Literal["date"] = "date"
    value: ISODate | None

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls(value=wire or None)

    def identity(self) -> Hashable:
        return self.value

    def to_wire(self) -> str:
        return self.value or ""

    def to_decoded(self) -> JsonValue:
        return self.value or ""


class DateRangeValue(KindValue):
    type: Literal["date-range"] = "date-range"
    min: ISODate | None = None
    max: ISODate | None = None

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls.model_validate(_decoded_object(wire, "date-range"))

    def identity(self) -> Hashable:
        return (self.min, self.max)

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


class TimestampValue(KindValue):
    type: Literal["timestamp"] = "timestamp"
    value: str

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls(value=wire)

    def identity(self) -> Hashable:
        return self.value

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class SinglePickValue(KindValue):
    type: Literal["single-pick-vocabulary"] = "single-pick-vocabulary"
    value: str

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        try:
            terms = _ONE_TERM.validate_json(wire) if wire.startswith("[") else [wire]
        except ValueError:
            terms = [wire]
        match terms:
            case []:
                return cls(value="")
            case [term]:
                return cls(value=term)
            case _:
                return cls(value=wire)

    def identity(self) -> Hashable:
        return self.value

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class MultiPickValue(KindValue):
    type: Literal["multi-pick-vocabulary"] = "multi-pick-vocabulary"
    # An empty list means "nothing selected", which is legal for any param
    # whose spec allows it. Forbidding it here left callers no way to express
    # an empty selection, so they sent the literal string "[]" and vocabulary
    # matching rejected it. Required-ness is enforced per spec, not per type.
    values: list[str] = Field(default_factory=list)

    __hash__ = KindValue.__hash__

    @field_validator("values")
    @classmethod
    def _each_term_once(cls, values: list[str]) -> list[str]:
        if len(set(values)) != len(values):
            msg = "a multi-pick names each term once"
            raise ValueError(msg)
        return values

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls(values=_ONE_TERM.validate_json(wire) if wire else [])

    def identity(self) -> Hashable:
        return frozenset(self.values)

    def to_wire(self) -> str:
        return json.dumps(self.values)

    def to_decoded(self) -> JsonValue:
        return list(self.values)


class InputDatasetValue(KindValue):
    type: Literal["input-dataset"] = "input-dataset"
    dataset_id: str = Field(pattern=r"^([1-9][0-9]*)?$")

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls(dataset_id=wire)

    def identity(self) -> Hashable:
        return self.dataset_id

    def to_wire(self) -> str:
        return self.dataset_id

    def to_decoded(self) -> JsonValue:
        return self.dataset_id


class InputStepValue(KindValue):
    type: Literal["input-step"] = "input-step"
    step_id: str = Field(pattern=r"^[0-9]*$")

    __hash__ = KindValue.__hash__

    @classmethod
    def from_wire(cls, wire: str) -> Self:
        return cls(step_id=wire)

    def identity(self) -> Hashable:
        return int(self.step_id) if self.step_id else None

    def to_wire(self) -> str:
        return self.step_id

    def to_decoded(self) -> JsonValue:
        return self.step_id


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
