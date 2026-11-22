from __future__ import annotations

from pydantic import ValidationError

from veupathdb.domain.parameters.phyletic_expression import (
    PHYLETIC_EXPRESSION_PARAM,
    PhyleticExpression,
)
from veupathdb.domain.parameters.value_codec import from_wire, to_wire
from veupathdb.domain.parameters.values import ParamKind, ParamValue
from veupathdb.errors import VEuPathDBError


def _parsed(text: str) -> PhyleticExpression | str:
    try:
        return PhyleticExpression.parse(text)
    except VEuPathDBError, ValidationError, RecursionError:
        return text


def _in_kind(kind: ParamKind | None, value: ParamValue) -> ParamValue | None:
    if kind is None or value.type == kind:
        return value
    try:
        return from_wire(kind, to_wire(value))
    except ValueError, TypeError:
        return None


def same_param_value(
    name: str, kind: ParamKind | None, left: ParamValue, right: ParamValue
) -> bool:
    if name == PHYLETIC_EXPRESSION_PARAM:
        return _parsed(to_wire(left)) == _parsed(to_wire(right))
    read_left, read_right = _in_kind(kind, left), _in_kind(kind, right)
    if read_left is None or read_right is None:
        return left.type == right.type and to_wire(left) == to_wire(right)
    return read_left == read_right
