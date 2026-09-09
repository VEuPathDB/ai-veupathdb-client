"""Structural stand-ins for the EDA wire shapes the pure predicates walk."""

from __future__ import annotations

from dataclasses import dataclass, field

from veupathdb.domain.eda_study import VEUPATHDB_GENE_ID


@dataclass(frozen=True)
class Var:
    id: str
    type: str = "string"
    display_name: str = ""
    display_type: str = "default"
    parent_id: str | None = None
    vocabulary: list[str] | None = None
    is_multi_valued: bool = False
    data_shape: str | None = None


@dataclass(frozen=True)
class Ent:
    id: str
    display_name: str = ""
    variables: list[Var] = field(default_factory=list)
    children: list["Ent"] = field(default_factory=list)


@dataclass(frozen=True)
class Study:
    id: str
    root_entity: Ent


@dataclass(frozen=True)
class Sub:
    variable_id: str
    string_set: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Filt:
    entity_id: str
    variable_id: str
    type: str
    string_set: list[str] = field(default_factory=list)
    number_set: list[float] = field(default_factory=list)
    date_set: list[str] = field(default_factory=list)
    min: float | str | None = None
    max: float | str | None = None
    left: float | None = None
    right: float | None = None
    operation: str = "union"
    sub_filters: list[Sub] = field(default_factory=list)


@dataclass(frozen=True)
class BareFilt:
    entity_id: str
    variable_id: str
    type: str


GENE_PHENOTYPE = "GENE_PHENOTYPE_DATA_ENTITY"


def phenotype_study() -> Study:
    """One entity carrying every variable type the filter checks branch on."""
    return Study(
        id="STUDY_53f554ec6a",
        root_entity=Ent(
            id=GENE_PHENOTYPE,
            variables=[
                Var(
                    id="VAR_a8ad31c0",
                    type="string",
                    display_name="Success of Genetic Modification",
                    vocabulary=["no", "yes"],
                ),
                Var(
                    id="EUPATH_0043064",
                    type="integer",
                    display_name="count",
                    data_shape="continuous",
                ),
                Var(
                    id="EUPATH_0043256",
                    type="date",
                    display_name="Collection date",
                    vocabulary=["2017-05-05", "2017-05-11"],
                ),
                Var(id="OBI_0001621", type="longitude", display_name="longitude"),
                Var(
                    id="CAT_1",
                    type="category",
                    display_name="Diagnosis",
                    display_type="multifilter",
                ),
                Var(
                    id="CHILD_1",
                    type="string",
                    display_name="Malaria",
                    parent_id="CAT_1",
                    vocabulary=["Yes"],
                ),
            ],
        ),
    )


def counts_study() -> Study:
    """A samples entity above a gene-counts entity, the differential-expression shape."""
    counts = Ent(
        id="ENT_fd574cd6",
        display_name="pfal3D7 htseq counts",
        variables=[
            Var(id=VEUPATHDB_GENE_ID),
            Var(id="SEQUENCE_READ_COUNT_SENSE", type="number"),
        ],
    )
    samples = Ent(
        id="ENT_8151325d",
        display_name="Samples",
        variables=[
            Var(
                id="VAR_081ab087",
                display_name="temperature",
                vocabulary=["febrile", "normal"],
            )
        ],
        children=[counts],
    )
    return Study(id="STUDY_e973eadd57", root_entity=samples)
