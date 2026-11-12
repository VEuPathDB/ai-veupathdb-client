"""A step's output organisms, read from the parameter WDK marks on its search."""

from __future__ import annotations

from typing import Literal

import pytest

from veupathdb.domain.parameters.values import MultiPickValue, StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import ColocationParams, CombineOp
from veupathdb.domain.strategy.organism import extract_output_organisms
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse

if needs_qa_recording(
    "wdk/search_genes_by_ngs_snps.json",
    "wdk/search_genes_by_molecular_weight.json",
    "wdk/search_genes_by_orthologs.json",
    "wdk/search_genes_by_location.json",
):
    pytest.skip(NEEDS_QA_RECORDING, allow_module_level=True)

_PF = "Plasmodium falciparum 3D7"
_PV = "Plasmodium vivax P01"


def _marked(fixture: str) -> tuple[str, str]:
    search = WDKSearchResponse.model_validate(
        load_recorded(fixture).json_body()
    ).search_data
    name = next(p.name for p in search.parameters or [] if p.is_organism)
    return search.url_segment, name


_MARKED = dict(
    _marked(fixture)
    for fixture in (
        "search_genes_by_ngs_snps",
        "search_genes_by_molecular_weight",
        "search_genes_by_orthologs",
        "search_genes_by_location",
    )
)


def _snps(organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="GenesByNgsSnps",
        parameters={"organismSinglePick": MultiPickValue(values=[organism])},
    )


def _weight(organism: str) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="GenesByMolecularWeight",
        parameters={"organism": MultiPickValue(values=[organism])},
    )


def test_a_leaf_reads_the_marked_parameter_whatever_its_name() -> None:
    assert extract_output_organisms(_snps(_PF), _MARKED) == {_PF}


def _combine(
    operator: CombineOp, primary: StrategyStepNode, secondary: StrategyStepNode
) -> StrategyStepNode:
    return StrategyStepNode(
        search_name="__combine__",
        primary_input=primary,
        secondary_input=secondary,
        operator=operator,
    )


def _swapped(step: StrategyStepNode) -> StrategyStepNode:
    if step.primary_input is None or step.secondary_input is None:
        return step
    return step.model_copy(
        update={
            "primary_input": _swapped(step.secondary_input),
            "secondary_input": _swapped(step.primary_input),
        }
    )


def test_a_union_holds_the_organisms_of_both_inputs() -> None:
    union = _combine(CombineOp.UNION, _snps(_PV), _weight(_PF))

    assert extract_output_organisms(union, _MARKED) == {_PV, _PF}


def test_a_union_with_an_unknown_input_is_unknown() -> None:
    unknown = StrategyStepNode(search_name="GenesByLocation")
    union = _combine(CombineOp.UNION, _snps(_PV), unknown)

    assert extract_output_organisms(union, _MARKED) is None
    assert extract_output_organisms(_swapped(union), _MARKED) is None


def test_an_intersect_holds_the_organisms_of_both_inputs() -> None:
    intersect = _combine(CombineOp.INTERSECT, _snps(_PV), _weight(_PF))

    assert extract_output_organisms(intersect, _MARKED) == {_PV, _PF}


def test_an_intersect_with_an_unknown_input_is_unknown() -> None:
    unknown = StrategyStepNode(search_name="GenesByLocation")
    intersect = _combine(CombineOp.INTERSECT, unknown, _weight(_PF))

    assert extract_output_organisms(intersect, _MARKED) is None
    assert extract_output_organisms(_swapped(intersect), _MARKED) is None


@pytest.mark.parametrize("operator", [CombineOp.MINUS, CombineOp.LONLY])
def test_a_left_minus_keeps_the_primary_scope(operator: CombineOp) -> None:
    minus = _combine(operator, _snps(_PV), _weight(_PF))

    assert extract_output_organisms(minus, _MARKED) == {_PV}


@pytest.mark.parametrize("operator", [CombineOp.RMINUS, CombineOp.RONLY])
def test_a_right_minus_keeps_the_secondary_scope(operator: CombineOp) -> None:
    minus = _combine(operator, _snps(_PV), _weight(_PF))

    assert extract_output_organisms(minus, _MARKED) == {_PF}


@pytest.mark.parametrize(("output", "expected"), [("a", _PV), ("b", _PF)])
def test_a_colocation_keeps_the_scope_of_the_side_it_outputs(
    output: Literal["a", "b"], expected: str
) -> None:
    colocate = StrategyStepNode(
        search_name="__combine__",
        primary_input=_snps(_PV),
        secondary_input=_weight(_PF),
        operator=CombineOp.COLOCATE,
        colocation_params=ColocationParams(output=output),
    )

    assert extract_output_organisms(colocate, _MARKED) == {expected}


_TG_GT1 = "Toxoplasma gondii GT1"
_PK_H = "Plasmodium knowlesi strain H"
_PK_A1H1 = "Plasmodium knowlesi strain A1H1"
_EDA = "GenesByPhenotypeEdaSubset"


def _study(step_id: str) -> StrategyStepNode:
    return StrategyStepNode(id=step_id, search_name=_EDA)


def _measured_tree() -> StrategyStepNode:
    screens = _combine(
        CombineOp.UNION,
        _combine(
            CombineOp.UNION,
            _combine(CombineOp.UNION, _study("gt1_screen"), _study("gt1_profile")),
            _study("pk_h"),
        ),
        _study("pk_a1h1"),
    )
    profile = StrategyStepNode(
        search_name="GenesByOrthologPattern",
        parameters={"organism": MultiPickValue(values=["Apicomplexa"])},
    )
    return _combine(CombineOp.INTERSECT, screens, profile)


_STUDIES = {
    "gt1_screen": frozenset({_TG_GT1}),
    "gt1_profile": frozenset({_TG_GT1}),
    "pk_h": frozenset({_PK_H}),
    "pk_a1h1": frozenset({_PK_A1H1}),
}
_PATTERN = {"GenesByOrthologPattern": "organism"}


def test_an_intersect_of_unioned_studies_holds_every_study_organism() -> None:
    found = extract_output_organisms(_measured_tree(), _PATTERN, _STUDIES)

    assert found == {_TG_GT1, _PK_H, _PK_A1H1, "Apicomplexa"}


def test_swapping_every_operand_keeps_the_scope() -> None:
    tree = _measured_tree()

    assert extract_output_organisms(
        _swapped(tree), _PATTERN, _STUDIES
    ) == extract_output_organisms(tree, _PATTERN, _STUDIES)


def test_a_leaf_that_marks_no_organism_reads_its_own_organisms() -> None:
    assert extract_output_organisms(_study("pk_h"), {}, _STUDIES) == {_PK_H}


def test_a_marked_parameter_outranks_the_step_organisms() -> None:
    step = _snps(_PV)
    stated = {step.id: frozenset({_PF})}

    assert extract_output_organisms(step, _MARKED, stated) == {_PV}


def test_an_ortholog_transform_yields_its_target_organism() -> None:
    orthologs = StrategyStepNode(
        search_name="GenesByOrthologs",
        parameters={"organism": MultiPickValue(values=[_PV])},
        primary_input=_weight(_PF),
    )

    assert extract_output_organisms(orthologs, _MARKED) == {_PV}


def test_an_ortholog_transform_without_a_target_is_unknown() -> None:
    orthologs = StrategyStepNode(
        search_name="GenesByOrthologs",
        parameters={},
        primary_input=_weight(_PF),
    )

    assert extract_output_organisms(orthologs, _MARKED) is None


def test_a_parameter_named_organism_is_not_the_mark() -> None:
    unmarked = StrategyStepNode(
        search_name="GenesByLocation",
        parameters={"organism": StringValue(value=_PF)},
    )

    assert extract_output_organisms(unmarked, _MARKED) is None


def test_an_empty_selection_is_unknown() -> None:
    empty = StrategyStepNode(
        search_name="GenesByNgsSnps",
        parameters={"organismSinglePick": MultiPickValue(values=[])},
    )
    assert extract_output_organisms(empty, _MARKED) is None
