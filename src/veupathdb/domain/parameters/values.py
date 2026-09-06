from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import Field, JsonValue, RootModel, model_validator

from veupathdb.domain.parameters.date_bounds import WDKDateBound
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
        if self.value.is_integer():
            return str(int(self.value))
        return str(self.value)

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
    value: str = Field(min_length=1)

    def to_wire(self) -> str:
        return self.value

    def to_decoded(self) -> JsonValue:
        return self.value


class DateRangeValue(CamelModel):
    type: Literal["date-range"] = "date-range"
    min: WDKDateBound | None = None
    max: WDKDateBound | None = None

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


class FilterClauseTerms(RootModel[frozenset[str]]):
    """The values one filter clause states, as a set.

    A membership clause carries a list of terms and a range clause carries an
    object with its bounds. Neither states an order.
    """

    @model_validator(mode="before")
    @classmethod
    def _as_terms(cls, raw: JsonValue) -> JsonValue:
        if isinstance(raw, dict):
            return [f"{key}={value}" for key, value in raw.items()]
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return [] if raw is None else [str(raw)]


FilterClauseKey = tuple[str, bool, bool, frozenset[str]]
"""One clause by what it states: its field, its two flags, and its values."""


class FilterTermClause(CamelModel):
    """One faceted clause of a WDK filter value. Keys mirror wdk-client's
    authoritative ``BaseFilter`` (field/type/isRange/includeUnknown/value);
    parsing ignores extra keys (e.g. ``fieldDisplayName``) and emits only these."""

    field: str
    type: str = "string"
    is_range: bool = False
    include_unknown: bool = False
    value: JsonValue = Field(default_factory=list)

    @property
    def comparable(self) -> FilterClauseKey:
        """The clause by what it states, not by how it was serialized.

        ``type`` is a property of the field rather than of the selection, so
        it is left out.
        """
        return (
            self.field,
            self.is_range,
            self.include_unknown,
            FilterClauseTerms.model_validate(self.value).root,
        )


class FilterValue(CamelModel):
    type: Literal["filter"] = "filter"
    filters: list[FilterTermClause] = Field(default_factory=list)

    def to_wire(self) -> str:
        return json.dumps(
            {
                "filters": [
                    c.model_dump(by_alias=True, mode="json") for c in self.filters
                ]
            },
        )

    def to_decoded(self) -> JsonValue:
        return {
            "filters": [c.model_dump(by_alias=True, mode="json") for c in self.filters],
        }

    @property
    def clause_set(self) -> frozenset[FilterClauseKey]:
        """The clauses this value states. Their order is not part of it."""
        return frozenset(clause.comparable for clause in self.filters)


class InputDatasetValue(CamelModel):
    type: Literal["input-dataset"] = "input-dataset"
    dataset_id: str = Field(min_length=1)

    def to_wire(self) -> str:
        return self.dataset_id

    def to_decoded(self) -> JsonValue:
        return self.dataset_id


class InputStepValue(CamelModel):
    type: Literal["input-step"] = "input-step"
    step_id: str = Field(min_length=1)

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
