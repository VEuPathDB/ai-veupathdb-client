"""Conversion between a typed ``ParamValue`` and WDK's wire and decoded forms."""

import json
from collections.abc import Callable

from pydantic import JsonValue, TypeAdapter
from pydantic import ValidationError as PydanticValidationError

from veupathdb.domain.parameters.values import (
    HeldValue,
    ParamKind,
    ParamValue,
)

_PARAM_VALUE_ADAPTER: TypeAdapter[ParamValue] = TypeAdapter(ParamValue)
_PARAM_KIND_ADAPTER: TypeAdapter[ParamKind] = TypeAdapter(ParamKind)


def as_param_kind(raw: str) -> ParamKind:
    return _PARAM_KIND_ADAPTER.validate_python(raw)


def _decoded_object(wire: str, kind: str) -> dict[str, JsonValue]:
    decoded: JsonValue = json.loads(wire) if wire else {}
    if not isinstance(decoded, dict):
        msg = f"{kind} wire payload must be a JSON object"
        raise TypeError(msg)
    return decoded


def _multi_pick_payload(w: str) -> dict[str, JsonValue]:
    return {
        "type": "multi-pick-vocabulary",
        "values": list(json.loads(w)) if w else [],
    }


_ONE_TERM: TypeAdapter[list[str]] = TypeAdapter(list[str])


def _single_pick_payload(w: str) -> dict[str, JsonValue]:
    try:
        terms = _ONE_TERM.validate_json(w) if w.startswith("[") else [w]
    except PydanticValidationError:
        terms = [w]
    match terms:
        case []:
            return {"type": "single-pick-vocabulary", "value": ""}
        case [term]:
            return {"type": "single-pick-vocabulary", "value": term}
        case _:
            return {"type": "single-pick-vocabulary", "value": w}


def _number_range_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "number-range", **_decoded_object(w, "number-range")}


def _date_range_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "date-range", **_decoded_object(w, "date-range")}


def _filter_payload(w: str) -> dict[str, JsonValue]:
    if not w:
        return {"type": "filter", "empty": True}
    body = _decoded_object(w, "filter")
    return {"type": "filter", "filters": body.get("filters", [])}


def _number_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "number", "value": float(w) if w else None}


def _date_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "date", "value": w or None}


def _input_dataset_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "input-dataset", "dataset_id": w}


def _input_step_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "input-step", "step_id": w}


_WIRE_BUILDERS: dict[ParamKind, Callable[[str], dict[str, JsonValue]]] = {
    "multi-pick-vocabulary": _multi_pick_payload,
    "single-pick-vocabulary": _single_pick_payload,
    "number-range": _number_range_payload,
    "date-range": _date_range_payload,
    "filter": _filter_payload,
    "number": _number_payload,
    "date": _date_payload,
    "input-dataset": _input_dataset_payload,
    "input-step": _input_step_payload,
}


def _wire_payload(kind: ParamKind, wire: str) -> dict[str, JsonValue]:
    builder = _WIRE_BUILDERS.get(kind)
    if builder is not None:
        return builder(wire)
    return {"type": kind, "value": wire}


def from_wire(kind: ParamKind, wire: str) -> ParamValue:
    return _PARAM_VALUE_ADAPTER.validate_python(_wire_payload(kind, wire))


def from_wire_as(value: ParamValue, wire: str) -> ParamValue:
    match value:
        case HeldValue():
            return HeldValue(wire=wire)
        case _:
            return from_wire(value.type, wire)


def to_wire(value: ParamValue) -> str:
    return value.to_wire()


def wire_map(values: dict[str, ParamValue]) -> dict[str, str]:
    return {name: to_wire(v) for name, v in values.items()}


def to_decoded(value: ParamValue) -> JsonValue:
    return value.to_decoded()


def to_decoded_map(values: dict[str, ParamValue]) -> dict[str, JsonValue]:
    return {name: v.to_decoded() for name, v in values.items()}
