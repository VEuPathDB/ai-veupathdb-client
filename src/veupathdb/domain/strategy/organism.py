"""Organism scope extraction from strategy step trees."""

from collections.abc import Mapping

from veupathdb.domain.parameters.values import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy.ast import StrategyStepNode

_ORGANISM_PARAMS = ("organism", "text_search_organism")


def _organism_terms(value: ParamValue) -> set[str]:
    if isinstance(value, MultiPickValue):
        return set(value.values)
    if isinstance(value, (SinglePickValue, StringValue)):
        return {value.value}
    return set()


def _parse_organisms(params: Mapping[str, ParamValue]) -> set[str] | None:
    for key in _ORGANISM_PARAMS:
        raw = params.get(key)
        if raw is not None:
            terms = _organism_terms(raw)
            if terms:
                return terms
    return None


def extract_output_organisms(step: StrategyStepNode) -> set[str] | None:
    """Return the organism scope of a step's output, or None if unknown.

    GenesByOrthologs changes the scope to its target organism.
    Combines and other transforms inherit from their primary input.
    Leaf steps use their organism parameter directly.
    """
    # Ortholog transform defines its own output organism.
    if step.search_name == "GenesByOrthologs" and step.parameters:
        return _parse_organisms(step.parameters)

    # Any step with a primary input inherits from it.
    if step.primary_input is not None:
        return extract_output_organisms(step.primary_input)

    # Leaf: read organism directly.
    return _parse_organisms(step.parameters) if step.parameters else None
