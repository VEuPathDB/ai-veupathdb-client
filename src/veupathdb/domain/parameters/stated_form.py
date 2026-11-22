"""The stated form of a held value: the form the stated reader of its kind reads back."""

from __future__ import annotations

from pydantic import ConfigDict, JsonValue

from veupathdb.domain.parameters.decimals import decimal_text
from veupathdb.domain.parameters.filter_clause import (
    FilterClause,
    FilterProposal,
    FilterValue,
    MultiMembers,
    NumberMembers,
)
from veupathdb.domain.parameters.values import HeldValue, ParamValue
from veupathdb.model import CamelModel


class KeptValue(CamelModel):
    model_config = ConfigDict(frozen=True)
    wire: str


StatedForm = JsonValue | KeptValue


def _clause(clause: FilterClause) -> JsonValue:
    match clause:
        case MultiMembers():
            return None
        case NumberMembers(value=numbers):
            stated: JsonValue = [decimal_text(n) for n in numbers]
        case _:
            stated = clause.model_dump(mode="json", exclude_none=True)["value"]
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
    if not clauses or None in clauses:
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
