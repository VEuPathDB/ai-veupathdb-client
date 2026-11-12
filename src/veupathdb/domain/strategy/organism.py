"""Organism scope extraction from strategy step trees."""

from collections.abc import Collection, Mapping
from types import MappingProxyType

from veupathdb.domain.parameters.values import (
    MultiPickValue,
    ParamValue,
    SinglePickValue,
    StringValue,
)
from veupathdb.domain.strategy.ast import StrategyStepNode
from veupathdb.domain.strategy.ops import CombineOp


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


def _leaf_organisms(
    step: StrategyStepNode,
    organism_params: Mapping[str, str],
    leaf_organisms: Mapping[str, Collection[str]],
) -> set[str] | None:
    if step.search_name in organism_params:
        return _parse_organisms(step, organism_params)
    return set(leaf_organisms.get(step.id, ())) or None


def _fold(
    step: StrategyStepNode, primary: set[str] | None, secondary: set[str] | None
) -> set[str] | None:
    if step.operator in (CombineOp.MINUS, CombineOp.LONLY):
        return primary
    if step.operator in (CombineOp.RMINUS, CombineOp.RONLY):
        return secondary
    if step.colocation_params is not None:
        return primary if step.colocation_params.output == "a" else secondary
    if primary is None or secondary is None:
        return None
    return primary | secondary


def extract_output_organisms(
    step: StrategyStepNode,
    organism_params: Mapping[str, str],
    leaf_organisms: Mapping[str, Collection[str]] = MappingProxyType({}),
) -> set[str] | None:
    """Return the organism scope of a step's output, or None if unknown.

    ``organism_params`` maps a search name to the parameter WDK marks with
    ``organismProperties``. ``leaf_organisms`` maps a step id to the organisms of
    a leaf whose search marks no such parameter. A combine folds both inputs.
    """
    if step.search_name == "GenesByOrthologs":
        return _parse_organisms(step, organism_params)
    if step.primary_input is None:
        return _leaf_organisms(step, organism_params, leaf_organisms)
    primary = extract_output_organisms(
        step.primary_input, organism_params, leaf_organisms
    )
    if step.secondary_input is None:
        return primary
    secondary = extract_output_organisms(
        step.secondary_input, organism_params, leaf_organisms
    )
    return _fold(step, primary, secondary)
