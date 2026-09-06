"""Conversion between a typed ``ParamValue`` and WDK's wire and decoded forms."""

import json
from collections.abc import Callable

from pydantic import JsonValue, TypeAdapter

from veupathdb.domain.parameters.values import (
    DateRangeValue,
    DateValue,
    FilterValue,
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


def _number_range_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "number-range", **_decoded_object(w, "number-range")}


def _date_range_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "date-range", **_decoded_object(w, "date-range")}


def _filter_payload(w: str) -> dict[str, JsonValue]:
    body = _decoded_object(w or '{"filters": []}', "filter")
    return {"type": "filter", "filters": body.get("filters", [])}


def _number_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "number", "value": float(w)}


def _input_dataset_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "input-dataset", "dataset_id": w}


def _input_step_payload(w: str) -> dict[str, JsonValue]:
    return {"type": "input-step", "step_id": w}


_WIRE_BUILDERS: dict[ParamKind, Callable[[str], dict[str, JsonValue]]] = {
    "multi-pick-vocabulary": _multi_pick_payload,
    "number-range": _number_range_payload,
    "date-range": _date_range_payload,
    "filter": _filter_payload,
    "number": _number_payload,
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


def to_wire(value: ParamValue) -> str:
    return value.to_wire()


_SCALAR_KINDS: frozenset[ParamKind] = frozenset(
    {
        "string",
        "number",
        "date",
        "timestamp",
        "single-pick-vocabulary",
        "input-dataset",
        "input-step",
    },
)


def coerce_param_value(value: ParamValue, kind: ParamKind) -> ParamValue:
    """Re-cast *value* to *kind* when both are scalar (single-value) kinds.

    WDK is stringly-typed — numeric params are ``StringParam`` with
    ``isNumber=True`` — so a ``number`` supplied for a ``string`` param (or
    vice versa) is coerced through the wire form rather than rejected.
    Structural kinds (ranges, multi-pick, filter) have no scalar coercion;
    a mismatch raises ``ValueError``.
    """
    if value.type == kind:
        return value
    if value.type in _SCALAR_KINDS and kind in _SCALAR_KINDS:
        return from_wire(kind, value.to_wire())
    msg = f"a {value.type!r} value is not valid for a {kind!r} parameter"
    raise ValueError(msg)


_SCALAR_VALUE_BY_KIND: dict[ParamKind, Callable[[object], ParamValue]] = {
    "string": lambda v: StringValue(value=str(v)),
    "number": lambda v: NumberValue(value=float(str(v))),
    "date": lambda v: DateValue(value=str(v)),
    "timestamp": lambda v: TimestampValue(value=str(v)),
    "single-pick-vocabulary": lambda v: SinglePickValue(value=str(v)),
    "input-dataset": lambda v: InputDatasetValue(dataset_id=str(v)),
    "input-step": lambda v: InputStepValue(step_id=str(v)),
    "multi-pick-vocabulary": lambda v: MultiPickValue(
        values=[str(x) for x in v] if isinstance(v, list) else [str(v)]
    ),
}


_PARAM_VALUE_TYPES = (
    StringValue,
    NumberValue,
    NumberRangeValue,
    DateValue,
    DateRangeValue,
    TimestampValue,
    SinglePickValue,
    MultiPickValue,
    FilterValue,
    InputDatasetValue,
    InputStepValue,
)


def param_value_from_raw(raw: object, kind: ParamKind) -> ParamValue:
    """Build a typed ``ParamValue`` of *kind* from a raw scalar/list/dict the
    LLM supplied, so callers needn't hand-construct the typed wrapper. An
    already-typed value (a ``ParamValue`` instance or a dict carrying ``type``)
    is coerced to *kind*; structural kinds (ranges/filter) are validated from
    their object form. The system knows *kind* from the WDK spec, so it does
    the typing."""

    if isinstance(raw, _PARAM_VALUE_TYPES):
        return coerce_param_value(raw, kind)
    if isinstance(raw, dict) and "type" in raw:
        return coerce_param_value(_PARAM_VALUE_ADAPTER.validate_python(raw), kind)
    builder = _SCALAR_VALUE_BY_KIND.get(kind)
    if builder is not None and not isinstance(raw, dict):
        return builder(raw)
    structural: dict[ParamKind, type[ParamValue]] = {
        "number-range": NumberRangeValue,
        "date-range": DateRangeValue,
        "filter": FilterValue,
    }
    model = structural.get(kind)
    if model is not None and isinstance(raw, dict):
        return model.model_validate(raw)
    msg = f"cannot build a {kind!r} parameter value from {raw!r}"
    raise ValueError(msg)


def coerce_context_values(raw: dict[str, object]) -> dict[str, ParamValue]:
    """Coerce raw context param values (parent values for dependent-vocab
    refresh) into ``ParamValue``s by SHAPE — list → multi-pick, scalar →
    single-pick, already-typed (instance or ``type`` dict) → validated. No spec
    needed: WDK is stringly-typed, so the wire form is identical regardless of
    the param's declared kind."""

    out: dict[str, ParamValue] = {}
    for name, value in raw.items():
        if isinstance(value, _PARAM_VALUE_TYPES):
            out[name] = value
        elif isinstance(value, dict) and "type" in value:
            out[name] = _PARAM_VALUE_ADAPTER.validate_python(value)
        elif isinstance(value, list):
            out[name] = MultiPickValue(values=[str(x) for x in value])
        else:
            out[name] = SinglePickValue(value=str(value))
    return out


def wire_map(values: dict[str, ParamValue]) -> dict[str, str]:
    return {name: to_wire(v) for name, v in values.items()}


def to_decoded(value: ParamValue) -> JsonValue:
    return value.to_decoded()


def to_decoded_map(values: dict[str, ParamValue]) -> dict[str, JsonValue]:
    return {name: v.to_decoded() for name, v in values.items()}


def _normalize_decoded_endpoint(value: JsonValue) -> JsonValue:
    if isinstance(value, str):
        return value or None
    return value


def from_decoded(kind: ParamKind, decoded: JsonValue) -> ParamValue:
    """Build a ``ParamValue`` from a canonicalized decoded JSON shape.

    Inverse of :func:`to_decoded` for canonicalizer outputs:
      * ``string``/``number``/``date``/``timestamp``/``single-pick-vocabulary``/
        ``input-dataset``/``input-step`` accept a scalar wire value.
      * ``multi-pick-vocabulary`` accepts a list of strings.
      * ``number-range``/``date-range`` accept a ``{min?, max?}`` dict.
      * ``filter`` accepts a ``{filters: [...]}`` dict.
    """
    payload: dict[str, JsonValue]
    match kind:
        case "multi-pick-vocabulary":
            values = decoded if isinstance(decoded, list) else [decoded]
            payload = {
                "type": "multi-pick-vocabulary",
                "values": [str(v) for v in values if v is not None],
            }
        case "number-range" | "date-range":
            if not isinstance(decoded, dict):
                msg = f"{kind} requires a dict, got {type(decoded).__name__}"
                raise TypeError(msg)
            payload = {"type": kind}
            min_v = _normalize_decoded_endpoint(decoded.get("min"))
            max_v = _normalize_decoded_endpoint(decoded.get("max"))
            if min_v is not None:
                payload["min"] = min_v
            if max_v is not None:
                payload["max"] = max_v
        case "filter":
            filters: JsonValue = (
                decoded.get("filters", []) if isinstance(decoded, dict) else []
            )
            payload = {"type": "filter", "filters": filters}
        case "number":
            payload = {"type": "number", "value": float(str(decoded))}
        case "input-dataset":
            payload = {"type": "input-dataset", "dataset_id": str(decoded)}
        case "input-step":
            payload = {"type": "input-step", "step_id": str(decoded)}
        case _:
            payload = {"type": kind, "value": str(decoded)}
    return _PARAM_VALUE_ADAPTER.validate_python(payload)
