from __future__ import annotations

from veupathdb.domain.eda_study import VEUPATHDB_GENE_ID
from veupathdb.domain.eda_validation import find_gene_entity

from ._eda_facts import Ent, Study, Var, counts_study


def test_exactly_one_gene_id_variable_resolves_the_gene_entity() -> None:
    result = find_gene_entity(counts_study(), subject="strategy step")
    assert result.entity_id == "ENT_fd574cd6"
    assert result.error is None


def test_no_gene_id_variable_is_an_error_naming_the_reserved_id() -> None:
    study = Study(id="S", root_entity=Ent(id="E", variables=[Var(id="V")]))
    result = find_gene_entity(study, subject="strategy step")
    assert result.entity_id is None
    assert result.error == (
        f"Study S carries no {VEUPATHDB_GENE_ID} variable, so it cannot export a "
        f"gene list to a strategy step."
    )


def test_the_subject_names_what_the_gene_list_is_exported_to() -> None:
    study = Study(id="S", root_entity=Ent(id="E", variables=[Var(id="V")]))
    result = find_gene_entity(study, subject="notebook cell")
    assert result.error is not None
    assert result.error.endswith("gene list to a notebook cell.")


def test_two_gene_id_variables_are_an_error_naming_both_entities() -> None:
    study = Study(
        id="S",
        root_entity=Ent(
            id="A",
            variables=[Var(id=VEUPATHDB_GENE_ID)],
            children=[Ent(id="B", variables=[Var(id=VEUPATHDB_GENE_ID)])],
        ),
    )
    result = find_gene_entity(study, subject="strategy step")
    assert result.entity_id is None
    assert result.error == (
        f"Study S carries {VEUPATHDB_GENE_ID} on more than one entity (A, B), and "
        f"the gene bridge requires exactly one."
    )
