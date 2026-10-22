"""Records the JBrowse bodies the hermetic genome and junction tests read.

Usage::

    python -m veupathdb.devtools.jbrowse_capture record
    python -m veupathdb.devtools.jbrowse_capture junctions
    python -m veupathdb.devtools.jbrowse_capture coverage

Recording needs WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD.
"""

from __future__ import annotations

import asyncio
import datetime
import struct
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter

from veupathdb.devtools.qa_sites import use_qa_sites
from veupathdb.jbrowse.bigwig import (
    BIGWIG_MAX_BLOCKS,
    BIGWIG_MAX_RTREE_DEPTH,
    BigWigReader,
)
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.genome import FASTA_PATH, data_prefix, parse_fai
from veupathdb.jbrowse.models import SubTrack, TrackConfig
from veupathdb.jbrowse.tabix import TabixReader
from veupathdb.testing.fixture_store import FIXTURE_ROOT
from veupathdb.testing.wdk_credentials import act_as_the_test_account
from veupathdb.wdk.factory import get_site

FIXTURE_DIR = FIXTURE_ROOT / "jbrowse"
PROVENANCE_FILE = "provenance.json"
SITE = "plasmodb"
ABBREV = "pfal3D7"
CRT_SEQID = "Pf3D7_07_v3"
CRT_EXON1 = (403222, 403312)
TRACKS_FILE = f"{ABBREV}_organism_tracks.json"
INDEX_FILE = f"{ABBREV}_genome.fasta.fai"
WINDOW_FILE = f"{ABBREV}_crt_exon1.fasta"
JUNCTION_ABBREV = "pcynM"
JUNCTION_SEQID = "PcyM_07"
JUNCTION_REGION = (1380000, 1384000)
JUNCTION_TRACKS_FILE = f"{JUNCTION_ABBREV}_junction_tracks.json"
JUNCTION_INDEX_FILE = f"{JUNCTION_ABBREV}_junctions.gff.gz.tbi"
JUNCTION_BLOCKS_FILE = (
    f"{JUNCTION_ABBREV}_junctions_{JUNCTION_SEQID}"
    f"_{JUNCTION_REGION[0]}_{JUNCTION_REGION[1]}.gff.gz"
)
_JUNCTION_EXCHANGES = 3
COVERAGE_SITE = "vectorbase"
COVERAGE_ABBREV = "agamPEST"
COVERAGE_GENE = "AGAP003685"
COVERAGE_SEQID = "AgamP4_2R"
COVERAGE_REGION = (41950997, 41954101)
COVERAGE_STRAND = "-"
COVERAGE_TRACKS_FILE = f"{COVERAGE_ABBREV}_coverage_tracks.json"
COVERAGE_READ_FILE = f"{COVERAGE_ABBREV}_{COVERAGE_GENE}_bigwig_read{{index}}.bin"
STRAND_WORDS = {"+": ("forward", "plus", "(+)"), "-": ("reverse", "minus", "(-)")}
UNREAD_STRAND_WORDS = ("sense", "antisense")
COVERAGE_BUDGET = 1 + 2 + BIGWIG_MAX_RTREE_DEPTH + BIGWIG_MAX_BLOCKS
_INDEX_OFFSET = struct.Struct("<Q")
_INDEX_OFFSET_AT = 24
_USAGE = (
    "usage: python -m veupathdb.devtools.jbrowse_capture record\n"
    "       python -m veupathdb.devtools.jbrowse_capture junctions\n"
    "       python -m veupathdb.devtools.jbrowse_capture coverage"
)


class JBrowseFixtureProvenance(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    site: str
    url: str
    status: int
    recorded_at: str
    reads: str


_PROVENANCE: TypeAdapter[dict[str, JBrowseFixtureProvenance]] = TypeAdapter(
    dict[str, JBrowseFixtureProvenance]
)


class RecordedExchange(BaseModel):
    model_config = ConfigDict(frozen=True)

    url: str
    byte_range: str
    status: int
    body: bytes


class ExchangeRecorder(httpx.AsyncBaseTransport):
    def __init__(
        self, inner: httpx.AsyncBaseTransport, budget: int | None = None
    ) -> None:
        self._inner = inner
        self._budget = budget
        self.exchanges: list[RecordedExchange] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if self._budget is not None and len(self.exchanges) >= self._budget:
            msg = f"the recording spent its budget of {self._budget} requests"
            raise RuntimeError(msg)
        response = await self._inner.handle_async_request(request)
        self.exchanges.append(
            RecordedExchange(
                url=str(request.url),
                byte_range=request.headers.get("Range", ""),
                status=response.status_code,
                body=await response.aread(),
            )
        )
        return response

    async def aclose(self) -> None:
        await self._inner.aclose()


def load_provenance(directory: Path) -> dict[str, JBrowseFixtureProvenance]:
    return _PROVENANCE.validate_json((directory / PROVENANCE_FILE).read_text())


def write_recording(
    into: Path, bodies: dict[str, bytes], entries: dict[str, JBrowseFixtureProvenance]
) -> None:
    into.mkdir(parents=True, exist_ok=True)
    for name, body in bodies.items():
        (into / name).write_bytes(body)
    kept = load_provenance(into) if (into / PROVENANCE_FILE).exists() else {}
    ordered = dict(sorted({**kept, **entries}.items()))
    (into / PROVENANCE_FILE).write_text(
        _PROVENANCE.dump_json(ordered, indent=2).decode() + "\n"
    )


class _Recording:
    def __init__(self, recorder: ExchangeRecorder, site: str) -> None:
        self._recorder = recorder
        self._site = site
        self._recorded_at = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
        self.bodies: dict[str, bytes] = {}
        self.entries: dict[str, JBrowseFixtureProvenance] = {}

    def keep(self, name: str, reads: str, back: int = 1) -> None:
        self.keep_exchange(name, reads, self._recorder.exchanges[-back])

    def keep_exchange(self, name: str, reads: str, exchange: RecordedExchange) -> None:
        self.bodies[name] = exchange.body
        self.entries[name] = JBrowseFixtureProvenance(
            site=self._site,
            url=exchange.url,
            status=exchange.status,
            recorded_at=self._recorded_at,
            reads=reads,
        )


async def _recording_client(
    site: str = SITE, budget: int | None = None
) -> tuple[JBrowseClient, ExchangeRecorder]:
    use_qa_sites()
    await act_as_the_test_account()
    recorder = ExchangeRecorder(httpx.AsyncHTTPTransport(), budget)
    client = JBrowseClient(base_url=get_site(site).web_base_url, transport=recorder)
    return client, recorder


async def record(into: Path = FIXTURE_DIR) -> int:
    client, recorder = await _recording_client()
    recording = _Recording(recorder, SITE)
    try:
        tracks = await client.track_list("organismSpecific", ABBREV)
        recording.keep(TRACKS_FILE, f"the {ABBREV} organism track list")
        fasta = FASTA_PATH.format(prefix=data_prefix(tracks))
        index = await client.store_bytes(f"{fasta}.fai")
        recording.keep(INDEX_FILE, f"the {ABBREV} genome index")
        entry = parse_fai(index.decode())[CRT_SEQID]
        first, last = entry.byte_of(CRT_EXON1[0]), entry.byte_of(CRT_EXON1[1])
        await client.store_bytes(fasta, (first, last))
        recording.keep(
            WINDOW_FILE,
            f"{CRT_SEQID}:{CRT_EXON1[0]}-{CRT_EXON1[1]}, bytes={first}-{last}",
        )
    finally:
        await client.close()
    write_recording(into, recording.bodies, recording.entries)
    return 0


async def record_junctions(into: Path = FIXTURE_DIR) -> int:
    client, recorder = await _recording_client()
    recording = _Recording(recorder, SITE)
    start, end = JUNCTION_REGION
    try:
        (track,) = await client.junction_tracks(JUNCTION_ABBREV)
        recording.keep(JUNCTION_TRACKS_FILE, f"the {JUNCTION_ABBREV} junction tracks")
        await TabixReader(client).lines(track, JUNCTION_SEQID, start, end)
    finally:
        await client.close()
    if len(recorder.exchanges) != _JUNCTION_EXCHANGES:
        msg = f"{JUNCTION_SEQID}:{start}-{end} read no block of {track.data_path}"
        raise RuntimeError(msg)
    recording.keep(JUNCTION_INDEX_FILE, f"the index of {track.data_path}", back=2)
    recording.keep(
        JUNCTION_BLOCKS_FILE,
        f"{JUNCTION_SEQID}:{start}-{end}, {recorder.exchanges[-1].byte_range}",
    )
    write_recording(into, recording.bodies, recording.entries)
    return 0


def strand_of(subtrack: SubTrack) -> str | None:
    name = subtrack.name.lower()
    if any(word in name for word in UNREAD_STRAND_WORDS):
        return "unread"
    for strand, words in STRAND_WORDS.items():
        if any(word in name for word in words):
            return strand
    return None


def coverage_subtrack(tracks: list[TrackConfig], strand: str) -> SubTrack | None:
    pairs = [(track, sub) for track in tracks for sub in track.subtracks()]
    unstranded = [(track, sub) for track, sub in pairs if strand_of(sub) is None]
    unified = [
        sub
        for track, sub in unstranded
        if "unified" in track.key.lower() or "unified" in track.label.lower()
    ]
    for candidates in (
        [sub for _, sub in pairs if strand_of(sub) == strand],
        unified,
        [sub for _, sub in unstranded],
    ):
        if candidates:
            return candidates[0]
    return None


def _read_role(index: int, exchange: RecordedExchange, index_at: int) -> str:
    first = int(exchange.byte_range.removeprefix("bytes=").split("-")[0])
    if index == 1:
        return "the header and zoom headers"
    if index == 2:
        return "the chromosome tree"
    if first == index_at:
        return "the R-tree header and root"
    if first > index_at:
        return "an R-tree node"
    return "a data block"


async def record_coverage(into: Path = FIXTURE_DIR) -> int:
    client, recorder = await _recording_client(COVERAGE_SITE, COVERAGE_BUDGET)
    recording = _Recording(recorder, COVERAGE_SITE)
    start, end = COVERAGE_REGION
    try:
        tracks = await client.coverage_tracks(COVERAGE_ABBREV)
        recording.keep(COVERAGE_TRACKS_FILE, f"the {COVERAGE_ABBREV} rnaseq tracks")
        subtrack = coverage_subtrack(tracks, COVERAGE_STRAND)
        if subtrack is None:
            msg = f"{COVERAGE_ABBREV} lists no coverage subtrack"
            raise RuntimeError(msg)
        await BigWigReader(client, subtrack.data_path).depth(COVERAGE_SEQID, start, end)
    finally:
        await client.close()
    reads = recorder.exchanges[1:]
    index_at = _INDEX_OFFSET.unpack_from(reads[0].body, _INDEX_OFFSET_AT)[0]
    for index, exchange in enumerate(reads, 1):
        role = _read_role(index, exchange, index_at)
        recording.keep_exchange(
            COVERAGE_READ_FILE.format(index=index),
            f"{COVERAGE_GENE} {COVERAGE_SEQID}:{start}-{end} on {subtrack.name}, "
            f"read {index} of {len(reads)}, {role}, {exchange.byte_range}",
            exchange,
        )
    write_recording(into, recording.bodies, recording.entries)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    modes = {
        "record": record,
        "junctions": record_junctions,
        "coverage": record_coverage,
    }
    if len(args) != 1 or args[0] not in modes:
        print(_USAGE)
        return 2
    code = asyncio.run(modes[args[0]]())
    for name, entry in load_provenance(FIXTURE_DIR).items():
        size = (FIXTURE_DIR / name).stat().st_size
        print(f"{name}: {entry.status} {size}b {entry.url}")
    return code


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "FIXTURE_DIR",
    "PROVENANCE_FILE",
    "ExchangeRecorder",
    "JBrowseFixtureProvenance",
    "RecordedExchange",
    "coverage_subtrack",
    "load_provenance",
    "main",
    "record",
    "record_coverage",
    "record_junctions",
    "strand_of",
    "write_recording",
]
