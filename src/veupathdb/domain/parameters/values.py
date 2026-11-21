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
    value: float

    def to_wire(self) -> str:
        return decimal_text(self.value)

    def to_decoded(self) -> JsonValue:
        return self.value


class NumberRangeValue(CamelModel):
    type: Literal["number-range"] = "number-range"
    min: float | None = None
    max: float | None = None

    @model_validator(mode="after")
    def _at_least_one_endpoint(self) -> NumberRangeValue:
        if self.min is None and self.max is None:
            msg = "number-range requires at least one of min/max"
            raise ValueError(msg)
        if self.min is not None and self.max is not None and self.min > self.max:
            msg = f"number-range min ({self.min}) > max ({self.max})"
            raise ValueError(msg)
        return self

    def to_wire(self) -> str:
        payload: dict[str, float] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return json.dumps(payload)

    def to_decoded(self) -> JsonValue:
        payload: dict[str, JsonValue] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return payload


class DateValue(CamelModel):
    type: Literal["date"] = "date"
    value: ISODate

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class DateRangeValue(CamelModel):
    type: Literal["date-range"] = "date-range"
    min: ISODate | None = None
    max: ISODate | None = None

    @model_validator(mode="after")
    def _at_least_one_endpoint(self) -> DateRangeValue:
        if self.min is None and self.max is None:
            msg = "date-range requires at least one of min/max"
            raise ValueError(msg)
        return self

    def to_wire(self) -> str:
        payload: dict[str, str] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return json.dumps(payload)

    def to_decoded(self) -> JsonValue:
        payload: dict[str, JsonValue] = {}
        if self.min is not None:
            payload["min"] = self.min
        if self.max is not None:
            payload["max"] = self.max
        return payload


class TimestampValue(CamelModel):
    type: Literal["timestamp"] = "timestamp"
    value: str = Field(min_length=1)

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class SinglePickValue(CamelModel):
    type: Literal["single-pick-vocabulary"] = "single-pick-vocabulary"
    value: str = Field(min_length=1)

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
    dataset_id: str = Field(pattern=r"^[1-9][0-9]*$")

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
    | InputStepValue,
    Field(discriminator="type"),
]
