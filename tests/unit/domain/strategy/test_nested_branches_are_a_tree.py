"""Two shapes over the same three searches, and the slot that tells them apart.

``A INTERSECT (B UNION C)`` hangs the union on the intersect's secondary input.
``(A INTERSECT B) UNION C`` hangs the intersect on the union's primary input.
WDK accepts both, and they answer different questions.
"""

from __future__ import annotations

from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.tree import leaves, parent_of, walk


def _leaf(name: str) -> StrategyStepNode:
    return StrategyStepNode(search_name=f"GenesBy{name}", display_name=name)


def _combine(
    left: StrategyStepNode, right: StrategyStepNode, operator: CombineOp
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        operator=operator,
        primary_input=left,
        secondary_input=right,
    )


def _nested() -> StrategyStepNode:
    return _combine(
        _leaf("A"),
        _combine(_leaf("B"), _leaf("C"), CombineOp.UNION),
        CombineOp.INTERSECT,
    )


def _flattened() -> StrategyStepNode:
    return _combine(
        _combine(_leaf("A"), _leaf("B"), CombineOp.INTERSECT),
        _leaf("C"),
        CombineOp.UNION,
    )


def test_a_branch_hangs_off_the_secondary_input() -> None:
    root = _nested()
    union = root.secondary_input

    assert union is not None
    assert (root.operator, union.operator) == (CombineOp.INTERSECT, CombineOp.UNION)
    assert [node.display_label for node in leaves(root)] == ["A", "B", "C"]
    assert len(walk(root)) == 5


def test_the_two_shapes_put_the_union_in_different_slots() -> None:
    nested = _nested()
    flattened = _flattened()
    nested_union = nested.secondary_input
    flattened_intersect = flattened.primary_input

    assert nested_union is not None
    assert flattened_intersect is not None
    nested_parent = parent_of(nested_union.id, flatten_tree(nested))
    flattened_parent = parent_of(flattened_intersect.id, flatten_tree(flattened))

    assert nested_parent is not None
    assert flattened_parent is not None
    assert (nested_parent[0].id, nested_parent[1]) == (nested.id, "secondary")
    assert (flattened_parent[0].id, flattened_parent[1]) == (flattened.id, "primary")
    assert (nested.operator, flattened.operator) == (
        CombineOp.INTERSECT,
        CombineOp.UNION,
    )


def test_both_shapes_hold_the_same_three_searches() -> None:
    searched = [node.search_name for node in leaves(_nested())]

    assert searched == [node.search_name for node in leaves(_flattened())]
    assert searched == ["GenesByA", "GenesByB", "GenesByC"]
