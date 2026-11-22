"""A wire form no kind reads stays on its step as WDK holds it until it is stated."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from veupathdb.domain.parameters import NumberValue, StringValue
from veupathdb.domain.strategy import (
    StrategyStep,
    StrategyStepNode,
    flatten_tree,
    rebuild_tree,
    sent_wire,
    settle_values,
    state_values,
)

_HELD = {"min_weight": "abc"}


def test_a_node_refuses_a_name_both_read_and_held() -> None:
    with pytest.raises(ValidationError, match="min_weight"):
        StrategyStepNode(
            search_name="GenesByMolecularWeight",
            parameters={"min_weight": NumberValue(value=5)},
            held_wire=_HELD,
        )


def test_a_step_refuses_a_name_both_read_and_held() -> None:
    with pytest.raises(ValidationError, match="min_weight"):
        StrategyStep.model_validate(
            {
                "id": "a",
                "kind": "search",
                "parameters": {"min_weight": {"type": "number", "value": 5}},
                "heldWire": _HELD,
            }
        )


def test_the_held_wire_survives_flatten_and_rebuild() -> None:
    node = StrategyStepNode(
        id="a",
        search_name="GenesByMolecularWeight",
        parameters={"organism": StringValue(value="pfal")},
        held_wire=_HELD,
    )

    assert rebuild_tree("a", flatten_tree(node)) == node


def test_the_sent_wire_is_the_read_values_and_the_held_forms() -> None:
    step = StrategyStepNode(
        search_name="GenesByMolecularWeight",
        parameters={"max_weight": NumberValue(value=50)},
        held_wire=_HELD,
    )

    assert sent_wire(step.parameters, step.held_wire) == {
        "max_weight": "50",
        "min_weight": "abc",
    }


def test_a_stated_value_leaves_the_held_wire() -> None:
    step = flatten_tree(
        StrategyStepNode(id="a", search_name="GenesByMolecularWeight", held_wire=_HELD)
    )["a"]

    state_values(step, {"min_weight": NumberValue(value=7)})

    assert (step.parameters, step.held_wire) == (
        {"min_weight": NumberValue(value=7)},
        {},
    )


def test_an_empty_held_wire_is_left_out_of_the_dump() -> None:
    node = StrategyStepNode(search_name="GenesByMolecularWeight")

    assert "heldWire" not in node.model_dump(by_alias=True)


def test_settled_values_leave_a_held_value_in_place() -> None:
    step = flatten_tree(
        StrategyStepNode(id="a", search_name="GenesByMolecularWeight", held_wire=_HELD)
    )["a"]

    settle_values(
        step,
        {"min_weight": NumberValue(value=0), "max_weight": NumberValue(value=9)},
    )

    assert (step.parameters, step.held_wire) == (
        {"max_weight": NumberValue(value=9)},
        _HELD,
    )
