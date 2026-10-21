"""One GFF3 feature line of a genome browser track, typed column by column."""

from __future__ import annotations

from typing import Literal, Self
from urllib.parse import unquote

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from veupathdb.jbrowse.errors import TrackReadError

GFF_COLUMNS = (
    "seqid",
    "source",
    "kind",
    "start",
    "end",
    "score",
    "strand",
    "phase",
    "attributes",
)
_EMPTY = "."


def parse_attributes(text: str) -> dict[str, tuple[str, ...]]:
    pairs: dict[str, tuple[str, ...]] = {}
    for part in filter(None, (piece.strip() for piece in text.split(";"))):
        key, separator, value = part.partition("=")
        if not separator:
            msg = f"the GFF attribute {part!r} has no value"
            raise ValueError(msg)
        name = unquote(key)
        if name in pairs:
            msg = f"the GFF attribute {name!r} appears twice"
            raise ValueError(msg)
        pairs[name] = tuple(unquote(one) for one in value.split(",")) if value else ()
    return pairs


class GffFeature(BaseModel):
    model_config = ConfigDict(frozen=True)

    seqid: str = Field(min_length=1)
    source: str
    kind: str
    start: int = Field(ge=1)
    end: int
    score: float | None
    strand: Literal["+", "-", ".", "?"]
    phase: int | None = Field(ge=0, le=2)
    attributes: dict[str, tuple[str, ...]]

    @field_validator("score", "phase", mode="before")
    @classmethod
    def _absent(cls, value: str) -> str | None:
        return None if value == _EMPTY else value

    @field_validator("attributes", mode="before")
    @classmethod
    def _pairs(cls, value: str) -> dict[str, tuple[str, ...]]:
        return parse_attributes(value)

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            msg = f"the feature ends before it starts: {self.start}-{self.end}"
            raise ValueError(msg)
        return self


def parse_gff_line(line: str) -> GffFeature:
    columns = line.rstrip("\r\n").split("\t")
    if len(columns) != len(GFF_COLUMNS):
        msg = f"a GFF line has 9 columns, this one has {len(columns)}: {line!r}"
        raise TrackReadError(msg)
    try:
        return GffFeature.model_validate(dict(zip(GFF_COLUMNS, columns, strict=True)))
    except ValidationError as error:
        msg = f"{error} in the line {line!r}"
        raise TrackReadError(msg) from error
