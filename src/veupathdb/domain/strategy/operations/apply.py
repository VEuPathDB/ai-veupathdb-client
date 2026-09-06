"""Apply one operation to the working graph.

Steps are keyed by id and refer to each other by id, so one operation changes
one step.
"""

from veupathdb.domain.strategy.graph_model import (
    DuplicateStepIdError,
    StepKind,
    StrategyStep,
    flatten_tree,
)
from veupathdb.domain.strategy.operations._delete import (
    _apply_delete_edge,
    _apply_delete_step,
)
from veupathdb.domain.strategy.operations._graph_edit import (
    ApplyError,
    ApplyResult,
    _drop,
    _reject_existing,
    _require,
    _set_input_slot,
    _settle,
    _step_from_node,
)
from veupathdb.domain.strategy.operations.types import (
    AddCombineOp,
    AddLeafOp,
    AddTransformOp,
    AttachIntoSlot,
    DeleteEdgeOp,
    DeleteStepOp,
    DuplicateStepOp,
    GraphOperation,
    ReplaceStrategyOp,
    ReplaceSubtreeOp,
    UpdateCombineOperatorOp,
    UpdateStepMetaOp,
    UpdateStepParamsOp,
    UpdateStrategyMetaOp,
    WireInputOp,
)
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.session import StrategyGraph
from veupathdb.domain.strategy.tree import subtree_ids


def apply_operation(graph: StrategyGraph, op: GraphOperation) -> ApplyResult:
    structural = _try_apply_structural(graph, op)
    if structural is not None:
        return structural
    return _apply_field_update(graph, op)


def _try_apply_structural(
    graph: StrategyGraph, op: GraphOperation
) -> ApplyResult | None:
    add_result = _try_apply_add_op(graph, op)
    if add_result is not None:
        return add_result
    if isinstance(op, DeleteStepOp):
        return _apply_delete_step(graph, op)
    if isinstance(op, DeleteEdgeOp):
        return _apply_delete_edge(graph, op)
    if isinstance(op, ReplaceSubtreeOp):
        return _apply_replace_subtree(graph, op)
    if isinstance(op, ReplaceStrategyOp):
        return _apply_replace_strategy(graph, op)
    return None


def _try_apply_add_op(graph: StrategyGraph, op: GraphOperation) -> ApplyResult | None:
    if isinstance(op, AddLeafOp):
        return _apply_add_leaf(graph, op)
    if isinstance(op, AddCombineOp):
        return _apply_add_combine(graph, op)
    if isinstance(op, AddTransformOp):
        return _apply_add_transform(graph, op)
    if isinstance(op, DuplicateStepOp):
        return _apply_duplicate_step(graph, op)
    return None


def _apply_field_update(graph: StrategyGraph, op: GraphOperation) -> ApplyResult:
    if isinstance(op, UpdateStepParamsOp):
        return _apply_update_params(graph, op)
    if isinstance(op, UpdateCombineOperatorOp):
        return _apply_update_combine_operator(graph, op)
    if isinstance(op, UpdateStepMetaOp):
        return _apply_update_step_meta(graph, op)
    if isinstance(op, UpdateStrategyMetaOp):
        return _apply_update_strategy_meta(graph, op)
    if isinstance(op, WireInputOp):
        return _apply_wire_input(graph, op)
    msg = f"unsupported operation: {type(op).__name__}"
    raise ApplyError(msg)


def _apply_add_leaf(graph: StrategyGraph, op: AddLeafOp) -> ApplyResult:
    step = _step_from_node(op.step, StepKind.SEARCH)
    _reject_existing(graph, step.id, "step id")
    graph.steps[step.id] = step
    if isinstance(op.attach, AttachIntoSlot):
        target = _require(graph, op.attach.target_step_id, "target step")
        _set_input_slot(target, op.attach.slot, step.id)
    _settle(graph, step.id)
    return ApplyResult(description=f"Added {step.display_name or step.id}")


def _apply_add_combine(graph: StrategyGraph, op: AddCombineOp) -> ApplyResult:
    if op.left_id == op.right_id:
        msg = "combine inputs must differ"
        raise ApplyError(msg)
    _require(graph, op.left_id, "combine input step")
    _require(graph, op.right_id, "combine input step")
    _reject_existing(graph, op.step.id, "step id")
    combine = _step_from_node(op.step, StepKind.COMBINE)
    combine.primary_input_id = op.left_id
    combine.secondary_input_id = op.right_id
    graph.steps[combine.id] = combine
    _settle(graph, combine.id)
    return ApplyResult(description=f"Combined {op.left_id} and {op.right_id}")


def _apply_add_transform(graph: StrategyGraph, op: AddTransformOp) -> ApplyResult:
    _require(graph, op.input_id, "input step")
    _reject_existing(graph, op.step.id, "step id")
    transform = _step_from_node(op.step, StepKind.TRANSFORM)
    transform.primary_input_id = op.input_id
    consumer_info = (
        graph.parent_of(op.input_id) if op.mode == "before-consumer" else (None)
    )
    graph.steps[transform.id] = transform
    if consumer_info is not None:
        consumer, slot = consumer_info
        _set_input_slot(consumer, slot, transform.id)
    _settle(graph, transform.id)
    return ApplyResult(
        description=f"Inserted transform {transform.display_name or transform.id}"
    )


def _apply_replace_subtree(graph: StrategyGraph, op: ReplaceSubtreeOp) -> ApplyResult:
    _require(graph, op.step_id, "step")
    old_ids = set(subtree_ids(op.step_id, graph.steps))
    parent_info = graph.parent_of(op.step_id)

    try:
        incoming = flatten_tree(op.subtree)
    except DuplicateStepIdError as exc:
        raise ApplyError(str(exc)) from exc
    _drop(graph, old_ids)
    graph.steps.update(incoming)

    if parent_info is not None:
        parent, slot = parent_info
        _set_input_slot(parent, slot, op.subtree.id)
    _settle(graph, op.subtree.id)
    return ApplyResult(
        description=f"Replaced subtree at {op.step_id}",
        dropped_step_ids=sorted(old_ids - set(incoming)),
    )


def _apply_replace_strategy(graph: StrategyGraph, op: ReplaceStrategyOp) -> ApplyResult:
    """Replace the whole graph with the given tree.

    The result is the tree exactly. A step that the tree does not name is
    gone.
    """
    try:
        rebuilt = flatten_tree(op.root)
    except DuplicateStepIdError as exc:
        raise ApplyError(str(exc)) from exc
    dropped = sorted(set(graph.steps) - set(rebuilt))
    graph.steps = rebuilt
    graph.roots = {op.root.id}
    graph.last_step_id = op.root.id
    if op.name is not None:
        graph.name = op.name
    if op.description is not None:
        graph.description = op.description
    return ApplyResult(description="Replaced strategy", dropped_step_ids=dropped)


def _apply_update_params(graph: StrategyGraph, op: UpdateStepParamsOp) -> ApplyResult:
    target = _require(graph, op.step_id, "step")
    target.parameters = {**target.parameters, **op.parameters}
    return ApplyResult(description=f"Updated parameters of {op.step_id}")


def _apply_update_combine_operator(
    graph: StrategyGraph, op: UpdateCombineOperatorOp
) -> ApplyResult:
    target = _require(graph, op.step_id, "step")
    target.operator = op.operator
    target.colocation_params = op.colocation_params
    return ApplyResult(
        description=f"Set operator of {op.step_id} to {op.operator.value}"
    )


def _apply_update_step_meta(graph: StrategyGraph, op: UpdateStepMetaOp) -> ApplyResult:
    target = _require(graph, op.step_id, "step")
    target.display_name = op.display_name
    return ApplyResult(description=f"Renamed {op.step_id}")


def _apply_update_strategy_meta(
    graph: StrategyGraph,
    op: UpdateStrategyMetaOp,
) -> ApplyResult:
    if op.name is not None:
        graph.name = op.name
    if op.description is not None:
        graph.description = op.description
    return ApplyResult(description="Updated strategy metadata")


def _apply_duplicate_step(
    graph: StrategyGraph,
    op: DuplicateStepOp,
) -> ApplyResult:
    source = _require(graph, op.source_step_id, "step")
    _reject_existing(graph, op.duplicate_step_id, "duplicate id")
    _reject_existing(graph, op.combine_step_id, "combine id")

    duplicate = source.model_copy(
        update={
            "id": op.duplicate_step_id,
            "kind": StepKind.SEARCH,
            "primary_input_id": None,
            "secondary_input_id": None,
            "operator": None,
            "colocation_params": None,
        }
    )
    combine = StrategyStep(
        id=op.combine_step_id,
        kind=StepKind.COMBINE,
        primary_input_id=source.id,
        secondary_input_id=duplicate.id,
        operator=CombineOp.INTERSECT,
        display_name=op.combine_display_name,
    )

    parent_info = graph.parent_of(op.source_step_id)
    graph.steps[duplicate.id] = duplicate
    graph.steps[combine.id] = combine
    if parent_info is not None:
        parent, slot = parent_info
        _set_input_slot(parent, slot, combine.id)
    _settle(graph, combine.id)
    return ApplyResult(description=f"Duplicated {op.source_step_id}")


def _apply_wire_input(graph: StrategyGraph, op: WireInputOp) -> ApplyResult:
    target = _require(graph, op.target_step_id, "target step")
    _require(graph, op.source_step_id, "source step")
    _set_input_slot(target, op.slot, op.source_step_id)
    if target.primary_input_id and target.secondary_input_id:
        target.kind = StepKind.COMBINE
    _settle(graph, target.id)
    return ApplyResult(
        description=f"Wired {op.source_step_id} to {op.target_step_id}",
    )


__all__ = ["ApplyError", "ApplyResult", "apply_operation"]
