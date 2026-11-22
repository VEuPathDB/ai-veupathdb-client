"""The wire forms WDK holds on a step that no parameter kind reads."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from veupathdb.domain.parameters.value_codec import wire_map
from veupathdb.domain.parameters.values import ParamValue


class HoldsWire(Protocol):
    parameters: dict[str, ParamValue]
    held_wire: dict[str, str]


def refuse_held_overlap(
    parameters: Mapping[str, ParamValue], held_wire: Mapping[str, str]
) -> None:
    both = sorted(parameters.keys() & held_wire.keys())
    if both:
        msg = f"{', '.join(both)} is both read and held as WDK holds it"
        raise ValueError(msg)


def state_values(step: HoldsWire, values: Mapping[str, ParamValue]) -> None:
    step.held_wire = {n: w for n, w in step.held_wire.items() if n not in values}
    step.parameters = {**step.parameters, **values}


def sent_wire(
    parameters: Mapping[str, ParamValue], held_wire: Mapping[str, str]
) -> dict[str, str]:
    return {**wire_map(dict(parameters)), **held_wire}


def settle_values(step: HoldsWire, values: Mapping[str, ParamValue]) -> None:
    step.parameters = {n: v for n, v in values.items() if n not in step.held_wire}
