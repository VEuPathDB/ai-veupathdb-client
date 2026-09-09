"""Why a differentialexpression compute config will fail or mislead.

The shapes are structural, so this module imports no other layer.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from veupathdb.domain.eda_study import (
    CATEGORY_TYPE,
    VEUPATHDB_GENE_ID,
    StudyFacts,
    VariableFacts,
    ancestor_entity_ids,
    entity_by_id,
    listed,
    variable_by_id,
    vocabulary_of,
    walk_entities,
)

GENE_EXPRESSION_VALUE_IDS = frozenset(
    {
        "SEQUENCE_READ_COUNT",
        "SEQUENCE_READ_COUNT_SENSE",
        "SEQUENCE_READ_COUNT_ANTISENSE",
        "NORMALIZED_EXPRESSION",
        "NORMALIZED_INTENSITY",
    }
)

DIFFERENTIAL_EXPRESSION_METHODS = frozenset({"DESeq", "limma"})


class VariableSpecFacts(Protocol):
    @property
    def entity_id(self) -> str: ...
    @property
    def variable_id(self) -> str: ...


class LabeledRangeFacts(Protocol):
    @property
    def label(self) -> str: ...


class ComparatorFacts(Protocol):
    @property
    def variable(self) -> VariableSpecFacts: ...
    @property
    def group_a(self) -> Sequence[LabeledRangeFacts]: ...
    @property
    def group_b(self) -> Sequence[LabeledRangeFacts]: ...


class ComputeConfigFacts(Protocol):
    @property
    def identifier_variable(self) -> VariableSpecFacts: ...
    @property
    def value_variable(self) -> VariableSpecFacts: ...
    @property
    def comparator(self) -> ComparatorFacts: ...
    @property
    def differential_expression_method(self) -> str: ...


def validate_compute_config(
    study: StudyFacts,
    config: ComputeConfigFacts,
) -> list[str]:
    """Every reason this differentialexpression config will fail or mislead.

    Submission validates schema shape and study permission only, so a bad
    entity pairing or an out-of-vocabulary label reaches a failed job.
    """
    comparator_variable = _variable_at(study, config.comparator.variable)
    if comparator_variable is None:
        return _unresolved_specs(study, config)
    unresolved = _unresolved_specs(study, config)
    if unresolved:
        return unresolved
    return [
        *_pairing_errors(config),
        *_comparator_errors(study, config, comparator_variable),
        *_method_errors(config),
    ]


def _variable_at(study: StudyFacts, spec: VariableSpecFacts) -> VariableFacts | None:
    entity = entity_by_id(study.root_entity, spec.entity_id)
    if entity is None:
        return None
    return variable_by_id(entity, spec.variable_id)


def _unresolved_specs(study: StudyFacts, config: ComputeConfigFacts) -> list[str]:
    named = (
        ("identifierVariable", config.identifier_variable),
        ("valueVariable", config.value_variable),
        ("comparator.variable", config.comparator.variable),
    )
    return [
        _unresolved_message(study, name, spec)
        for name, spec in named
        if _variable_at(study, spec) is None
    ]


def _unresolved_message(
    study: StudyFacts,
    name: str,
    spec: VariableSpecFacts,
) -> str:
    entity = entity_by_id(study.root_entity, spec.entity_id)
    if entity is None:
        known = [entry.id for entry in walk_entities(study.root_entity)]
        return (
            f"{name} names entity {spec.entity_id}, which study {study.id} does not "
            f"carry. Its entities are {listed(known)}."
        )
    return (
        f"{name} names variable {spec.variable_id}, which entity {entity.id} does "
        f"not declare."
    )


def _pairing_errors(config: ComputeConfigFacts) -> list[str]:
    identifier = config.identifier_variable
    value = config.value_variable
    if identifier.entity_id != value.entity_id:
        return [
            (
                f"identifierVariable is on entity {identifier.entity_id} and "
                f"valueVariable is on entity {value.entity_id}. The plugin needs both "
                f"on the same entity."
            )
        ]
    errors: list[str] = []
    if identifier.variable_id != VEUPATHDB_GENE_ID:
        errors.append(
            f"identifierVariable names {identifier.variable_id}, and "
            f"differentialexpression accepts only {VEUPATHDB_GENE_ID}."
        )
    if value.variable_id not in GENE_EXPRESSION_VALUE_IDS:
        errors.append(
            f"valueVariable names {value.variable_id}, and differentialexpression "
            f"accepts {listed(sorted(GENE_EXPRESSION_VALUE_IDS))}."
        )
    return errors


def _comparator_errors(
    study: StudyFacts,
    config: ComputeConfigFacts,
    comparator_variable: VariableFacts,
) -> list[str]:
    comparator = config.comparator
    errors = _comparator_entity_errors(study, config)
    group_a = [entry.label for entry in comparator.group_a]
    group_b = [entry.label for entry in comparator.group_b]
    for name, labels in (("groupA", group_a), ("groupB", group_b)):
        if not labels:
            errors.append(
                f"comparator {name} is empty, and the plugin needs a label in each "
                f"group to name the two sides of the comparison."
            )
    shared = sorted(set(group_a) & set(group_b))
    if shared:
        errors.append(
            f"comparator names {listed(shared)} in both groups, and a sample "
            f"cannot be its own control."
        )
    if comparator_variable.type == CATEGORY_TYPE:
        errors.append(
            f"comparator.variable names {comparator_variable.id}, which is a "
            f"{CATEGORY_TYPE} variable. A category groups other variables and "
            f"holds no values, so no label can name a side of the comparison."
        )
    vocabulary = vocabulary_of(comparator_variable)
    if vocabulary is None:
        return errors
    unknown = [label for label in group_a + group_b if label not in vocabulary]
    if unknown:
        errors.append(
            f"comparator names the labels {listed(unknown)}, which the vocabulary "
            f"of {comparator_variable.id} does not carry. The vocabulary is "
            f"{listed(vocabulary)}."
        )
    return errors


def _comparator_entity_errors(
    study: StudyFacts,
    config: ComputeConfigFacts,
) -> list[str]:
    identifier_entity = config.identifier_variable.entity_id
    ancestors = ancestor_entity_ids(study.root_entity, identifier_entity)
    comparator_entity = config.comparator.variable.entity_id
    if comparator_entity in ancestors:
        return []
    return [
        (
            f"comparator.variable is on entity {comparator_entity}, and the plugin "
            f"reads the comparator from an ancestor entity of {identifier_entity}. "
            f"The ancestor entities are {listed(sorted(ancestors))}."
        )
    ]


def _method_errors(config: ComputeConfigFacts) -> list[str]:
    method = config.differential_expression_method
    if method in DIFFERENTIAL_EXPRESSION_METHODS:
        return []
    return [
        (
            f"differentialExpressionMethod is {method}, and the service accepts "
            f"{listed(sorted(DIFFERENTIAL_EXPRESSION_METHODS))}."
        )
    ]
