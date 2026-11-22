from __future__ import annotations

import json

from pydantic import ValidationError

from veupathdb.domain.parameters.filter_clause import FilterValue
from veupathdb.domain.parameters.phyletic_expression import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticExpression,
)
from veupathdb.domain.parameters.value_codec import from_wire_as, to_wire
from veupathdb.domain.parameters.values import MultiPickValue, ParamValue, same_value
from veupathdb.errors import VEuPathDBError


def _parsed(text: str) -> PhyleticExpression | str:
    try:
        return PhyleticExpression.parse(text)
    except VEuPathDBError, ValidationError, RecursionError:
        return text


def _expression(text: str) -> str:
    match _parsed(text):
        case PhyleticExpression() as parsed:
            return parsed.render()
        case written:
            return written


def same_param_value(name: str, left: ParamValue, right: ParamValue) -> bool:
    if name == PHYLETIC_EXPRESSION_PARAM:
        return _parsed(to_wire(left)) == _parsed(to_wire(right))
    if left.type == right.type:
        return same_value(left, right)
    return same_as_wire(name, left, to_wire(right)) or same_as_wire(
        name, right, to_wire(left)
    )


def same_as_wire(name: str, held: ParamValue, wire: str) -> bool:
    try:
        read = from_wire_as(held, wire)
    except ValidationError, ValueError, TypeError:
        return False
    return read.type == held.type and same_param_value(name, held, read)


def param_value_key(name: str, value: ParamValue) -> str:
    if name == PHYLETIC_EXPRESSION_PARAM:
        return _expression(to_wire(value))
    match value:
        case MultiPickValue(values=terms):
            return json.dumps(sorted(set(terms)))
        case FilterValue(empty=False) as filtered:
            keys = sorted(
                [field, ranged, unknown, sorted(terms)]
                for field, ranged, unknown, terms in filtered.clause_set
            )
            return json.dumps(keys)
        case _:
            return to_wire(value)
