"""Organism scope extraction from strategy step trees."""

from collections.abc import Mapping

from veupathdb.domain.parameters.values import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy.ast import StrategyStepNode


def _organism_terms(value: ParamValue) -> set[str]:
    if isinstance(value, MultiPickValue):
        return set(value.values)
    if isinstance(value, (SinglePickValue, StringValue)):
        return {value.value}
    return set()


def _parse_organisms(
    step: StrategyStepNode, organism_params: Mapping[str, str]
) -> set[str] | None:
    name = organism_params.get(step.search_name)
    raw = step.parameters.get(name) if name is not None else None
    terms = _organism_terms(raw) if raw is not None else set()
    return terms or None


def extract_output_organisms(
    step: StrategyStepNode, organism_params: Mapping[str, str]
) -> set[str] | None:
    """Return the organism scope of a step's output, or None if unknown.

    ``organism_params`` maps a search name to the parameter WDK marks with
    ``organismProperties``. GenesByOrthologs yields its target organism, a step
    with a primary input inherits it, and a leaf reads its marked parameter.
    """
    if step.search_name == "GenesByOrthologs":
        return _parse_organisms(step, organism_params)
    if step.primary_input is not None:
        return extract_output_organisms(step.primary_input, organism_params)
    return _parse_organisms(step, organism_params)
