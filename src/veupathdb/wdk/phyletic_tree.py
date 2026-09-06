"""Reads the phyletic clade tree off a WDK search definition."""

from veupathdb.domain.parameters.phyletic import PHYLETIC_PARAM_NAMES, PhyleticTree
from veupathdb.wdk.wdk_parameters import WDKParameter


def phyletic_tree_of(params: list[WDKParameter]) -> PhyleticTree | None:
    """The clade tree of a phyletic search, or ``None`` when it is not one.

    A search is phyletic only when it carries all five parameter names and both
    maps are standard enum vocabularies. The indent map carries the depths, so a
    term map without it reads as a tree of roots, in which a clade holds no
    species and expands to nothing.
    """
    by_name = {p.name: p for p in params}
    if not by_name.keys() >= PHYLETIC_PARAM_NAMES:
        return None
    term_map = by_name["phyletic_term_map"].vocabulary
    indent_map = by_name["phyletic_indent_map"].vocabulary
    if not isinstance(term_map, list) or not isinstance(indent_map, list):
        return None
    if term_map and not indent_map:
        return None
    return PhyleticTree.from_vocab(term_map, indent_map)
