from __future__ import annotations

from dataclasses import dataclass, field

from veupathdb.domain.eda_compute_validation import validate_compute_config
from veupathdb.domain.eda_study import VEUPATHDB_GENE_ID

from ._eda_facts import Ent, Study, Var, counts_study

_COUNTS = "ENT_fd574cd6"
_SAMPLES = "ENT_8151325d"
_TEMPERATURE = "VAR_081ab087"
_READS = "SEQUENCE_READ_COUNT_SENSE"


@dataclass(frozen=True)
class Spec:
    entity_id: str
    variable_id: str


@dataclass(frozen=True)
class Group:
    label: str


@dataclass(frozen=True)
class Comparator:
    variable: Spec
    group_a: list[Group] = field(default_factory=list)
    group_b: list[Group] = field(default_factory=list)


@dataclass(frozen=True)
class Config:
    identifier_variable: Spec
    value_variable: Spec
    comparator: Comparator
    differential_expression_method: str = "DESeq"


def _comparator(group_a: list[str], group_b: list[str], variable: Spec) -> Comparator:
    return Comparator(
        variable=variable,
        group_a=[Group(label) for label in group_a],
        group_b=[Group(label) for label in group_b],
    )


def _config(**overrides: object) -> Config:
    base = Config(
        identifier_variable=Spec(_COUNTS, VEUPATHDB_GENE_ID),
        value_variable=Spec(_COUNTS, _READS),
        comparator=_comparator(["normal"], ["febrile"], Spec(_SAMPLES, _TEMPERATURE)),
    )
    return Config(**{**base.__dict__, **overrides})


def _errors(**overrides: object) -> list[str]:
    return validate_compute_config(counts_study(), _config(**overrides))


def _on_temperature(group_a: list[str], group_b: list[str]) -> list[str]:
    return _errors(
        comparator=_comparator(group_a, group_b, Spec(_SAMPLES, _TEMPERATURE))
    )


def test_the_measured_working_configuration_is_accepted() -> None:
    assert _errors() == []


def test_limma_is_accepted() -> None:
    assert _errors(differential_expression_method="limma") == []


def test_deseq2_is_refused_with_the_two_wire_values_named() -> None:
    errors = _errors(differential_expression_method="DESeq2")
    assert len(errors) == 1
    assert "DESeq" in errors[0]
    assert "limma" in errors[0]


class TestTheInputVariables:
    def test_the_two_input_variables_must_share_an_entity(self) -> None:
        """A different entity is accepted at submit and the job then fails."""
        errors = _errors(value_variable=Spec(_SAMPLES, _TEMPERATURE))
        assert len(errors) == 1
        assert "same entity" in errors[0]

    def test_an_identifier_variable_that_is_not_the_reserved_gene_id_is_refused(
        self,
    ) -> None:
        assert _errors(identifier_variable=Spec(_COUNTS, _READS)) == [
            (
                f"identifierVariable names {_READS}, and differentialexpression accepts "
                f"only {VEUPATHDB_GENE_ID}."
            )
        ]

    def test_a_value_variable_outside_the_reserved_ids_is_refused(self) -> None:
        study = Study(
            id="S",
            root_entity=Ent(
                id="P",
                variables=[Var(id="C", vocabulary=["a", "b"])],
                children=[
                    Ent(
                        id="E",
                        variables=[
                            Var(id=VEUPATHDB_GENE_ID),
                            Var(id="MADE_UP", type="number"),
                        ],
                    )
                ],
            ),
        )
        assert validate_compute_config(
            study,
            Config(
                identifier_variable=Spec("E", VEUPATHDB_GENE_ID),
                value_variable=Spec("E", "MADE_UP"),
                comparator=_comparator(["a"], ["b"], Spec("P", "C")),
            ),
        ) == [
            (
                "valueVariable names MADE_UP, and differentialexpression accepts "
                "NORMALIZED_EXPRESSION, NORMALIZED_INTENSITY, SEQUENCE_READ_COUNT, "
                "SEQUENCE_READ_COUNT_ANTISENSE, SEQUENCE_READ_COUNT_SENSE."
            )
        ]

    def test_an_input_entity_the_study_does_not_carry_is_refused(self) -> None:
        errors = _errors(identifier_variable=Spec("ENT_nope", VEUPATHDB_GENE_ID))
        assert len(errors) == 1
        assert "ENT_nope" in errors[0]
        assert "identifierVariable" in errors[0]


class TestTheComparator:
    def test_the_comparator_variable_must_sit_on_an_ancestor_entity(self) -> None:
        assert _errors(comparator=_comparator(["a"], ["b"], Spec(_COUNTS, _READS))) == [
            (
                f"comparator.variable is on entity {_COUNTS}, and the plugin reads the "
                f"comparator from an ancestor entity of {_COUNTS}. The ancestor "
                f"entities are {_SAMPLES}."
            )
        ]

    def test_a_comparator_variable_the_entity_does_not_declare_is_refused(self) -> None:
        errors = _errors(
            comparator=_comparator(
                ["normal"], ["febrile"], Spec(_SAMPLES, "VAR_deadbeef")
            )
        )
        assert len(errors) == 1
        assert "VAR_deadbeef" in errors[0]
        assert "comparator.variable" in errors[0]

    def test_a_group_label_outside_the_vocabulary_is_refused(self) -> None:
        """Accepted at submit; the job then produces a wrong or empty answer."""
        errors = _on_temperature(["NOT_A_VALUE"], ["febrile"])
        assert len(errors) == 1
        assert "NOT_A_VALUE" in errors[0]
        assert "febrile" in errors[0]

    def test_an_empty_group_is_refused(self) -> None:
        assert _on_temperature([], ["febrile"]) == [
            (
                "comparator groupA is empty, and the plugin needs a label in each group "
                "to name the two sides of the comparison."
            )
        ]

    def test_an_empty_group_b_is_refused(self) -> None:
        assert _on_temperature(["normal"], []) == [
            (
                "comparator groupB is empty, and the plugin needs a label in each group "
                "to name the two sides of the comparison."
            )
        ]

    def test_the_two_groups_may_not_share_a_label(self) -> None:
        assert _on_temperature(["normal"], ["normal"]) == [
            (
                "comparator names normal in both groups, and a sample cannot be its own "
                "control."
            )
        ]

    def test_a_category_comparator_variable_is_refused(self) -> None:
        """A category groups other variables, so it has no values a label can name."""
        study = Study(
            id="S",
            root_entity=Ent(
                id="P",
                variables=[
                    Var(id="CAT_C", type="category", display_type="multifilter"),
                    Var(id="CHILD_C", parent_id="CAT_C", vocabulary=["Yes"]),
                ],
                children=[
                    Ent(
                        id="E",
                        variables=[
                            Var(id=VEUPATHDB_GENE_ID),
                            Var(id="SEQUENCE_READ_COUNT", type="integer"),
                        ],
                    )
                ],
            ),
        )
        assert validate_compute_config(
            study,
            Config(
                identifier_variable=Spec("E", VEUPATHDB_GENE_ID),
                value_variable=Spec("E", "SEQUENCE_READ_COUNT"),
                comparator=_comparator(["Yes"], ["No"], Spec("P", "CAT_C")),
            ),
        ) == [
            (
                "comparator.variable names CAT_C, which is a category variable. A category "
                "groups other variables and holds no values, so no label can name a side "
                "of the comparison."
            )
        ]

    def test_a_comparator_variable_with_no_vocabulary_accepts_any_label(self) -> None:
        study = Study(
            id="S",
            root_entity=Ent(
                id="P",
                variables=[Var(id="FREE_TEXT")],
                children=[
                    Ent(
                        id="E",
                        variables=[
                            Var(id=VEUPATHDB_GENE_ID),
                            Var(id="SEQUENCE_READ_COUNT", type="integer"),
                        ],
                    )
                ],
            ),
        )
        assert (
            validate_compute_config(
                study,
                Config(
                    identifier_variable=Spec("E", VEUPATHDB_GENE_ID),
                    value_variable=Spec("E", "SEQUENCE_READ_COUNT"),
                    comparator=_comparator(
                        ["anything"], ["else"], Spec("P", "FREE_TEXT")
                    ),
                ),
            )
            == []
        )
