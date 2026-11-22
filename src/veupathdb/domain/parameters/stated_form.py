"""The stated form of a held value: the form the stated reader of its kind reads back."""

from __future__ import annotations

import json

from pydantic import ConfigDict, JsonValue

from veupathdb.domain.parameters.filter_clause import (
    FilterClause,
    FilterProposal,
    FilterValue,
    MultiMembers,
)
from veupathdb.domain.parameters.value_base import HeldValue
from veupathdb.domain.parameters.values import ParamValue
from veupathdb.model import CamelModel


class KeptValue(CamelModel):
    model_config = ConfigDict(frozen=True)
    wire: str


StatedForm = JsonValue | KeptValue


def _clause(clause: FilterClause) -> JsonValue:
    match clause:
        case MultiMembers():
            return None
        case _:
            stated: JsonValue = clause.model_dump(mode="json", exclude_none=True)[
                "value"
            ]
    proposal = FilterProposal.model_validate(
        {
            "field": clause.field,
            "value": stated,
            "includeUnknown": clause.include_unknown,
        }
    )
    return proposal.model_dump(by_alias=True, mode="json", exclude_defaults=True)


def _filter(value: FilterValue) -> StatedForm:
    if value.empty:
        return ""
    clauses = [_clause(clause) for clause in value.filters]
    if None in clauses:
        return KeptValue(wire=value.to_wire())
    return clauses


def stated_form(value: ParamValue) -> StatedForm:
    match value:
        case HeldValue(wire=wire):
            return KeptValue(wire=wire)
        case FilterValue():
            return _filter(value)
        case _:
            return value.to_decoded()


KEPT_MARK = "(kept as the site holds it)"


def shown_stated(value: ParamValue) -> JsonValue:
    match stated_form(value):
        case KeptValue(wire=wire):
            return f"{wire!r} {KEPT_MARK}"
        case form:
            return form


def shown_stated_text(value: ParamValue) -> str:
    match stated_form(value):
        case KeptValue():
            return str(shown_stated(value))
        case form:
            return json.dumps(form)


def restates(value: ParamValue, stated: JsonValue) -> bool:
    match stated_form(value):
        case KeptValue(wire=wire):
            return stated in (wire, shown_stated(value))
        case form:
            return stated == form
