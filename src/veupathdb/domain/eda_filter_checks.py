"""Why one entry of an EDA filter array will not mean what it says.

The shapes are structural, so this module imports no other layer.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from veupathdb.domain.eda_study import (
    CATEGORY_TYPE,
    EntityFacts,
    VariableFacts,
    listed,
    variable_by_id,
    vocabulary_of,
)

_MULTIFILTER_DISPLAY = "multifilter"
_MULTIFILTER_OPERATIONS = frozenset({"intersect", "union"})
_DATE_TIME_MARKER = "T"
_BARE_DATE_EXAMPLE = "2017-05-05T00:00:00"
_DEGENERATE_LONGITUDE = 1e-8

TYPES_FOR_FILTER: dict[str, frozenset[str]] = {
    "stringSet": frozenset({"string"}),
    "numberSet": frozenset({"number", "integer"}),
    "dateSet": frozenset({"date"}),
    "numberRange": frozenset({"number", "integer"}),
    "dateRange": frozenset({"date"}),
    "longitudeRange": frozenset({"longitude"}),
    "multiFilter": frozenset({CATEGORY_TYPE}),
}

DeclaredRanges = Mapping[tuple[str, str], tuple[float, float]]


class SubFilterFacts(Protocol):
    @property
    def variable_id(self) -> str: ...
    @property
    def string_set(self) -> Sequence[str]: ...


class FilterFacts(Protocol):
    @property
    def entity_id(self) -> str: ...
    @property
    def variable_id(self) -> str: ...
    @property
    def type(self) -> str: ...


@runtime_checkable
class StringSetFacts(FilterFacts, Protocol):
    @property
    def string_set(self) -> Sequence[str]: ...


@runtime_checkable
class NumberSetFacts(FilterFacts, Protocol):
    @property
    def number_set(self) -> Sequence[float]: ...


@runtime_checkable
class DateSetFacts(FilterFacts, Protocol):
    @property
    def date_set(self) -> Sequence[str]: ...


@runtime_checkable
class RangeBoundsFacts(FilterFacts, Protocol):
    @property
    def min(self) -> float | str | None: ...
    @property
    def max(self) -> float | str | None: ...


@runtime_checkable
class LongitudeBoundsFacts(FilterFacts, Protocol):
    @property
    def left(self) -> float | None: ...
    @property
    def right(self) -> float | None: ...


@runtime_checkable
class MultiFilterFacts(FilterFacts, Protocol):
    @property
    def operation(self) -> str: ...
    @property
    def sub_filters(self) -> Sequence[SubFilterFacts]: ...


@dataclass(frozen=True, slots=True)
class Site:
    """One filter with the entity and the variable it resolved to."""

    entry: FilterFacts
    entity: EntityFacts
    variable: VariableFacts
    declared_ranges: DeclaredRanges


def strings_of(entry: FilterFacts) -> Sequence[str]:
    match entry:
        case StringSetFacts():
            return entry.string_set
        case _:
            return ()


def _numbers(entry: FilterFacts) -> Sequence[float]:
    match entry:
        case NumberSetFacts():
            return entry.number_set
        case _:
            return ()


def _dates(entry: FilterFacts) -> Sequence[str]:
    match entry:
        case DateSetFacts():
            return entry.date_set
        case _:
            return ()


def _bounds(entry: FilterFacts) -> tuple[float | str | None, float | str | None]:
    match entry:
        case RangeBoundsFacts():
            return entry.min, entry.max
        case _:
            return None, None


def _longitude_bounds(entry: FilterFacts) -> tuple[float | None, float | None]:
    match entry:
        case LongitudeBoundsFacts():
            return entry.left, entry.right
        case _:
            return None, None


def _multi_filter(entry: FilterFacts) -> tuple[str, Sequence[SubFilterFacts]]:
    match entry:
        case MultiFilterFacts():
            return entry.operation, entry.sub_filters
        case _:
            return "", ()


def _as_number(value: float | str | None) -> float | None:
    match value:
        case int() | float():
            return float(value)
        case _:
            return None


def _as_text(value: float | str | None) -> str | None:
    match value:
        case str():
            return value
        case _:
            return None


def _at(site: Site) -> str:
    return (
        f"Filter {site.entry.type} on variable {site.variable.id} of entity "
        f"{site.entity.id}"
    )


def _wrong_variable_type(site: Site) -> list[str]:
    allowed = TYPES_FOR_FILTER[site.entry.type]
    if site.variable.type in allowed:
        return []
    return [
        f"{_at(site)} is refused: the variable type is {site.variable.type}, and "
        f"{site.entry.type} applies to a variable of type {listed(sorted(allowed))}."
    ]


def _string_set_errors(site: Site) -> list[str]:
    wrong = _wrong_variable_type(site)
    if wrong:
        return wrong
    values = strings_of(site.entry)
    if not values:
        return [
            f"{_at(site)} carries no members, and the service refuses an empty set."
        ]
    vocabulary = vocabulary_of(site.variable)
    if vocabulary is None:
        return []
    unknown = [value for value in values if value not in vocabulary]
    if not unknown:
        return []
    return [
        f"{_at(site)} names {listed(unknown)}, which the vocabulary does not "
        f"carry. The vocabulary is {listed(vocabulary)}. An unknown value returns "
        f"count 0 rather than an error."
    ]


def _number_set_errors(site: Site) -> list[str]:
    wrong = _wrong_variable_type(site)
    if wrong:
        return wrong
    values = _numbers(site.entry)
    if not values:
        return [
            f"{_at(site)} carries no members, and the service refuses an empty set."
        ]
    if site.variable.type != "integer":
        return []
    fractional = [value for value in values if not float(value).is_integer()]
    if not fractional:
        return []
    return [
        f"{_at(site)} names {listed(fractional)}, and the variable is an integer, "
        f"so every member must be whole."
    ]


def _date_set_errors(site: Site) -> list[str]:
    wrong = _wrong_variable_type(site)
    if wrong:
        return wrong
    values = _dates(site.entry)
    if not values:
        return [
            f"{_at(site)} carries no members, and the service refuses an empty set."
        ]
    bare = [value for value in values if _DATE_TIME_MARKER not in value]
    if not bare:
        return []
    return [
        f"{_at(site)} names {listed(bare)} without a time part. Write every member "
        f"as YYYY-MM-DDTHH:mm:ss, for example {bare[0]}T00:00:00."
    ]


def _number_range_errors(site: Site) -> list[str]:
    wrong = _wrong_variable_type(site)
    if wrong:
        return wrong
    low_bound, high_bound = _bounds(site.entry)
    low = _as_number(low_bound)
    high = _as_number(high_bound)
    if low is None or high is None:
        return [f"{_at(site)} needs a numeric min and a numeric max."]
    if low > high:
        return [
            f"{_at(site)} has min {low} above max {high}, which returns count 0 "
            f"rather than an error."
        ]
    return _outside_declared_range(site, low, high)


def _outside_declared_range(site: Site, low: float, high: float) -> list[str]:
    key = (site.entity.id, site.variable.id)
    if key not in site.declared_ranges:
        return []
    range_min, range_max = site.declared_ranges[key]
    outside = [bound for bound in (low, high) if bound < range_min or bound > range_max]
    if not outside:
        return []
    return [
        f"{_at(site)} has {listed(outside)} outside the declared range "
        f"{range_min} to {range_max}."
    ]


def _date_range_errors(site: Site) -> list[str]:
    wrong = _wrong_variable_type(site)
    if wrong:
        return wrong
    low_bound, high_bound = _bounds(site.entry)
    low = _as_text(low_bound)
    high = _as_text(high_bound)
    if low is None or high is None:
        return [
            f"{_at(site)} needs a min and a max written as YYYY-MM-DDTHH:mm:ss, "
            f"for example {_BARE_DATE_EXAMPLE}."
        ]
    bare = [
        f"{_at(site)} has the bound {bound} without a time part. Write it as "
        f"{bound}T00:00:00."
        for bound in (low, high)
        if _DATE_TIME_MARKER not in bound
    ]
    if bare:
        return bare
    if low > high:
        return [
            f"{_at(site)} has min {low} above max {high}, which returns count 0 "
            f"rather than an error."
        ]
    return []


def _longitude_range_errors(site: Site) -> list[str]:
    wrong = _wrong_variable_type(site)
    if wrong:
        return wrong
    left, right = _longitude_bounds(site.entry)
    if left is None or right is None:
        return [f"{_at(site)} needs a numeric left and a numeric right."]
    if abs(left - right) >= _DEGENERATE_LONGITUDE:
        return []
    return [
        f"{_at(site)} has left {left} equal to right {right} within "
        f"{_DEGENERATE_LONGITUDE}, and the service reads an equal pair as a no-op "
        f"that keeps every row."
    ]


def _multi_filter_errors(site: Site) -> list[str]:
    wrong = _wrong_multifilter_target(site)
    if wrong:
        return wrong
    operation, sub_filters = _multi_filter(site.entry)
    if not sub_filters:
        return [f"{_at(site)} carries no subFilters, which the service refuses."]
    if operation not in _MULTIFILTER_OPERATIONS:
        return [
            f"{_at(site)} names operation {operation}, and the service accepts "
            f"{listed(sorted(_MULTIFILTER_OPERATIONS))}."
        ]
    return [error for sub in sub_filters for error in _sub_filter_errors(site, sub)]


def _wrong_multifilter_target(site: Site) -> list[str]:
    is_category = site.variable.type in TYPES_FOR_FILTER["multiFilter"]
    if is_category and site.variable.display_type == _MULTIFILTER_DISPLAY:
        return []
    return [
        f"{_at(site)} is refused: the target must be a category variable whose "
        f"displayType is {_MULTIFILTER_DISPLAY}, and this variable is type "
        f"{site.variable.type} with displayType {site.variable.display_type}."
    ]


def _sub_filter_errors(site: Site, sub: SubFilterFacts) -> list[str]:
    child = variable_by_id(site.entity, sub.variable_id)
    if child is None or child.parent_id != site.variable.id:
        children = [
            variable.id
            for variable in site.entity.variables
            if variable.parent_id == site.variable.id
        ]
        return [
            f"{_at(site)} names sub-filter variable {sub.variable_id}, which is not "
            f"a child of that category. Its children are {listed(children)}."
        ]
    if not sub.string_set:
        return [
            f"{_at(site)} gives sub-filter variable {sub.variable_id} no members, "
            f"and the service refuses an empty set."
        ]
    vocabulary = vocabulary_of(child)
    if vocabulary is None:
        return []
    unknown = [value for value in sub.string_set if value not in vocabulary]
    if not unknown:
        return []
    return [
        f"{_at(site)} gives sub-filter variable {sub.variable_id} the values "
        f"{listed(unknown)}, which its vocabulary does not carry. The vocabulary "
        f"is {listed(vocabulary)}."
    ]


CHECKS: dict[str, Callable[[Site], list[str]]] = {
    "stringSet": _string_set_errors,
    "numberSet": _number_set_errors,
    "dateSet": _date_set_errors,
    "numberRange": _number_range_errors,
    "dateRange": _date_range_errors,
    "longitudeRange": _longitude_range_errors,
    "multiFilter": _multi_filter_errors,
}
