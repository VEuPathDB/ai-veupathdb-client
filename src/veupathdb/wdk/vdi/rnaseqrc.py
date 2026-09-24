"""The file set an rnaseqrc upload sends: the count files, the sample info, the manifest.

The rules are the upload contract that the site's form and the wrangler plugin share.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import BinaryIO

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

SAMPLE_INFO_MAX_BYTES = 100_000
SAMPLE_INFO_NAME = "sample-info.txt"
MANIFEST_NAME = "manifest.tsv"


class RnaSeqRole(StrEnum):
    """The role a manifest line gives one file."""

    SENSE = "sense"
    ANTISENSE = "antisense"
    UNSTRANDED = "unstranded"
    SAMPLE_INFO = "sample-info"


@dataclass(frozen=True)
class RnaSeqCountFile:
    """One count file: the name the user gave it and an open binary stream."""

    name: str
    content: BinaryIO


class RnaSeqRcUpload(BaseModel):
    """One unstranded count file or a sense and antisense pair, with sample details."""

    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    counts: tuple[RnaSeqCountFile] | tuple[RnaSeqCountFile, RnaSeqCountFile]
    sample_details: str

    @field_validator("sample_details")
    @classmethod
    def _within_the_cap(cls, value: str) -> str:
        if not value.strip():
            msg = "The sample details are empty."
            raise ValueError(msg)
        size = len(value.encode())
        if size > SAMPLE_INFO_MAX_BYTES:
            msg = (
                f"The sample details are {size} bytes; the limit is "
                f"{SAMPLE_INFO_MAX_BYTES} bytes."
            )
            raise ValueError(msg)
        return value

    @model_validator(mode="after")
    def _names_fit_the_manifest(self) -> RnaSeqRcUpload:
        seen: set[str] = set()
        for count in self.counts:
            if "\t" in count.name:
                msg = f"The file name {count.name!r} contains a tab."
                raise ValueError(msg)
            key = count.name.lower()
            if key == MANIFEST_NAME:
                msg = f"{count.name!r} is a reserved name. Rename the file."
                raise ValueError(msg)
            if key in seen:
                msg = f"Two count files have the same name: {count.name!r}."
                raise ValueError(msg)
            seen.add(key)
        return self

    def _roles(self) -> tuple[RnaSeqRole, ...]:
        if len(self.counts) == 1:
            return (RnaSeqRole.UNSTRANDED,)
        return (RnaSeqRole.SENSE, RnaSeqRole.ANTISENSE)

    def _sample_info_name(self) -> str:
        """``sample-info.txt``, or ``sample-info-N.txt`` when a count file holds it."""
        taken = {count.name.lower() for count in self.counts}
        stem, dot, extension = SAMPLE_INFO_NAME.rpartition(".")
        candidate = SAMPLE_INFO_NAME
        number = 0
        while candidate.lower() in taken:
            number += 1
            candidate = f"{stem}-{number}{dot}{extension}"
        return candidate

    def files(
        self, allowed_extensions: Sequence[str]
    ) -> list[tuple[str, BinaryIO | bytes]]:
        """The parts to send, in order: the counts, the sample info, the manifest.

        VDI does not check each file's extension on a multi-file upload, so this does.
        """
        for count in self.counts:
            lower = count.name.lower()
            if not any(lower.endswith(ext.lower()) for ext in allowed_extensions):
                msg = (
                    f"Unsupported file type: {count.name}. Permitted types are "
                    f"{', '.join(allowed_extensions)}."
                )
                raise ValueError(msg)
        sample_info = self._sample_info_name()
        lines = [
            f"{role}\t{count.name}"
            for role, count in zip(self._roles(), self.counts, strict=True)
        ]
        lines.append(f"{RnaSeqRole.SAMPLE_INFO}\t{sample_info}")
        manifest = "".join(f"{line}\n" for line in lines)
        return [
            *((count.name, count.content) for count in self.counts),
            (sample_info, self.sample_details.encode()),
            (MANIFEST_NAME, manifest.encode()),
        ]
