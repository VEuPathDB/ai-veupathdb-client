"""The one place that decides whether a search is phyletic and builds its tree."""

from __future__ import annotations

from veupathdb.domain.parameters.wdk_vocab import (
    WDKTreeBoxVocabNode,
    WDKVocabNodeData,
    WDKVocabTerm,
)
from veupathdb.wdk.phyletic_tree import phyletic_tree_of
from veupathdb.wdk.wdk_parameters import (
    WDKEnumParam,
    WDKParameter,
    WDKStringParam,
)

_FIVE_NAMES = [
    "profile_pattern",
    "included_species",
    "excluded_species",
    "phyletic_indent_map",
    "phyletic_term_map",
]


def _term(code: str, display: str) -> WDKVocabTerm:
    return WDKVocabTerm((code, display, None))


_TERMS = [
    _term("ALL", "Root"),
    _term("EUKA", "Eukaryota"),
    _term("MAMM", "Mammalia"),
    _term("hsap", "Homo sapiens REF"),
    _term("pfal", "Plasmodium falciparum 3D7"),
]
_INDENTS = [
    _term("EUKA", "1"),
    _term("MAMM", "2"),
    _term("hsap", "3"),
    _term("pfal", "2"),
]


def _params(
    *,
    terms: list[WDKVocabTerm] | None = None,
    indents: list[WDKVocabTerm] | None = None,
    with_term_map: bool = True,
) -> list[WDKParameter]:
    params: list[WDKParameter] = [
        WDKStringParam(name="profile_pattern", is_visible=False),
        WDKStringParam(name="included_species", allow_empty_value=True),
        WDKStringParam(name="excluded_species", allow_empty_value=True),
        WDKEnumParam(
            name="phyletic_indent_map",
            type="multi-pick-vocabulary",
            vocabulary=_INDENTS if indents is None else indents,
        ),
    ]
    if with_term_map:
        params.append(
            WDKEnumParam(
                name="phyletic_term_map",
                type="multi-pick-vocabulary",
                vocabulary=_TERMS if terms is None else terms,
            )
        )
    return params


class TestAPhyleticSearch:
    def test_yields_the_hierarchy(self) -> None:
        tree = phyletic_tree_of(_params())

        assert tree is not None
        assert [r.code for r in tree.roots] == ["EUKA"]
        assert [c.code for c in tree.roots[0].children] == ["MAMM", "pfal"]

    def test_two_empty_maps_are_an_empty_tree(self) -> None:
        tree = phyletic_tree_of(_params(terms=[], indents=[]))

        assert tree is not None
        assert tree.roots == []


class TestNotAPhyleticSearch:
    def test_a_search_missing_one_of_the_five_names(self) -> None:
        params = _params(with_term_map=False)

        assert [p.name for p in params] == _FIVE_NAMES[:4]
        assert phyletic_tree_of(params) is None

    def test_an_ordinary_search(self) -> None:
        params: list[WDKParameter] = [WDKStringParam(name="text_expression")]

        assert [p.name for p in params] == ["text_expression"]
        assert phyletic_tree_of(params) is None

    def test_a_tree_shaped_map_is_not_a_phyletic_vocabulary(self) -> None:
        params = [p for p in _params() if p.name != "phyletic_term_map"]
        params.append(
            WDKEnumParam(
                name="phyletic_term_map",
                type="multi-pick-vocabulary",
                vocabulary=WDKTreeBoxVocabNode(
                    data=WDKVocabNodeData(term="root", display="root")
                ),
            )
        )

        assert sorted(p.name for p in params) == sorted(_FIVE_NAMES)
        assert phyletic_tree_of(params) is None


class TestAnUnreadableTree:
    """Without the depths every node is a root, so a clade expands to nothing.

    A clade that expands to nothing reaches WDK as a code the census never
    holds, and the search answers 0 rows instead of an error.
    """

    def test_an_empty_indent_map_beside_a_term_map(self) -> None:
        params = _params(indents=[])
        indent_map = next(p for p in params if p.name == "phyletic_indent_map")

        assert isinstance(indent_map, WDKEnumParam)
        assert indent_map.vocabulary == []
        assert phyletic_tree_of(params) is None
