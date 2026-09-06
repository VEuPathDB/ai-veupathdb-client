"""The seam from a bound spec to a WDK step tree, and the ids the build mints.

FRAME names a criterion with a label; the build mints a step id for it. Unless
the spec adopts that id, the next turn's edit has nothing to address.
"""

from __future__ import annotations

import pytest

from veupathdb.domain.parameters.values import MultiPickValue
from veupathdb.domain.strategy.ast import COMBINE_SEARCH_NAME, StrategyStepNode
from veupathdb.domain.strategy.graph_model import flatten_tree
from veupathdb.domain.strategy.operational_spec import (
    Criterion,
    OpenSlot,
    OperationalSpec,
    SpecStructure,
    StructureNode,
    build_step_tree,
    renumber_criteria,
)
from veupathdb.domain.strategy.ops import CombineOp

_PF = MultiPickValue(values=["Plasmodium falciparum 3D7"])


def _step_tree(spec: OperationalSpec) -> StrategyStepNode:
    return build_step_tree(spec).root


def _bound(cid: str, search: str) -> Criterion:
    return Criterion(
        id=cid, text="t", search_name=search, resolved_params={"organism": _PF}
    )


def _leaf_node(criterion_id: str) -> StructureNode:
    return StructureNode(kind="leaf", criterion_id=criterion_id)


def _joined(operator: CombineOp | None, *inputs: StructureNode) -> StructureNode:
    return StructureNode(kind="combine", operator=operator, inputs=list(inputs))


def _leaf_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="g",
        criteria=[_bound("c1", "GenesWithSignalPeptide")],
        structure=SpecStructure(root=_leaf_node("c1")),
    )


class TestReadyToBuild:
    def test_criterion_bound_flag(self) -> None:
        assert Criterion(id="c1", text="t").bound is False
        assert _bound("c1", "GenesWithSignalPeptide").bound is True

    def test_a_bound_criterion_with_a_structure_is_ready(self) -> None:
        assert _leaf_spec().ready_to_build is True

    def test_an_unbound_criterion_blocks(self) -> None:
        spec = OperationalSpec(
            goal="g",
            criteria=[Criterion(id="c1", text="t")],
            structure=SpecStructure(root=_leaf_node("c1")),
        )

        assert spec.ready_to_build is False

    def test_an_open_slot_blocks(self) -> None:
        spec = OperationalSpec(
            goal="g",
            criteria=[_bound("c1", "S")],
            structure=SpecStructure(root=_leaf_node("c1")),
            open_slots=[OpenSlot(criterion_id="c1", param_name="x")],
        )

        assert spec.ready_to_build is False

    def test_no_structure_blocks(self) -> None:
        assert (
            OperationalSpec(goal="g", criteria=[_bound("c1", "S")]).ready_to_build
            is False
        )


class TestTheSeam:
    def test_seam_single_leaf(self) -> None:
        node = _step_tree(_leaf_spec())

        assert node.search_name == "GenesWithSignalPeptide"
        assert node.parameters["organism"] == _PF
        assert node.primary_input is None

    def test_seam_two_leaf_intersect(self) -> None:
        spec = OperationalSpec(
            goal="g",
            criteria=[
                _bound("c1", "GenesWithSignalPeptide"),
                _bound("c2", "GenesByTransmembraneDomains"),
            ],
            structure=SpecStructure(
                root=_joined(CombineOp.INTERSECT, _leaf_node("c1"), _leaf_node("c2"))
            ),
        )

        node = _step_tree(spec)

        assert node.search_name == COMBINE_SEARCH_NAME
        assert node.operator == CombineOp.INTERSECT
        assert node.primary_input is not None
        assert node.secondary_input is not None
        assert node.primary_input.search_name == "GenesWithSignalPeptide"
        assert node.secondary_input.search_name == "GenesByTransmembraneDomains"

    def test_seam_three_leaf_left_fold(self) -> None:
        spec = OperationalSpec(
            goal="g",
            criteria=[_bound(f"c{i}", f"S{i}") for i in (1, 2, 3)],
            structure=SpecStructure(
                root=_joined(CombineOp.UNION, *[_leaf_node(f"c{i}") for i in (1, 2, 3)])
            ),
        )

        node = _step_tree(spec)

        # left fold: ((S1 UNION S2) UNION S3)
        assert node.secondary_input is not None
        assert node.secondary_input.search_name == "S3"
        assert node.primary_input is not None
        assert node.primary_input.search_name == COMBINE_SEARCH_NAME

    def test_transform_node_builds_a_transform_step_with_primary_input(self) -> None:
        """A transform criterion applies its search to an INPUT subtree, so it
        must materialize as a WDK transform step and not a standalone leaf."""
        spec = OperationalSpec(
            goal="g",
            criteria=[
                _bound("c_seed", "GenesByRNASeqGametocytes"),
                _bound("c_ortho", "GenesByOrthologs"),
            ],
            structure=SpecStructure(
                root=StructureNode(
                    kind="transform",
                    criterion_id="c_ortho",
                    inputs=[_leaf_node("c_seed")],
                )
            ),
        )

        tree = _step_tree(spec)

        assert tree.infer_kind() == "transform"
        assert tree.search_name == "GenesByOrthologs"
        assert tree.secondary_input is None
        assert tree.primary_input is not None
        assert tree.primary_input.search_name == "GenesByRNASeqGametocytes"

    def test_seam_unbound_criterion_raises(self) -> None:
        spec = OperationalSpec(
            goal="g",
            criteria=[Criterion(id="c1", text="t")],
            structure=SpecStructure(root=_leaf_node("c1")),
        )

        with pytest.raises(ValueError, match="unbound"):
            _step_tree(spec)


class TestNestedBranchesReachWdk:
    """A UNION branch on the secondary input must survive to the step tree.

    ``A INTERSECT (B UNION C)`` is representable in a WDK step tree. Flattening
    it to ``(A INTERSECT B) UNION C`` asks a different question.
    """

    def _spec(self) -> OperationalSpec:
        return OperationalSpec(
            goal="drug targets",
            criteria=[
                Criterion(id="kinases", text="kinases", search_name="GenesByInterpro"),
                Criterion(id="ms", text="mass spec", search_name="GenesByMassSpec"),
                Criterion(id="derisi", text="derisi", search_name="GenesByMicroarray"),
            ],
            structure=SpecStructure(
                root=_joined(
                    CombineOp.INTERSECT,
                    _leaf_node("kinases"),
                    _joined(CombineOp.UNION, _leaf_node("ms"), _leaf_node("derisi")),
                )
            ),
        )

    def test_the_union_stays_on_the_secondary_input(self) -> None:
        root = _step_tree(self._spec())

        assert root.operator == CombineOp.INTERSECT
        branch = root.secondary_input
        assert branch is not None
        assert branch.operator == CombineOp.UNION

    def test_the_branch_keeps_both_of_its_own_leaves(self) -> None:
        branch = _step_tree(self._spec()).secondary_input

        assert branch is not None
        assert branch.primary_input is not None
        assert branch.secondary_input is not None
        assert branch.primary_input.search_name == "GenesByMassSpec"
        assert branch.secondary_input.search_name == "GenesByMicroarray"

    def test_the_intersect_side_is_not_rewritten(self) -> None:
        root = _step_tree(self._spec())

        assert root.primary_input is not None
        assert root.primary_input.search_name == "GenesByInterpro"


def _abc_spec(root: StructureNode) -> OperationalSpec:
    return OperationalSpec(
        goal="drug targets",
        criteria=[
            Criterion(id=name, text=name, role="filter", search_name=f"By{name}")
            for name in ("a", "b", "c")
        ],
        structure=SpecStructure(root=root),
    )


class TestASpareWrapperIsTransparent:
    """Combining n criteria needs n-1 combine nodes, so a spec that emits one
    per criterion carries a spare node with nothing to combine against."""

    def test_the_tree_is_the_inner_combine(self) -> None:
        pair = _joined(CombineOp.INTERSECT, _leaf_node("a"), _leaf_node("b"))
        wrapper = _joined(CombineOp.INTERSECT, pair)

        tree = _step_tree(_abc_spec(wrapper))

        assert tree.operator == CombineOp.INTERSECT
        assert tree.primary_input is not None
        assert tree.secondary_input is not None

    def test_a_wrapper_around_a_leaf_is_the_leaf(self) -> None:
        wrapper = _joined(CombineOp.INTERSECT, _leaf_node("a"))

        assert _step_tree(_abc_spec(wrapper)).search_name == "Bya"

    def test_nested_wrappers_all_collapse(self) -> None:
        inner = _joined(CombineOp.INTERSECT, _leaf_node("a"))
        outer = _joined(CombineOp.INTERSECT, inner)

        assert _step_tree(_abc_spec(outer)).search_name == "Bya"


class TestAnEmptyCombineIsStillAnError:
    def test_no_inputs_is_refused(self) -> None:
        with pytest.raises(ValueError, match="combine"):
            _step_tree(_abc_spec(_joined(CombineOp.INTERSECT)))

    def test_no_operator_with_two_inputs_is_refused(self) -> None:
        node = _joined(None, _leaf_node("a"), _leaf_node("b"))

        with pytest.raises(ValueError, match="combine"):
            _step_tree(_abc_spec(node))


def _protease_spec() -> OperationalSpec:
    return OperationalSpec(
        goal="proteases",
        record_type="transcript",
        criteria=[
            Criterion(
                id="c1_protease_text",
                text="protease text",
                search_name="GenesByText",
                role="seed",
                resolved_params={"organism": MultiPickValue(values=["Plasmodium"])},
            ),
            Criterion(id="c2_go", text="proteolysis GO", search_name="GenesByGoTerm"),
            Criterion(
                id="c3_orthologs",
                text="P. vivax orthologs",
                search_name="GenesByOrthologs",
                role="transform",
            ),
        ],
        structure=SpecStructure(
            root=StructureNode(
                kind="transform",
                criterion_id="c3_orthologs",
                inputs=[
                    _joined(
                        CombineOp.INTERSECT,
                        _leaf_node("c1_protease_text"),
                        _leaf_node("c2_go"),
                    )
                ],
            )
        ),
    )


class TestCriterionIdsBecomeStepIds:
    def test_the_build_reports_the_step_id_it_minted_for_each_criterion(self) -> None:
        built = build_step_tree(_protease_spec())

        assert set(built.step_id_by_criterion) == {
            "c1_protease_text",
            "c2_go",
            "c3_orthologs",
        }
        assert set(built.step_id_by_criterion.values()) <= set(flatten_tree(built.root))

    def test_a_built_spec_addresses_its_steps_by_step_id(self) -> None:
        spec = _protease_spec()
        built = build_step_tree(spec)

        renumbered = renumber_criteria(spec, built.step_id_by_criterion)

        assert {c.id for c in renumbered.criteria} == set(
            built.step_id_by_criterion.values()
        )
        assert renumbered.structure is not None
        assert (
            renumbered.structure.root.criterion_id
            == built.step_id_by_criterion["c3_orthologs"]
        )
        combine_node = renumbered.structure.root.inputs[0]
        assert [node.criterion_id for node in combine_node.inputs] == [
            built.step_id_by_criterion["c1_protease_text"],
            built.step_id_by_criterion["c2_go"],
        ]

    def test_renumbering_keeps_every_bound_value(self) -> None:
        spec = _protease_spec()
        built = build_step_tree(spec)

        renumbered = renumber_criteria(spec, built.step_id_by_criterion)

        seed = renumbered.criteria[0]
        assert seed.search_name == "GenesByText"
        assert seed.resolved_params == {
            "organism": MultiPickValue(values=["Plasmodium"])
        }

    def test_a_criterion_the_build_did_not_place_keeps_its_id(self) -> None:
        spec = _protease_spec()
        spec.criteria.append(Criterion(id="c4_unused", text="unused", search_name="X"))

        renumbered = renumber_criteria(spec, build_step_tree(spec).step_id_by_criterion)

        assert "c4_unused" in {c.id for c in renumbered.criteria}
