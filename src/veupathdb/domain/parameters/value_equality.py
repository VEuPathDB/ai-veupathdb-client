from __future__ import annotations

import json
from collections.abc import Mapping

from pydantic import ValidationError

from veupathdb.domain.parameters.filter_clause import FilterValue
from veupathdb.domain.parameters.phyletic_expression import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticExpression,
)
from veupathdb.domain.parameters.value_codec import from_wire, to_wire
from veupathdb.domain.parameters.values import (
    HeldValue,
    MultiPickValue,
    ParamKind,
    ParamValue,
)
from veupathdb.errors import VEuPathDBError


def declared_kind(value: ParamValue) -> ParamKind | None:
    match value:
        case HeldValue():
            return None
        case _:
            return value.type


def _expression(text: str) -> str:
    try:
        return PhyleticExpression.parse(text).render()
    except VEuPathDBError, ValidationError, RecursionError:
        return text


def _canonical(name: str, value: ParamValue) -> str:
    if name == PHYLETIC_EXPRESSION_PARAM:
        return _expression(to_wire(value))
    match value:
        case MultiPickValue(values=terms):
            return json.dumps(sorted(set(terms)))
        case FilterValue(empty=False) as filtered:
            return json.dumps(
                sorted(
                    [field, ranged, unknown, sorted(terms)]
                    for field, ranged, unknown, terms in filtered.clause_set
                )
            )
        case _:
            return to_wire(value)


def _in_kind(kind: ParamKind | None, value: ParamValue) -> ParamValue | None:
    if kind is None or value.type == kind:
        return value
    try:
        return from_wire(kind, to_wire(value))
    except ValidationError, ValueError, TypeError:
        return None


def param_value_key(name: str, kind: ParamKind | None, value: ParamValue) -> str:
    read = _in_kind(kind, value)
    if read is None:
        return json.dumps(["unread", value.type, to_wire(value)])
    return json.dumps([read.type, _canonical(name, read)])


def same_param_value(
    name: str, kind: ParamKind | None, left: ParamValue, right: ParamValue
) -> bool:
    return param_value_key(name, kind, left) == param_value_key(name, kind, right)


def same_as_wire(name: str, value: ParamValue, wire: str) -> bool:
    return same_param_value(name, declared_kind(value), value, HeldValue(wire=wire))


def same_param_values(
    left: Mapping[str, ParamValue], right: Mapping[str, ParamValue]
) -> bool:
    return left.keys() == right.keys() and not changed_param_names(left, right)


def changed_param_names(
    before: Mapping[str, ParamValue], after: Mapping[str, ParamValue]
) -> list[str]:
    return sorted(
        name
        for name in before.keys() | after.keys()
        if name not in before
        or name not in after
        or not same_param_value(name, None, before[name], after[name])
    )
