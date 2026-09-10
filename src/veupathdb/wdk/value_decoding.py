"""WDK parameter value encoding/decoding.

WDK wire format is ``dict[str, str]``. The strategy AST and plan models
carry typed ``ParamValue`` (discriminated union over the 11 WDK parameter
types). This module is the only place that bridges the two.
"""

from veupathdb.domain.parameters.value_codec import from_wire, wire_map
from veupathdb.domain.parameters.values import ParamKind, ParamValue

WireParams = dict[str, str]
"""The WDK wire form of a search configuration's parameters."""


def encode_params(decoded: dict[str, ParamValue]) -> WireParams:
    return wire_map(decoded)


def decode_params(
    wire: WireParams,
    kinds: dict[str, ParamKind],
) -> dict[str, ParamValue]:
    out: dict[str, ParamValue] = {}
    for name, raw in wire.items():
        kind = kinds.get(name)
        if kind is None:
            continue
        out[name] = from_wire(kind, raw)
    return out
