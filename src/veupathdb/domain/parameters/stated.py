"""How a caller's stated value of one WDK parameter is read, by the parameter's kind."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Annotated, Any, Literal, Protocol

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
from veupathdb.domain.parameters.decimals import decimal_text
from veupathdb.domain.parameters.filter_clause import (
    FilterFacets,
    FilterProposal,
    FilterProposals,
)
from veupathdb.domain.parameters.specs import accepts_empty
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
    empty_value,
)
from veupathdb.domain.parameters.vocab_lookup import (
    Resolution,
    VocabularyEntryError,
    entries_or_refusal,
    entry_fault,
)
from veupathdb.domain.parameters.wdk_vocab import (
    VocabOption,
    WDKFilterOntologyTerm,
    WDKVocabulary,
    flatten_vocab,
)
from veupathdb.errors import ValidationError

Stated = ParamValue | FilterProposals

_MAX_ENUM_TERMS = 50
_WDK_NUMBER = r"^[+-]?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?$"
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
    def allow_empty_value(self) -> bool: ...
    @property
    def min_selected_count(self) -> int: ...
    @property
    def max_selected_count(self) -> int | None: ...
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
    allow_empty: bool
    fewest: int
    most: int | None
    length: int
    low: float | None
    high: float | None
    low_date: str | None
    high_date: str | None
    terms: tuple[str, ...] | None
    entries: tuple[tuple[str, str], ...]
    first_term: str
    facets: tuple[str, ...]


@dataclass(frozen=True)
class StatedReading:
    name: str
    adapter: TypeAdapter[Stated]
    shape: str
    example: JsonValue
    refused_empties: tuple[JsonValue, ...]
    entries: tuple[tuple[str, str], ...]

    def read(self, raw: JsonValue) -> Stated:
        return self.named(self.read_shape(raw))

    def read_shape(self, raw: JsonValue) -> Stated:
        if raw in self.refused_empties:
            raise empty_refusal(self.name, raw)
        try:
            return self.adapter.validate_python(raw)
        except pydantic.ValidationError:
            text = f"{self.name} takes {self.shape}, for example {self.example!r}; it read {raw!r}."
            raise StatedValuesError([StatedFault(self.name, raw, text)]) from None

    def named(self, read: Stated) -> Stated:
        match read:
            case SinglePickValue(value=term) if term:
                [entry] = self._entries([term])
                return SinglePickValue(value=entry)
            case MultiPickValue(values=terms) if terms:
                return MultiPickValue(values=self._entries(terms))
            case _:
                return read

    def _entries(self, terms: list[str]) -> list[str]:
        options = [VocabOption(value=v, display=d) for v, d in self.entries]
        return entries_or_refusal(self.name, options, terms)


def empty_refusal(name: str, raw: JsonValue) -> StatedValuesError:
    text = f"{name} takes a value, not the empty value {raw!r}."
    return StatedValuesError([StatedFault(name, raw, text)])


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
        match v:
            case str():
                written = v
            case _:
                written = decimal_text(v)
        if length and len(written) > length:
            msg = f"{written} is longer than {length} characters"
            raise ValueError(msg)
        return StringValue(value=written)

    return text


def _string(d: _Declared) -> _Shape:
    limit = f" of at most {d.length} characters" if d.length else ""
    if d.is_number:
        decimal: Any = Annotated[str, Field(pattern=_WDK_NUMBER)]
        finite: Any = Annotated[float, Field(allow_inf_nan=False)]
        return _Shape(finite | decimal, _number_text(d.length), f"a number{limit}", 5)
    return _Shape(
        Annotated[str, Field(min_length=1, max_length=d.length or None)],
        lambda v: StringValue(value=v),
        f"a non-empty string{limit}",
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
    return (
        Annotated[str, Field(json_schema_extra={"enum": list(d.terms)})],
        ", ".join(repr(term) for term in d.terms),
    )


def _single_pick(d: _Declared) -> _Shape:
    term, listed = _term(d)
    return _Shape(
        term,
        lambda v: SinglePickValue(value=v),
        f"one of {listed}" if listed else "one vocabulary term",
        d.first_term,
    )


def _how_many(fewest: int, most: int | None) -> str:
    if most == fewest:
        return f" (exactly {fewest})"
    if most is not None:
        return f" ({fewest} to {most})"
    return f" (at least {fewest})" if fewest > 1 else ""


def _multi_pick(d: _Declared) -> _Shape:
    term: Any
    term, listed = _term(d)
    terms = f"a list of terms from {listed}" if listed else "a list of vocabulary terms"
    return _Shape(
        Annotated[list[term], Field(min_length=d.fewest, max_length=d.most)],
        lambda v: MultiPickValue(values=v),
        f"{terms}{_how_many(d.fewest, d.most)}",
        [d.first_term],
    )


def _filter(d: _Declared) -> _Shape:
    facet = Annotated[str, Field(json_schema_extra={"enum": list(d.facets)})]
    item = create_model(d.name, __base__=FilterProposal, field=(facet, ...))
    inline = Annotated[item, WithJsonSchema(item.model_json_schema())]
    schema = TypeAdapter(list[inline]).json_schema()
    return _Shape(
        Annotated[FilterProposals, WithJsonSchema(schema)],
        lambda v: v,
        'a list of {"field": <facet>, "value": <members or {"min", "max"}>}, '
        "or [] for no filter",
        [{"field": "<facet>", "value": ["<member>"]}],
    )


def _input_dataset(_: _Declared) -> _Shape:
    return _Shape(
        int | Annotated[str, Field(pattern=r"^[1-9][0-9]*$")],
        lambda v: InputDatasetValue(dataset_id=str(v)),
        "a positive integer dataset id",
        123,
    )


def _input_step(_: _Declared) -> _Shape:
    return _Shape(
        Annotated[str, Field(pattern=r"^[0-9]+$")],
        lambda v: InputStepValue(step_id=v),
        "an integer step id",
        "12",
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


_NO_TERMS = Annotated[list[str], Field(max_length=0)]


def _with_empty(d: _Declared, shape: _Shape) -> _Shape:
    if not d.allow_empty:
        return shape
    empty = empty_value(d.kind)
    picks = d.kind == "multi-pick-vocabulary"
    unset: Any = Literal[""] | _NO_TERMS if picks else Literal[""]
    empties: tuple[JsonValue, ...] = ("", []) if picks else ("",)
    return _Shape(
        shape.stated | unset,
        lambda v: empty if v in empties else shape.to_value(v),
        f'{shape.text}, or "" to leave it empty',
        shape.example,
    )


@lru_cache(maxsize=4096)
def _reading(d: _Declared) -> StatedReading:
    shape = _with_empty(d, _SHAPES[d.kind](d))
    config = None if d.kind in _MODEL_KINDS else _STRICT
    adapter: TypeAdapter[Stated] = TypeAdapter(
        Annotated[shape.stated, AfterValidator(shape.to_value)], config=config
    )
    empties: tuple[JsonValue, ...] = (
        ()
        if d.allow_empty
        else ("", [])
        if d.kind == "multi-pick-vocabulary"
        else ("",)
    )
    return StatedReading(d.name, adapter, shape.text, shape.example, empties, d.entries)


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
            allow_empty=accepts_empty(param),
            fewest=max(param.min_selected_count, 1),
            most=param.max_selected_count,
            length=param.length,
            low=param.min,
            high=param.max,
            low_date=param.min_date,
            high_date=param.max_date,
            terms=_enum_terms(param),
            entries=tuple((o.value, o.display) for o in options),
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
    shapes: dict[str, Stated] = {}
    shape_faults: list[StatedFault] = []
    for param in params:
        if param.name not in stated:
            continue
        try:
            shapes[param.name] = stated_reading(param).read_shape(stated[param.name])
        except StatedValuesError as refusal:
            shape_faults.extend(refusal.faults)
    read: dict[str, Stated] = {}
    entry_faults: list[tuple[str, Resolution]] = []
    for param in params:
        if param.name not in shapes:
            continue
        try:
            read[param.name] = stated_reading(param).named(shapes[param.name])
        except VocabularyEntryError as refusal:
            entry_faults.extend(refusal.faults)
    if shape_faults:
        raise StatedValuesError(
            [
                *shape_faults,
                *(StatedFault(p, r.phrase, entry_fault(p, r)) for p, r in entry_faults),
            ]
        )
    if entry_faults:
        raise VocabularyEntryError(entry_faults)
    return read
