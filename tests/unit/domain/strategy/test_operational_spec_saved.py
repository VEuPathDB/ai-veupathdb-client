"""A criterion that names a saved strategy materializes as a collapsed input."""

from __future__ import annotations

import pytest

from veupathdb.domain.parameters.values import MultiPickValue
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SavedStrategyRef,
    SpecStructure,
    StructureNode,
    build_step_tree,
)
from veupathdb.domain.strategy.ops import CombineOp


def _step_tree(spec: OperationalSpec) -> StrategyStepNode:
    return build_step_tree(spec).root


_PF = MultiPickValue(values=["Plasmodium falciparum 3D7"])
_SAVED_NAME = "Pf protease union (text OR GO)"
_SAVED_WDK_ID = 330534203


def _saved_subtree() -> StrategyStepNode:
    """The three-step union the user saved: two searches under one UNION."""
    return StrategyStepNode(
        search_name=COMBINE_SEARCH_NAME,
        operator=CombineOp.UNION,
        primary_input=StrategyStepNode(search_name="GenesByText"),
        secondary_input=StrategyStepNode(search_name="GenesByGoTerm"),
    )


def _saved_ref() -> SavedStrategyRef:
    return SavedStrategyRef(
        conversation_id="9bd3a584-0000-4000-8000-000000000001",
        name=_SAVED_NAME,
        wdk_strategy_id=_SAVED_WDK_ID,
        root_count=227,
        step_count=3,
        subtree=_saved_subtree(),
    )


def _saved_criterion() -> Criterion:
    return Criterion(
        id="c_saved",
        text=f"start from my saved strategy {_SAVED_NAME!r}",
        role="seed",
        saved_strategy_ref=_saved_ref(),
    )


def _filter_criterion() -> Criterion:
    return Criterion(
        id="c_sp",
        text="has a predicted signal peptide",
        search_name="GenesWithSignalPeptide",
        resolved_params={"organism": _PF},
    )


def _spec(*, saved_first: bool, operator: CombineOp) -> OperationalSpec:
    order = ["c_saved", "c_sp"] if saved_first else ["c_sp", "c_saved"]
    return OperationalSpec(
        goal="start from the saved union, keep signal-peptide genes",
        criteria=[_saved_criterion(), _filter_criterion()],
        structure=SpecStructure(
            root=StructureNode(
                kind="combine",
                operator=operator,
                inputs=[StructureNode(kind="leaf", criterion_id=cid) for cid in order],
            )
        ),
    )


class TestASavedCriterionIsBound:
    def test_a_saved_reference_binds_the_criterion_without_a_search(self) -> None:
        criterion = _saved_criterion()
        assert criterion.search_name == ""
        assert criterion.bound is True

    def test_the_spec_is_ready_to_build(self) -> None:
        spec = _spec(saved_first=True, operator=CombineOp.INTERSECT)

        assert (spec.ready_to_build, spec.open_slots) == (True, [])


class TestTheSavedStrategyBecomesACollapsedInput:
    def test_the_combine_carries_the_saved_reference_and_the_saved_subtree(
        self,
    ) -> None:
        root = _step_tree(_spec(saved_first=False, operator=CombineOp.INTERSECT))
        assert root.search_name == COMBINE_SEARCH_NAME
        assert root.operator == CombineOp.INTERSECT
        assert root.expanded_strategy_id == _SAVED_WDK_ID
        assert root.expanded_name == _SAVED_NAME
        assert root.primary_input is not None
        assert root.primary_input.search_name == "GenesWithSignalPeptide"
        assert root.secondary_input is not None
        assert root.secondary_input.operator == CombineOp.UNION

    def test_a_saved_input_on_the_left_moves_to_the_secondary_slot(self) -> None:
        root = _step_tree(_spec(saved_first=True, operator=CombineOp.INTERSECT))
        assert root.operator == CombineOp.INTERSECT
        assert root.secondary_input is not None
        assert root.secondary_input.operator == CombineOp.UNION
        assert root.primary_input is not None
        assert root.primary_input.search_name == "GenesWithSignalPeptide"

    def test_the_operator_mirrors_when_the_saved_input_moves(self) -> None:
        root = _step_tree(_spec(saved_first=True, operator=CombineOp.MINUS))
        assert root.operator == CombineOp.RMINUS
        assert root.secondary_input is not None
        assert root.secondary_input.operator == CombineOp.UNION

    def test_every_step_of_the_saved_subtree_gets_a_fresh_id(self) -> None:
        spec = _spec(saved_first=False, operator=CombineOp.INTERSECT)
        first = _step_tree(spec)
        second = _step_tree(spec)
        assert first.secondary_input is not None
        assert second.secondary_input is not None
        assert first.secondary_input.id != second.secondary_input.id

    def test_a_saved_reference_alone_materializes_as_its_own_subtree(self) -> None:
        spec = OperationalSpec(
            goal="g",
            criteria=[_saved_criterion()],
            structure=SpecStructure(
                root=StructureNode(kind="leaf", criterion_id="c_saved")
            ),
        )
        root = _step_tree(spec)
        assert root.operator == CombineOp.UNION
        assert root.expanded_strategy_id is None


class TestAnUnresolvedSavedInputBlocksTheBuild:
    def test_a_criterion_with_an_open_saved_slot_is_not_ready_to_build(self) -> None:
        spec = OperationalSpec(
            goal="g",
            criteria=[
                Criterion(
                    id="c_saved",
                    text="start from my saved strategy 'Nope'",
                    role="seed",
                    open_params=[
                        OpenSlot(
                            criterion_id="c_saved",
                            param_name="saved_strategy",
                            question="Which saved strategy?",
                            options=[_SAVED_NAME],
                        )
                    ],
                ),
                _filter_criterion(),
            ],
            structure=SpecStructure(
                root=StructureNode(
                    kind="combine",
                    operator=CombineOp.INTERSECT,
                    inputs=[
                        StructureNode(kind="leaf", criterion_id="c_saved"),
                        StructureNode(kind="leaf", criterion_id="c_sp"),
                    ],
                )
            ),
        )
        assert spec.ready_to_build is False
        with pytest.raises(ValueError, match="missing or unbound"):
            _step_tree(spec)
