from __future__ import annotations

import pytest

from veupathdb.domain.parameters import ParamGraph
from veupathdb.domain.parameters.specs import ParamSpecNormalized
from veupathdb.testing import NEEDS_QA_RECORDING, needs_qa_recording
from veupathdb.testing.wdk_fixtures import load_recorded
from veupathdb.wdk.wdk_models import WDKSearchResponse

_NGS_SNPS = "wdk/search_genes_by_ngs_snps.json"


def _ngs_snps_graph() -> ParamGraph:
    search = WDKSearchResponse.model_validate(
        load_recorded("search_genes_by_ngs_snps").json_body()
    ).search_data
    return ParamGraph.of(search.parameters or [])


def _spec(name: str, *children: str, hidden: bool = False) -> ParamSpecNormalized:
    return ParamSpecNormalized(
        name=name,
        param_type="string",
        is_visible=not hidden,
        dependent_params=children,
    )


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
def test_a_hidden_parent_is_a_wire_parent_and_not_a_stated_one() -> None:
    graph = _ngs_snps_graph()

    assert graph.wire_parents["variation_sample_meta"] == (
        "organismSinglePick",
        "eda_sample_table_suffix",
    )
    assert graph.stated_parents["variation_sample_meta"] == ("organismSinglePick",)
    assert graph.stated_children["organismSinglePick"] == ("variation_sample_meta",)
    assert "eda_sample_table_suffix" not in graph.stated_children


@pytest.mark.skipif(needs_qa_recording(_NGS_SNPS), reason=NEEDS_QA_RECORDING)
def test_the_fill_order_puts_each_parent_before_its_children() -> None:
    order = _ngs_snps_graph().fill_order

    assert (
        order.index("organismSinglePick")
        < order.index("eda_sample_table_suffix")
        < order.index("variation_sample_meta")
    )


def test_a_stated_parent_is_reached_through_site_set_parents() -> None:
    graph = ParamGraph.of(
        [
            _spec("a", "h1", "c"),
            _spec("h1", "h2", hidden=True),
            _spec("h2", "c", hidden=True),
            _spec("c"),
        ]
    )

    assert graph.stated_parents["c"] == ("a",)


def test_a_parameter_under_only_site_set_parents_has_no_stated_parent() -> None:
    graph = ParamGraph.of([_spec("d", "t", hidden=True), _spec("t")])

    assert graph.wire_parents["t"] == ("d",)
    assert graph.stated_parents.get("t", ()) == ()


def test_a_cycle_keeps_each_name_once_in_the_fill_order() -> None:
    graph = ParamGraph.of([_spec("x", "y"), _spec("y", "x"), _spec("z")])

    assert graph.fill_order == ("z", "x", "y")


def test_the_fill_order_ignores_the_order_of_dependent_params() -> None:
    forward = ParamGraph.of([_spec("p", "a", "b"), _spec("a"), _spec("b")])
    backward = ParamGraph.of([_spec("p", "b", "a"), _spec("a"), _spec("b")])

    assert forward.fill_order == backward.fill_order == ("p", "a", "b")
