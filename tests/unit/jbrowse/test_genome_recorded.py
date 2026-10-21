from collections.abc import Iterator

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.jbrowse_capture import load_provenance
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.genome import GenomeReader, parse_fai
from veupathdb.testing import FIXTURE_ROOT

TRACKS = "jbrowse/pfal3D7_organism_tracks.json"
INDEX = "jbrowse/pfal3D7_genome.fasta.fai"
EXON = "jbrowse/pfal3D7_crt_exon1.fasta"
CRT_SEQID = "Pf3D7_07_v3"
GENOME = "Pfalciparum3D7/genomeAndProteome/fasta/genome.fasta"


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def recorded_reader() -> GenomeReader:
    index = (FIXTURE_ROOT / INDEX).read_bytes()
    entry = parse_fai(index.decode())[CRT_SEQID]
    exon_range = f"bytes={entry.byte_of(403222)}-{entry.byte_of(403312)}"

    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/service/jbrowse/organismSpecific/pfal3D7"):
            return httpx.Response(200, content=(FIXTURE_ROOT / TRACKS).read_bytes())
        if request.url.params["data"] == f"{GENOME}.fai":
            return httpx.Response(200, content=index)
        if (
            request.url.params["data"] == GENOME
            and request.headers["Range"] == exon_range
        ):
            return httpx.Response(206, content=(FIXTURE_ROOT / EXON).read_bytes())
        return httpx.Response(416)

    return GenomeReader(
        JBrowseClient(
            base_url="https://qa.plasmodb.org/plasmo.qa",
            transport=httpx.MockTransport(answer),
        )
    )


async def test_the_recorded_crt_exon_opens_the_crt_coding_sequence() -> None:
    window = await recorded_reader().window("pfal3D7", CRT_SEQID, 403222, 403312)
    assert (window.start, window.end) == (403222, 403312)
    assert len(window.sequence) == 91
    assert window.sequence.startswith("ATGAAATTCGCAAGTAAAAAAAATAATCAAAAAAATTC")


async def test_the_recorded_index_holds_chromosome_seven() -> None:
    assert await recorded_reader().sequence_length("pfal3D7", CRT_SEQID) == 1445207


def test_the_window_range_is_the_range_the_store_answered() -> None:
    entry = parse_fai((FIXTURE_ROOT / INDEX).read_text())[CRT_SEQID]
    window = load_provenance(FIXTURE_ROOT / "jbrowse")["pfal3D7_crt_exon1.fasta"]
    assert window.status == 206
    assert window.reads.endswith(
        f"bytes={entry.byte_of(403222)}-{entry.byte_of(403312)}"
    )
    assert len((FIXTURE_ROOT / EXON).read_bytes()) == 92
