from __future__ import annotations

from typing import Self

import pydantic
from pydantic import BaseModel, ConfigDict, Field, model_validator

from veupathdb.errors import ValidationError


class GenomeRegion(BaseModel):
    model_config = ConfigDict(frozen=True)

    seqid: str
    start: int = Field(ge=1)
    end: int

    @model_validator(mode="after")
    def _ordered(self) -> Self:
        if self.end < self.start:
            msg = f"the region {self.start}-{self.end} ends before it starts"
            raise ValueError(msg)
        return self

    @property
    def length(self) -> int:
        return self.end - self.start + 1


def genome_region(seqid: str, start: int, end: int) -> GenomeRegion:
    try:
        return GenomeRegion(seqid=seqid, start=start, end=end)
    except pydantic.ValidationError as error:
        raise ValidationError(
            title="Genome region not valid", detail=f"{seqid}:{start}-{end}: {error}"
        ) from error
