"""Records the JBrowse bodies the hermetic genome and junction tests read.

Usage::

    python -m veupathdb.devtools.jbrowse_capture record
    python -m veupathdb.devtools.jbrowse_capture junctions

Recording needs WDK_TEST_TOKEN, or WDK_TEST_EMAIL/WDK_TEST_PASSWORD.
"""

from __future__ import annotations

import asyncio
import datetime
import sys
from pathlib import Path

import httpx
from pydantic import BaseModel, ConfigDict, TypeAdapter

from veupathdb.devtools.qa_sites import use_qa_sites
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.genome import FASTA_PATH, data_prefix, parse_fai
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
_USAGE = (
    "usage: python -m veupathdb.devtools.jbrowse_capture record\n"
    "       python -m veupathdb.devtools.jbrowse_capture junctions"
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
    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.exchanges: list[RecordedExchange] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
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
        exchange = self._recorder.exchanges[-back]
        self.bodies[name] = exchange.body
        self.entries[name] = JBrowseFixtureProvenance(
            site=self._site,
            url=exchange.url,
            status=exchange.status,
            recorded_at=self._recorded_at,
            reads=reads,
        )


async def _recording_client() -> tuple[JBrowseClient, ExchangeRecorder]:
    use_qa_sites()
    await act_as_the_test_account()
    recorder = ExchangeRecorder(httpx.AsyncHTTPTransport())
    client = JBrowseClient(base_url=get_site(SITE).web_base_url, transport=recorder)
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


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    modes = {"record": record, "junctions": record_junctions}
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
    "load_provenance",
    "main",
    "record",
    "record_junctions",
    "write_recording",
]
