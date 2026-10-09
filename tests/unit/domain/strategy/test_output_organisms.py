"""A step's output organisms, read from the parameter WDK marks on its search."""

from __future__ import annotations

import pytest

from veupathdb.domain.parameters.values import MultiPickValue, StringValue
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp
from veupathdb.domain.strategy.organism import extract_output_organisms
from veupathdb.testing import NEEDS_QA_RECORDING
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse

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


def test_a_combine_inherits_its_primary_input() -> None:
    combine = StrategyStepNode(
        search_name="__combine__",
        primary_input=_snps(_PV),
        secondary_input=_weight(_PF),
        operator=CombineOp.INTERSECT,
    )

    assert extract_output_organisms(combine, _MARKED) == {_PV}


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
