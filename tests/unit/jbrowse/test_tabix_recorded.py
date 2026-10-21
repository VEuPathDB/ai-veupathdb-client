from collections.abc import Iterator

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.jbrowse_capture import load_provenance
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.gff import parse_gff_line
from veupathdb.jbrowse.models import TrackList
from veupathdb.jbrowse.tabix import TabixReader, parse_index
from veupathdb.testing import FIXTURE_ROOT

TRACKS = FIXTURE_ROOT / "jbrowse/pcynM_junction_tracks.json"
INDEX = FIXTURE_ROOT / "jbrowse/pcynM_junctions.gff.gz.tbi"
BLOCKS_FILE = "pcynM_junctions_PcyM_07_1380000_1384000.gff.gz"
BLOCKS = FIXTURE_ROOT / "jbrowse" / BLOCKS_FILE
DATA = "PcynomolgiM/genomeBrowser/gff/unifiedIntronJunction.gff.gz"
SEQID = "PcyM_07"
REGION_JUNCTIONS = [
    (1380080, 1380506, 15),
    (1380182, 1380394, 46),
    (1380182, 1380506, 1280),
    (1380182, 1380513, 22),
    (1380182, 1381630, 62),
    (1380182, 1381648, 51),
    (1380275, 1380506, 10),
    (1380556, 1381630, 723),
    (1380556, 1381648, 652),
    (1381125, 1381630, 8),
    (1381125, 1381648, 8),
    (1381674, 1381745, 1),
    (1381746, 1381841, 1),
    (1381746, 1381886, 1436),
    (1381746, 1382280, 31),
    (1382038, 1382280, 6),
    (1382045, 1382255, 22),
    (1382045, 1382280, 1686),
    (1382045, 1382630, 5),
    (1382045, 1383063, 1),
    (1382070, 1382280, 21),
    (1382111, 1382280, 1),
    (1382466, 1382630, 1970),
    (1382466, 1382632, 1),
    (1382466, 1382640, 1),
    (1382520, 1382630, 1),
    (1382670, 1383063, 1),
    (1382791, 1382910, 8),
    (1382791, 1382926, 1),
    (1382791, 1383063, 1442),
    (1382791, 1383067, 48),
    (1382937, 1383063, 1),
    (1382969, 1383063, 1),
    (1383259, 1383413, 2),
    (1383316, 1383462, 6),
]


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def recorded_range() -> tuple[int, int]:
    reads = load_provenance(FIXTURE_ROOT / "jbrowse")[BLOCKS_FILE].reads
    first, last = reads.rsplit("bytes=", 1)[1].split("-")
    return int(first), int(last)


class RecordedStore:
    def __init__(self) -> None:
        self.ranges: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/service/jbrowse/rnaseqJunctions/pcynM"):
            return httpx.Response(200, content=TRACKS.read_bytes())
        if request.url.params["data"] == f"{DATA}.tbi":
            return httpx.Response(200, content=INDEX.read_bytes())
        self.ranges.append(request.headers["Range"])
        first, last = request.headers["Range"].removeprefix("bytes=").split("-")
        recorded_first, recorded_last = recorded_range()
        if int(first) < recorded_first or int(last) > recorded_last:
            return httpx.Response(416)
        body = BLOCKS.read_bytes()
        return httpx.Response(
            206,
            content=body[int(first) - recorded_first : int(last) - recorded_first + 1],
        )


async def junctions(
    store: RecordedStore, start: int, end: int
) -> list[tuple[int, int, float | None]]:
    client = JBrowseClient(
        base_url="https://qa.plasmodb.org/plasmo.qa",
        transport=httpx.MockTransport(store),
    )
    (track,) = await client.junction_tracks("pcynM")
    lines = await TabixReader(client).lines(track, SEQID, start, end)
    features = [parse_gff_line(line) for line in lines]
    assert {feature.seqid for feature in features} <= {SEQID}
    return [(feature.start, feature.end, feature.score) for feature in features]


def test_the_recorded_junction_list_names_one_tabix_track() -> None:
    listed = TrackList.model_validate_json(TRACKS.read_bytes())
    assert [(t.label, t.index_path) for t in listed.tracks] == [
        ("RNA-Seq Evidence for Introns", f"{DATA}.tbi")
    ]


def test_the_recorded_index_is_a_gff_index_that_names_the_pcym_contig() -> None:
    index = parse_index(INDEX.read_bytes())
    assert SEQID in index.names
    assert len(index.names) == 55
    header = index.header
    assert (header.col_seq, header.col_beg, header.col_end, chr(header.meta)) == (
        1,
        4,
        5,
        "#",
    )
    assert not header.zero_based


async def test_the_pcym_0736700_region_reads_every_junction_that_overlaps_it() -> None:
    store = RecordedStore()
    found = await junctions(store, 1380000, 1384000)
    assert found == [(s, e, float(score)) for s, e, score in REGION_JUNCTIONS]
    assert store.ranges == ["bytes={}-{}".format(*recorded_range())]


async def test_the_region_holds_the_two_junctions_of_the_missing_exon() -> None:
    found = await junctions(RecordedStore(), 1380000, 1384000)
    assert (1381746, 1381886, 1436.0) in found
    assert (1382045, 1382280, 1686.0) in found
    assert all((s, e) != (1381746, 1382305) for s, e, _ in found)


async def test_a_junction_that_ends_on_the_region_start_is_included() -> None:
    found = await junctions(RecordedStore(), 1381886, 1381900)
    assert [(s, e) for s, e, _ in found] == [(1381746, 1381886), (1381746, 1382280)]


async def test_a_junction_that_starts_on_the_region_end_is_included() -> None:
    found = await junctions(RecordedStore(), 1381700, 1381746)
    assert [(s, e) for s, e, _ in found] == [
        (1381674, 1381745),
        (1381746, 1381841),
        (1381746, 1381886),
        (1381746, 1382280),
    ]


async def test_a_region_one_base_short_of_a_junction_leaves_it_out() -> None:
    found = await junctions(RecordedStore(), 1381700, 1381745)
    assert [(s, e) for s, e, _ in found] == [(1381674, 1381745)]
