"""Genome sequence windows read through a site's JBrowse store."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

from veupathdb.errors import ExternalServiceError, VEuPathDBError, VEuPathDBErrorCode
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.models import TrackList

FASTA_PATH = "{prefix}/genomeAndProteome/fasta/genome.fasta"

_STORE = "JBrowse store"
_FAI_COLUMNS = ("name", "length", "offset", "line_bases", "line_bytes")


class GenomeIndexError(VEuPathDBError[VEuPathDBErrorCode]):
    def __init__(self, detail: str) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.VALIDATION_ERROR,
            title="Genome sequence not found",
            status=404,
            detail=detail,
        )


class FaiEntry(BaseModel):
    model_config = ConfigDict(frozen=True)

    name: str
    length: int
    offset: int
    line_bases: int
    line_bytes: int

    def byte_of(self, position: int) -> int:
        index = position - 1
        return (
            self.offset
            + index // self.line_bases * self.line_bytes
            + index % self.line_bases
        )


class GenomeWindow(BaseModel):
    model_config = ConfigDict(frozen=True)

    seqid: str
    start: int
    sequence: str

    @property
    def end(self) -> int:
        return self.start + len(self.sequence) - 1


def parse_fai(text: str) -> dict[str, FaiEntry]:
    entries = (
        FaiEntry.model_validate(
            dict(zip(_FAI_COLUMNS, line.split("\t")[:5], strict=True))
        )
        for line in text.splitlines()
        if len(line.split("\t")) >= len(_FAI_COLUMNS)
    )
    return {entry.name: entry for entry in entries}


def data_prefix(tracks: TrackList) -> str:
    for track in tracks.tracks:
        path = track.data_path
        if "store?" in track.url_template and "/" in path:
            return path.split("/", 1)[0]
    msg = "the track list names no JBrowse data directory"
    raise GenomeIndexError(msg)


class GenomeReader:
    def __init__(self, client: JBrowseClient) -> None:
        self._client = client
        self._prefixes: dict[str, str] = {}
        self._indexes: dict[str, dict[str, FaiEntry]] = {}

    async def _fasta(self, abbrev: str) -> str:
        if abbrev not in self._prefixes:
            tracks = await self._client.track_list("organismSpecific", abbrev)
            self._prefixes[abbrev] = data_prefix(tracks)
        return FASTA_PATH.format(prefix=self._prefixes[abbrev])

    async def _entry(self, abbrev: str, seqid: str) -> FaiEntry:
        if abbrev not in self._indexes:
            raw = await self._client.store_bytes(await self._fasta(abbrev) + ".fai")
            self._indexes[abbrev] = parse_fai(raw.decode())
        index = self._indexes[abbrev]
        if seqid not in index:
            msg = f"the genome index of {abbrev} has no sequence {seqid}"
            raise GenomeIndexError(msg)
        return index[seqid]

    async def sequence_length(self, abbrev: str, seqid: str) -> int:
        return (await self._entry(abbrev, seqid)).length

    async def window(
        self, abbrev: str, seqid: str, start: int, end: int
    ) -> GenomeWindow:
        entry = await self._entry(abbrev, seqid)
        first, last = max(1, start), min(entry.length, end)
        if first > last:
            msg = (
                f"{seqid}:{start}-{end} holds no base of a {entry.length} base sequence"
            )
            raise GenomeIndexError(msg)
        raw = await self._client.store_bytes(
            await self._fasta(abbrev), (entry.byte_of(first), entry.byte_of(last))
        )
        text = raw.decode().replace("\r", "").replace("\n", "").upper()
        if len(text) != last - first + 1:
            msg = f"{seqid}:{first}-{last} read {len(text)} of {last - first + 1} bases"
            raise ExternalServiceError(_STORE, msg)
        return GenomeWindow(seqid=seqid, start=first, sequence=text)
