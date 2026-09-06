"""The traversal surface for a strategy graph, in both of the shapes it takes.

WDK gives structure twice: a nested step tree and a flat map of steps keyed by
id. Walking either one lives here, so a step-tree bug is fixable in one place.
"""

from collections.abc import Callable

from veupathdb.domain.strategy.ast import StrategyStepNode, generate_step_id
from veupathdb.domain.strategy.graph_model import StrategyStep

type StepFold[T] = Callable[[StrategyStepNode, list[T]], T]


def walk(root: StrategyStepNode) -> list[StrategyStepNode]:
    """Every node of the tree, inputs before the step that consumes them and
    the primary input before the secondary."""
    steps: list[StrategyStepNode] = []

    def visit(node: StrategyStepNode) -> None:
        for child in node.inputs():
            visit(child)
        steps.append(node)

    visit(root)
    return steps


def fold[T](root: StrategyStepNode, combine: StepFold[T]) -> T:
    """Fold the tree bottom up.

    Each node is given the folded results of its inputs in slot order: none
    for a search, the primary alone for a transform, both for a combine.
    """
    return combine(root, [fold(child, combine) for child in root.inputs()])


def leaves(root: StrategyStepNode) -> list[StrategyStepNode]:
    """The searches: the nodes that consume no other step."""
    return [node for node in walk(root) if not node.inputs()]


def clone_with_fresh_ids(node: StrategyStepNode) -> StrategyStepNode:
    """Clone a subtree, assigning a fresh ``id`` to every node.

    A cloned subtree joins another graph, so its ids must not collide with the
    ids that graph already holds.
    """
    return node.model_copy(
        deep=True,
        update={
            "id": generate_step_id(),
            "primary_input": (
                clone_with_fresh_ids(node.primary_input)
                if node.primary_input is not None
                else None
            ),
            "secondary_input": (
                clone_with_fresh_ids(node.secondary_input)
                if node.secondary_input is not None
                else None
            ),
        },
    )


def root_ids(steps: dict[str, StrategyStep]) -> set[str]:
    """The steps that no other step consumes."""
    consumed = {input_id for step in steps.values() for input_id in step.input_ids()}
    return {step_id for step_id in steps if step_id not in consumed}


def subtree_ids(root_id: str, steps: dict[str, StrategyStep]) -> list[str]:
    """The root and everything feeding it, descendants before ancestors."""
    out: list[str] = []
    seen: set[str] = set()

    def visit(step_id: str) -> None:
        if step_id in seen or step_id not in steps:
            return
        seen.add(step_id)
        for input_id in steps[step_id].input_ids():
            visit(input_id)
        out.append(step_id)

    visit(root_id)
    return out


def parent_of(
    step_id: str, steps: dict[str, StrategyStep]
) -> tuple[StrategyStep, str] | None:
    """The step that consumes this step, and the slot it occupies."""
    for step in steps.values():
        if step.primary_input_id == step_id:
            return step, "primary"
        if step.secondary_input_id == step_id:
            return step, "secondary"
    return None
