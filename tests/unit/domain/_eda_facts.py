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
