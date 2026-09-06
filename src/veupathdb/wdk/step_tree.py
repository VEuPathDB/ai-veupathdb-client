"""Traversal of the WDK step tree."""

from veupathdb.wdk.wdk_models import WDKStepTree


def walk_wdk_step_tree(root: WDKStepTree) -> list[WDKStepTree]:
    """Walk a WDK step tree depth first. Each node comes after its inputs, and
    the primary input comes before the secondary input."""
    nodes: list[WDKStepTree] = []

    def visit(node: WDKStepTree) -> None:
        if node.primary_input is not None:
            visit(node.primary_input)
        if node.secondary_input is not None:
            visit(node.secondary_input)
        nodes.append(node)

    visit(root)
    return nodes
