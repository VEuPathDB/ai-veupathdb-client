"""How a caller's stated value of one WDK parameter is read, by the parameter's kind."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Protocol

import pydantic
from pydantic import (
    AfterValidator,
    ConfigDict,
    Field,
    JsonValue,
    TypeAdapter,
    WithJsonSchema,
    create_model,
)

from veupathdb.domain.parameters.date_bounds import ISODate
from veupathdb.domain.parameters.filter_clause import (
    FilterFacets,
    FilterProposal,
    FilterProposals,
)
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
    decimal_text,
)
from veupathdb.domain.parameters.wdk_vocab import (
    WDKFilterOntologyTerm,
    WDKVocabulary,
    flatten_vocab,
)
from veupathdb.errors import ValidationError

Stated = ParamValue | FilterProposals

_MAX_ENUM_TERMS = 50
_MODEL_KINDS = frozenset({"number-range", "date-range", "filter"})
_STRICT = ConfigDict(strict=True, extra="forbid")


class StatedDeclaration(Protocol):
    @property
    def name(self) -> str: ...
    @property
    def type(self) -> ParamKind: ...
    @property
    def is_number(self) -> bool: ...
    @property
    def length(self) -> int: ...
    @property
    def min(self) -> float | None: ...
    @property
    def max(self) -> float | None: ...
    @property
    def min_date(self) -> str | None: ...
    @property
    def max_date(self) -> str | None: ...
    @property
    def vocabulary(self) -> WDKVocabulary | None: ...
    @property
    def display_type(self) -> str: ...
    @property
    def ontology(self) -> Sequence[WDKFilterOntologyTerm]: ...
    @property
    def values(self) -> dict[str, list[str]] | None: ...


@dataclass(frozen=True)
class StatedFault:
    name: str
    read: JsonValue
    text: str


class StatedValuesError(ValidationError):
    def __init__(self, faults: list[StatedFault]) -> None:
        self.faults = faults
        super().__init__(
            title="Invalid parameter value",
            detail=" ".join(fault.text for fault in faults),
            errors=[{"param": fault.name, "detail": fault.text} for fault in faults],
        )


@dataclass(frozen=True)
class _Declared:
    name: str
    kind: ParamKind
    is_number: bool
    length: int
    low: float | None
    high: float | None
    low_date: str | None
    high_date: str | None
    terms: tuple[str, ...] | None
    first_term: str
    facets: tuple[str, ...]


@dataclass(frozen=True)
class StatedReading:
    name: str
    adapter: TypeAdapter[Stated]
    shape: str
    example: JsonValue

    def read(self, raw: JsonValue) -> Stated:
        try:
            return self.adapter.validate_python(raw)
        except pydantic.ValidationError:
            text = f"{self.name} takes {self.shape}, for example {self.example!r}; it read {raw!r}."
            raise StatedValuesError([StatedFault(self.name, raw, text)]) from None


def _limits(low: str | None, high: str | None) -> str:
    return "".join(
        part
        for part, bound in ((f" from {low}", low), (f" to {high}", high))
        if bound is not None
    )


def _number_limits(d: _Declared) -> str:
    low, high = (None if b is None else decimal_text(b) for b in (d.low, d.high))
    return _limits(low, high)


def _within_dates(low: str | None, high: str | None) -> Callable[[str], str]:
    def check(day: str) -> str:
        if (low is not None and day < low) or (high is not None and day > high):
            msg = f"{day} is outside{_limits(low, high)}"
            raise ValueError(msg)
        return day

    return check


@dataclass(frozen=True)
class _Shape:
    stated: Any
    to_value: Callable[[Any], Stated]
    text: str
    example: JsonValue


def _number(d: _Declared) -> Any:
    return Annotated[float, Field(ge=d.low, le=d.high, allow_inf_nan=False)]


def _day(d: _Declared) -> Any:
    return Annotated[
        ISODate,
        Field(json_schema_extra={"format": "date"}),
        AfterValidator(_within_dates(d.low_date, d.high_date)),
    ]


def _range(d: _Declared, end: Any, low: object, high: object) -> Any:
    fields: dict[str, Any] = {
        side: (end, ... if limit is None else limit)
        for side, limit in (("min", low), ("max", high))
    }
    return create_model(d.name, __config__=_STRICT, **fields)


def _lowest(d: _Declared) -> float:
    return d.low if d.low is not None else 0.0


def _first_day(d: _Declared) -> str:
    return d.low_date or d.high_date or "2020-01-01"


def _number_text(length: int) -> Callable[[float | str], StringValue]:
    def text(v: float | str) -> StringValue:
        written = decimal_text(float(v))
        if length and len(written) > length:
            msg = f"{written} is longer than {length} characters"
            raise ValueError(msg)
        return StringValue(value=written)

    return text


def _string(d: _Declared) -> _Shape:
    limit = f" of at most {d.length} characters" if d.length else ""
    if d.is_number:
        decimal: Any = Annotated[str, Field(pattern=r"^-?([0-9]+\.?[0-9]*|\.[0-9]+)$")]
        finite: Any = Annotated[float, Field(allow_inf_nan=False)]
        return _Shape(finite | decimal, _number_text(d.length), f"a number{limit}", 5)
    return _Shape(
        Annotated[str, Field(max_length=d.length or None)],
        lambda v: StringValue(value=v),
        f"a string{limit}",
        "text",
    )


def _number_value(d: _Declared) -> _Shape:
    return _Shape(
        _number(d),
        lambda v: NumberValue(value=v),
        f"a number{_number_limits(d)}",
        _lowest(d),
    )


def _number_range(d: _Declared) -> _Shape:
    lowest = _lowest(d)
    return _Shape(
        _range(d, _number(d), d.low, d.high),
        lambda v: NumberRangeValue(min=v.min, max=v.max),
        f'{{"min": number, "max": number}}{_number_limits(d)}',
        {"min": lowest, "max": d.high if d.high is not None else lowest + 1},
    )


def _date(d: _Declared) -> _Shape:
    return _Shape(
        _day(d),
        lambda v: DateValue(value=v),
        f"yyyy-mm-dd{_limits(d.low_date, d.high_date)}",
        _first_day(d),
    )


def _date_range(d: _Declared) -> _Shape:
    first = _first_day(d)
    return _Shape(
        _range(d, _day(d), d.low_date, d.high_date),
        lambda v: DateRangeValue(min=v.min, max=v.max),
        f'{{"min": yyyy-mm-dd, "max": yyyy-mm-dd}}{_limits(d.low_date, d.high_date)}',
        {"min": first, "max": d.high_date or first},
    )


def _timestamp(_: _Declared) -> _Shape:
    return _Shape(
        Annotated[str, Field(min_length=1)],
        lambda v: TimestampValue(value=v),
        "a non-empty string",
        "2020-01-01T00:00:00",
    )


def _term(d: _Declared) -> tuple[Any, str]:
    if d.terms is None:
        return Annotated[str, Field(min_length=1)], ""
    terms = d.terms

    def member(term: str) -> str:
        if term not in terms:
            msg = f"{term!r} is not a term"
            raise ValueError(msg)
        return term

    return (
        Annotated[
            str, Field(json_schema_extra={"enum": list(terms)}), AfterValidator(member)
        ],
        ", ".join(repr(term) for term in terms),
    )


def _single_pick(d: _Declared) -> _Shape:
    term, listed = _term(d)
    return _Shape(
        term,
        lambda v: SinglePickValue(value=v),
        f"one of {listed}" if listed else "one vocabulary term",
        d.first_term,
    )


def _multi_pick(d: _Declared) -> _Shape:
    term, listed = _term(d)
    return _Shape(
        list.__class_getitem__(term),
        lambda v: MultiPickValue(values=v),
        f"a list of terms from {listed}" if listed else "a list of vocabulary terms",
        [d.first_term],
    )


def _listed(item: Any) -> Any:
    return Annotated[list[item], *FilterProposals.model_fields["root"].metadata]


def _filter(d: _Declared) -> _Shape:
    facet = Annotated[str, Field(json_schema_extra={"enum": list(d.facets)})]
    item = create_model(d.name, __base__=FilterProposal, field=(facet, ...))
    inline = Annotated[item, WithJsonSchema(item.model_json_schema())]
    schema = TypeAdapter(_listed(inline)).json_schema()
    return _Shape(
        Annotated[FilterProposals, WithJsonSchema(schema)],
        lambda v: v,
        'a list of {"field": <facet>, "value": <members or {"min", "max"}>}',
        [{"field": "<facet>", "value": ["<member>"]}],
    )


def _input_dataset(_: _Declared) -> _Shape:
    return _Shape(
        int | Annotated[str, *InputDatasetValue.model_fields["dataset_id"].metadata],
        lambda v: InputDatasetValue(dataset_id=str(v)),
        "a positive integer dataset id",
        123,
    )


def _input_step(_: _Declared) -> _Shape:
    return _Shape(
        Annotated[str, *InputStepValue.model_fields["step_id"].metadata],
        lambda v: InputStepValue(step_id=v),
        '"" or an integer step id',
        "",
    )


_SHAPES: dict[ParamKind, Callable[[_Declared], _Shape]] = {
    "string": _string,
    "number": _number_value,
    "number-range": _number_range,
    "date": _date,
    "date-range": _date_range,
    "timestamp": _timestamp,
    "single-pick-vocabulary": _single_pick,
    "multi-pick-vocabulary": _multi_pick,
    "filter": _filter,
    "input-dataset": _input_dataset,
    "input-step": _input_step,
}


@lru_cache(maxsize=4096)
def _reading(d: _Declared) -> StatedReading:
    shape = _SHAPES[d.kind](d)
    config = None if d.kind in _MODEL_KINDS else _STRICT
    adapter: TypeAdapter[Stated] = TypeAdapter(
        Annotated[shape.stated, AfterValidator(shape.to_value)], config=config
    )
    return StatedReading(d.name, adapter, shape.text, shape.example)


def _enum_terms(param: StatedDeclaration) -> tuple[str, ...] | None:
    vocabulary = param.vocabulary
    if (
        not isinstance(vocabulary, list)
        or len(vocabulary) > _MAX_ENUM_TERMS
        or param.display_type == "typeAhead"
        or any(entry.parent is not None for entry in vocabulary)
    ):
        return None
    return tuple(entry.term for entry in vocabulary)


def stated_reading(param: StatedDeclaration) -> StatedReading:
    options = flatten_vocab(param.vocabulary)
    return _reading(
        _Declared(
            name=param.name,
            kind=param.type,
            is_number=param.is_number,
            length=param.length,
            low=param.min,
            high=param.max,
            low_date=param.min_date,
            high_date=param.max_date,
            terms=_enum_terms(param),
            first_term=options[0].value if options else "term",
            facets=tuple(
                dict.fromkeys(
                    name
                    for facet in FilterFacets.of(param).root
                    for name in (facet.term, facet.display)
                )
            ),
        )
    )


def read_stated_values(
    params: Sequence[StatedDeclaration], stated: Mapping[str, JsonValue]
) -> dict[str, Stated]:
    read: dict[str, Stated] = {}
    faults: list[StatedFault] = []
    for param in params:
        if param.name not in stated:
            continue
        try:
            read[param.name] = stated_reading(param).read(stated[param.name])
        except StatedValuesError as refusal:
            faults.extend(refusal.faults)
    if faults:
        raise StatedValuesError(faults)
    return read
