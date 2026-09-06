"""Delete a step or an edge, and re-wire what the deletion leaves behind."""

from veupathdb.domain.strategy.graph_model import StepKind, StrategyStep
from veupathdb.domain.strategy.operations._graph_edit import (
    ApplyError,
    ApplyResult,
    _demote_to_single_input,
    _drop,
    _require,
    _set_input_slot,
    _settle,
)
from veupathdb.domain.strategy.operations.types import (
    DeleteEdgeOp,
    DeleteEdgeResolution,
    DeleteResolution,
    DeleteStepOp,
)
from veupathdb.domain.strategy.session import StrategyGraph
from veupathdb.domain.strategy.tree import subtree_ids


def _apply_delete_step(graph: StrategyGraph, op: DeleteStepOp) -> ApplyResult:
    target = _require(graph, op.step_id, "step")

    if op.resolution == DeleteResolution.DELETE_STRATEGY:
        dropped = sorted(graph.steps)
        graph.steps.clear()
        graph.roots.clear()
        graph.last_step_id = None
        return ApplyResult(description="Deleted strategy", dropped_step_ids=dropped)

    parent_info = graph.parent_of(op.step_id)

    if op.resolution == DeleteResolution.DELETE_SUBTREE:
        return _delete_subtree(graph, target, parent_info)
    if op.resolution == DeleteResolution.COLLAPSE_COMBINE:
        return _collapse_combine(graph, target, parent_info)
    if op.resolution == DeleteResolution.ORPHAN_SIBLING:
        return _orphan_sibling(graph, target, parent_info)
    if op.resolution == DeleteResolution.PROMOTE_PRIMARY:
        return _promote_primary(graph, target, parent_info)

    msg = f"unhandled resolution {op.resolution!r}"
    raise ApplyError(msg)


def _delete_subtree(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str] | None,
) -> ApplyResult:
    to_delete = set(subtree_ids(target.id, graph.steps))
    if parent_info is not None:
        parent, slot = parent_info
        if parent.kind is StepKind.TRANSFORM:
            # A transform needs an input, so it goes with the deleted subtree.
            to_delete.add(parent.id)
            grandparent_info = graph.parent_of(parent.id)
            if grandparent_info is not None:
                grandparent, gp_slot = grandparent_info
                _set_input_slot(grandparent, gp_slot, None)
        else:
            _set_input_slot(parent, slot, None)
    _drop(graph, to_delete)
    _settle(graph)
    return ApplyResult(
        description=f"Deleted {target.id} and subtree",
        dropped_step_ids=sorted(to_delete),
    )


def _collapse_combine(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str] | None,
) -> ApplyResult:
    if parent_info is None:
        return _collapse_root_combine(graph, target)
    parent, slot = parent_info
    if parent.kind is StepKind.TRANSFORM:
        return _collapse_through_transform_parent(graph, target, parent)
    return _collapse_combine_parent(graph, target, parent, slot)


def _collapse_root_combine(graph: StrategyGraph, target: StrategyStep) -> ApplyResult:
    if target.kind is not StepKind.COMBINE:
        msg = "collapse-combine on non-combine root"
        raise ApplyError(msg)
    secondary_id = target.secondary_input_id
    to_delete = {target.id}
    if secondary_id is not None:
        to_delete |= set(subtree_ids(secondary_id, graph.steps))
    primary_id = target.primary_input_id
    _drop(graph, to_delete)
    _settle(graph, primary_id)
    return ApplyResult(
        description=f"Collapsed combine {target.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _collapse_through_transform_parent(
    graph: StrategyGraph,
    target: StrategyStep,
    parent: StrategyStep,
) -> ApplyResult:
    to_delete = set(subtree_ids(target.id, graph.steps)) | {parent.id}
    grandparent_info = graph.parent_of(parent.id)
    if grandparent_info is not None:
        grandparent, gp_slot = grandparent_info
        _set_input_slot(grandparent, gp_slot, None)
    _drop(graph, to_delete)
    _settle(graph)
    return ApplyResult(
        description=f"Collapsed via transform {target.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _collapse_combine_parent(
    graph: StrategyGraph,
    target: StrategyStep,
    parent: StrategyStep,
    slot: str,
) -> ApplyResult:
    sibling_id = (
        parent.secondary_input_id if slot == "primary" else parent.primary_input_id
    )
    to_delete = set(subtree_ids(target.id, graph.steps)) | {parent.id}
    grandparent_info = graph.parent_of(parent.id)
    if grandparent_info is not None:
        grandparent, gp_slot = grandparent_info
        _set_input_slot(grandparent, gp_slot, sibling_id)
    _drop(graph, to_delete)
    _settle(graph)
    return ApplyResult(
        description=f"Collapsed combine {parent.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _orphan_sibling(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str] | None,
) -> ApplyResult:
    """Delete this branch and detach the combine and its other input.

    The survivors form their own component. WDK rejects a step that has inputs
    but no strategy, so a detached component stays local.
    """
    if parent_info is None:
        msg = "orphan-sibling requires a combine parent"
        raise ApplyError(msg)

    parent, slot = parent_info
    to_delete = set(subtree_ids(target.id, graph.steps))
    _drop(graph, to_delete)
    _demote_to_single_input(parent, slot)

    grandparent_info = graph.parent_of(parent.id)
    if grandparent_info is not None:
        grandparent, gp_slot = grandparent_info
        _demote_to_single_input(grandparent, gp_slot)

    _settle(graph)
    return ApplyResult(
        description=f"Deleted {target.id}, orphaned {parent.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _promote_primary(
    graph: StrategyGraph,
    target: StrategyStep,
    parent_info: tuple[StrategyStep, str] | None,
) -> ApplyResult:
    if target.kind is not StepKind.COMBINE:
        msg = "promote-primary on non-combine"
        raise ApplyError(msg)
    secondary_id = target.secondary_input_id
    to_delete = {target.id}
    if secondary_id is not None:
        to_delete |= set(subtree_ids(secondary_id, graph.steps))
    primary_id = target.primary_input_id
    if parent_info is not None:
        parent, slot = parent_info
        _set_input_slot(parent, slot, primary_id)
    _drop(graph, to_delete)
    _settle(graph, primary_id)
    return ApplyResult(
        description=f"Promoted primary of {target.id}",
        dropped_step_ids=sorted(to_delete),
    )


def _apply_delete_edge(graph: StrategyGraph, op: DeleteEdgeOp) -> ApplyResult:
    target = _require(graph, op.target_id, "step")

    if op.resolution == DeleteEdgeResolution.COLLAPSE:
        return _apply_delete_step(
            graph,
            DeleteStepOp(
                step_id=op.source_id,
                resolution=DeleteResolution.COLLAPSE_COMBINE,
            ),
        )

    wired = (
        target.primary_input_id if op.slot == "primary" else target.secondary_input_id
    )
    if wired != op.source_id:
        msg = (
            f"{op.slot} input of {op.target_id!r} is not wired to {op.source_id!r}; "
            f"the graph changed since this edge was drawn"
        )
        raise ApplyError(msg)

    _demote_to_single_input(target, op.slot)
    _settle(graph, op.target_id)
    return ApplyResult(description=f"Detached edge {op.source_id} to {op.target_id}")
