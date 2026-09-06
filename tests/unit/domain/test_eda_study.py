from __future__ import annotations

from veupathdb.domain.eda_study import (
    VEUPATHDB_GENE_ID,
    ancestor_entity_ids,
    entity_by_id,
    is_multi_valued,
    listed,
    variable_by_id,
    vocabulary_of,
    walk_entities,
)

from ._eda_facts import Ent, Study, Var, counts_study


def _found_id(root: Ent, entity_id: str) -> str:
    found = entity_by_id(root, entity_id)
    return "" if found is None else found.id


def test_walk_visits_the_root_and_every_descendant() -> None:
    ids = [entity.id for entity in walk_entities(counts_study().root_entity)]
    assert ids == ["ENT_8151325d", "ENT_fd574cd6"]


def test_entity_by_id_finds_a_descendant() -> None:
    found = entity_by_id(counts_study().root_entity, "ENT_fd574cd6")
    assert found is not None
    assert found.display_name == "pfal3D7 htseq counts"


def test_entity_by_id_returns_none_for_an_unknown_id() -> None:
    assert _found_id(counts_study().root_entity, "ENT_nope") == ""


def test_ancestors_of_a_leaf_are_every_entity_above_it() -> None:
    assert ancestor_entity_ids(counts_study().root_entity, "ENT_fd574cd6") == frozenset(
        {"ENT_8151325d"}
    )


def test_ancestors_of_the_root_are_empty() -> None:
    assert (
        ancestor_entity_ids(counts_study().root_entity, "ENT_8151325d") == frozenset()
    )


def test_variable_by_id_reads_the_entity_that_declares_it() -> None:
    counts = entity_by_id(counts_study().root_entity, "ENT_fd574cd6")
    assert counts is not None
    found = variable_by_id(counts, VEUPATHDB_GENE_ID)
    assert found is not None
    assert found.id == VEUPATHDB_GENE_ID


def test_vocabulary_and_multi_valued_read_the_variable() -> None:
    single = Var(id="V", vocabulary=["a", "b"])
    assert vocabulary_of(single) == ["a", "b"]
    assert is_multi_valued(single) is False
    assert is_multi_valued(Var(id="M", is_multi_valued=True)) is True


def test_listed_joins_values_for_a_message() -> None:
    assert listed(["b", "a"]) == "b, a"


def test_a_study_of_one_entity_walks_to_that_entity() -> None:
    study = Study(id="S", root_entity=Ent(id="E", variables=[Var(id="V")]))
    assert [entity.id for entity in walk_entities(study.root_entity)] == ["E"]
