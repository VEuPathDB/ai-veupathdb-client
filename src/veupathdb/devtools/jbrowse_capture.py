"""Records the JBrowse bodies the hermetic genome tests read.

Usage::

    python -m veupathdb.devtools.jbrowse_capture record

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
_USAGE = "usage: python -m veupathdb.devtools.jbrowse_capture record"


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


class ExchangeRecorder(httpx.AsyncBaseTransport):
    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self._inner = inner
        self.last_url = ""
        self.last_status = 0
        self.last_body = b""

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await self._inner.handle_async_request(request)
        self.last_url = str(request.url)
        self.last_status = response.status_code
        self.last_body = await response.aread()
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
    ordered = dict(sorted(entries.items()))
    (into / PROVENANCE_FILE).write_text(
        _PROVENANCE.dump_json(ordered, indent=2).decode() + "\n"
    )


async def record(into: Path = FIXTURE_DIR) -> int:
    use_qa_sites()
    await act_as_the_test_account()
    recorder = ExchangeRecorder(httpx.AsyncHTTPTransport())
    client = JBrowseClient(base_url=get_site(SITE).web_base_url, transport=recorder)
    recorded_at = datetime.datetime.now(tz=datetime.UTC).date().isoformat()
    bodies: dict[str, bytes] = {}
    entries: dict[str, JBrowseFixtureProvenance] = {}

    def keep(name: str, reads: str) -> None:
        bodies[name] = recorder.last_body
        entries[name] = JBrowseFixtureProvenance(
            site=SITE,
            url=recorder.last_url,
            status=recorder.last_status,
            recorded_at=recorded_at,
            reads=reads,
        )

    try:
        tracks = await client.track_list("organismSpecific", ABBREV)
        keep(TRACKS_FILE, f"the {ABBREV} organism track list")
        fasta = FASTA_PATH.format(prefix=data_prefix(tracks))
        index = await client.store_bytes(f"{fasta}.fai")
        keep(INDEX_FILE, f"the {ABBREV} genome index")
        entry = parse_fai(index.decode())[CRT_SEQID]
        first, last = entry.byte_of(CRT_EXON1[0]), entry.byte_of(CRT_EXON1[1])
        await client.store_bytes(fasta, (first, last))
        keep(
            WINDOW_FILE,
            f"{CRT_SEQID}:{CRT_EXON1[0]}-{CRT_EXON1[1]}, bytes={first}-{last}",
        )
    finally:
        await client.close()
    write_recording(into, bodies, entries)
    return 0


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if args != ["record"]:
        print(_USAGE)
        return 2
    code = asyncio.run(record())
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
    "load_provenance",
    "main",
    "record",
    "write_recording",
]
