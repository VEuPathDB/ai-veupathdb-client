"""The primitives every graph operation shares: lookup, wiring, and settling."""

from dataclasses import dataclass, field

from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.graph_model import (
    StepKind,
    StrategyStep,
    own_search_name,
)
from veupathdb.domain.strategy.session import StrategyGraph


@dataclass
class ApplyResult:
    description: str
    dropped_step_ids: list[str] = field(default_factory=list)


class ApplyError(Exception):
    """Raised when the graph rejects an operation."""


def _require(graph: StrategyGraph, step_id: str, label: str) -> StrategyStep:
    step = graph.steps.get(step_id)
    if step is None:
        msg = f"{label} {step_id!r} not found"
        raise ApplyError(msg)
    return step


def _reject_existing(graph: StrategyGraph, step_id: str, label: str) -> None:
    if step_id in graph.steps:
        msg = f"{label} {step_id!r} already exists"
        raise ApplyError(msg)


def _set_input_slot(parent: StrategyStep, slot: str, value: str | None) -> None:
    if slot == "primary":
        parent.primary_input_id = value
    else:
        parent.secondary_input_id = value


def _drop(graph: StrategyGraph, step_ids: set[str]) -> None:
    for step_id in step_ids:
        graph.steps.pop(step_id, None)


def _settle(graph: StrategyGraph, last_step_id: str | None = None) -> None:
    graph.recompute_roots()
    graph.last_step_id = (
        last_step_id if last_step_id in graph.steps else graph.primary_root_id()
    )


def _demote_to_single_input(step: StrategyStep, slot: str) -> None:
    """Clear an input slot and move the survivor up.

    A secondary input without a primary input is not a valid shape, so the
    remaining branch takes the primary slot.
    """
    _set_input_slot(step, slot, None)
    if slot == "primary" and step.secondary_input_id is not None:
        step.primary_input_id = step.secondary_input_id
        step.secondary_input_id = None
    step.operator = None
    step.colocation_params = None
    if step.primary_input_id is not None:
        step.kind = StepKind.TRANSFORM if step.search_name else StepKind.COMBINE


def _step_from_node(node: StrategyStepNode, kind: StepKind) -> StrategyStep:
    """Convert an incoming node into a keyed step.

    Nesting on the node is dropped, because the wiring travels in the fields of
    the operation itself.
    """
    return StrategyStep(
        id=node.id,
        kind=kind,
        search_name=own_search_name(node, kind),
        parameters=dict(node.parameters),
        display_name=node.display_name,
        operator=node.operator,
        colocation_params=node.colocation_params,
        filters=list(node.filters),
        analyses=list(node.analyses),
        reports=list(node.reports),
        wdk_weight=node.wdk_weight,
        expanded_strategy_id=node.expanded_strategy_id,
        expanded_name=node.expanded_name,
    )
