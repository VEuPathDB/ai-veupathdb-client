from __future__ import annotations

from pydantic import TypeAdapter

from veupathdb.domain.parameters.wdk_vocab import (
    WDKFilterOntologyTerm,
    WDKTreeBoxVocabNode,
    WDKVocabTerm,
)
from veupathdb.wdk.wdk_parameters import (
    WDKDatasetParam,
    WDKEnumParam,
    WDKFilterParam,
    WDKParameter,
)


def test_standard_enum_vocabulary_parses_term_display_null_triples() -> None:
    """checkBox/select/typeAhead vocab is [[term, display, null], ...]."""
    raw = {
        "name": "text_fields",
        "type": "multi-pick-vocabulary",
        "displayType": "checkBox",
        "vocabulary": [
            ["apolloCommentContent", "Apollo Annotations", None],
            ["ECNumbers", "EC descriptions and numbers", None],
        ],
    }
    param = WDKEnumParam.model_validate(raw)
    assert isinstance(param.vocabulary, list)
    first = param.vocabulary[0]
    assert isinstance(first, WDKVocabTerm)
    assert first.term == "apolloCommentContent"
    assert first.display == "Apollo Annotations"


def test_treebox_enum_vocabulary_parses_recursive_nodes() -> None:
    """treeBox vocab is {data:{term,display}, children:[...]}."""
    raw = {
        "name": "organism",
        "type": "multi-pick-vocabulary",
        "displayType": "treeBox",
        "vocabulary": {
            "data": {"term": "@@fake@@", "display": "@@fake@@"},
            "children": [
                {
                    "data": {"term": "Plasmodiidae", "display": "Plasmodiidae"},
                    "children": [
                        {
                            "data": {"term": "Hepatocystis", "display": "Hepatocystis"},
                            "children": [],
                        },
                    ],
                },
            ],
        },
    }
    param = WDKEnumParam.model_validate(raw)
    assert isinstance(param.vocabulary, WDKTreeBoxVocabNode)
    child = param.vocabulary.children[0]
    assert child.data.term == "Plasmodiidae"
    assert child.children[0].data.display == "Hepatocystis"


def test_dataset_param_parses_typed_parsers() -> None:
    raw = {
        "name": "ds_gene_ids",
        "type": "input-dataset",
        "defaultIdList": "PF3D7_1133400",
        "parsers": [
            {
                "name": "list",
                "displayName": "List",
                "description": "The input is a list of records.",
            },
        ],
    }
    param = WDKDatasetParam.model_validate(raw)
    assert param.default_id_list == "PF3D7_1133400"
    assert param.parsers[0].name == "list"
    assert param.parsers[0].display_name == "List"


def test_filter_param_parses_typed_ontology() -> None:
    raw = {
        "name": "f",
        "type": "filter",
        "minSelectedCount": 0,
        "ontology": [
            {
                "term": "age",
                "parent": None,
                "display": "Age",
                "type": "number",
                "precision": 1,
                "isRange": True,
            },
        ],
        "values": {"age": ["10", "20"]},
    }
    param = WDKFilterParam.model_validate(raw)
    term = param.ontology[0]
    assert isinstance(term, WDKFilterOntologyTerm)
    assert term.term == "age"
    assert term.is_range is True
    assert param.values == {"age": ["10", "20"]}


def test_discriminated_union_routes_to_typed_subtypes() -> None:
    adapter = TypeAdapter(WDKParameter)
    param = adapter.validate_python(
        {
            "name": "organism",
            "type": "multi-pick-vocabulary",
            "displayType": "treeBox",
            "vocabulary": {"data": {"term": "r", "display": "R"}, "children": []},
        },
    )
    assert isinstance(param, WDKEnumParam)
    assert isinstance(param.vocabulary, WDKTreeBoxVocabNode)
    assert param.name == "organism"
    assert (param.vocabulary.data.term, param.vocabulary.data.display) == ("r", "R")
    assert param.vocabulary.children == []
