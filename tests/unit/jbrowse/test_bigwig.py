import struct
from collections.abc import Iterator

import httpx
import pytest
from tests.unit.jbrowse._bigwig_files import (
    Layout,
    Section,
    bedgraph,
    bigwig,
    fixedstep,
    typed,
    varstep,
)
from tests.unit.jbrowse._tabix_files import Store

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.jbrowse_capture import load_provenance
from veupathdb.errors import ValidationError
from veupathdb.jbrowse.bigwig import (
    BIGWIG_BYTE_ORDER,
    BIGWIG_MAX_BLOCK_BYTES,
    BIGWIG_MAX_BLOCKS,
    BIGWIG_MAX_CHROM_TREE_BYTES,
    BIGWIG_MAX_NODE_ITEMS,
    BIGWIG_MAX_REGION,
    BIGWIG_MAX_RTREE_DEPTH,
    BIGWIG_MAX_ZOOM_LEVELS,
    BigWigReader,
)
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.errors import SequenceNotIndexedError, TrackReadError
from veupathdb.testing import FIXTURE_ROOT

DATA = "org1/genomeBrowser/bigwig/sample1.bw"
HEADER_READ = 64 + 24 * 10
ROOT_READ = 48 + 4 + 256 * 32


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def served(body: bytes) -> tuple[BigWigReader, Store]:
    store = Store({DATA: body})
    return BigWigReader(store.client(), DATA), store


def offsets(body: bytes) -> tuple[int, int, int]:
    chrom_at, data_at, index_at = struct.unpack_from("<QQQ", body, 8)
    return chrom_at, data_at, index_at


def spaced(count: int) -> list[Section]:
    return [bedgraph(0, [(i * 100, i * 100 + 10, float(i + 1))]) for i in range(count)]


TWO_CHROMS = bigwig(
    ["chr1", "chr2"],
    [
        bedgraph(0, [(9, 12, 2.0), (12, 15, 5.5)]),
        bedgraph(1, [(0, 4, 1.0)]),
    ],
)


async def test_a_region_reads_one_value_per_base_with_zero_where_nothing_covers_it() -> (
    None
):
    reader, _ = served(TWO_CHROMS)
    assert await reader.depth("chr1", 8, 17) == [
        0.0,
        0.0,
        2.0,
        2.0,
        2.0,
        5.5,
        5.5,
        5.5,
        0.0,
        0.0,
    ]


async def test_the_first_call_reads_the_header_the_chrom_tree_the_root_and_a_block() -> (
    None
):
    reader, store = served(TWO_CHROMS)
    await reader.depth("chr1", 8, 17)
    chrom_at, data_at, index_at = offsets(TWO_CHROMS)
    block_at = data_at + 4
    block_size = struct.unpack_from("<Q", TWO_CHROMS, index_at + 48 + 4 + 24)[0]
    assert store.ranges() == [
        f"bytes=0-{HEADER_READ - 1}",
        f"bytes={chrom_at}-{data_at - 1}",
        f"bytes={index_at}-{index_at + ROOT_READ - 1}",
        f"bytes={block_at}-{block_at + block_size - 1}",
    ]
    assert reader.reads == 4


async def test_a_second_call_keeps_the_header_the_chrom_tree_and_the_root() -> None:
    reader, store = served(TWO_CHROMS)
    await reader.depth("chr1", 8, 17)
    assert await reader.depth("chr2", 1, 4) == [1.0, 1.0, 1.0, 1.0]
    assert reader.reads == 5
    assert len(store.ranges()) == 5


async def test_a_region_no_block_covers_reads_zeros_and_no_block() -> None:
    reader, _ = served(TWO_CHROMS)
    assert await reader.depth("chr1", 100, 104) == [0.0] * 5
    assert reader.reads == 3


async def test_a_three_level_index_is_read_one_node_per_level() -> None:
    body = bigwig(["chr1"], spaced(8), Layout(block_size=2))
    reader, _ = served(body)
    assert await reader.depth("chr1", 301, 312) == [4.0] * 10 + [0.0] * 2
    assert reader.reads == 2 + 3 + 1
    await reader.depth("chr1", 501, 505)
    assert reader.reads == 6 + 2 + 1


async def test_a_five_level_index_is_refused_at_the_fifth_level() -> None:
    body = bigwig(["chr1"], spaced(32), Layout(block_size=2))
    reader, store = served(body)
    with pytest.raises(TrackReadError, match="BIGWIG_MAX_RTREE_DEPTH"):
        await reader.depth("chr1", 301, 305)
    assert reader.reads == 2 + BIGWIG_MAX_RTREE_DEPTH
    assert len(store.ranges()) == reader.reads


async def test_a_four_level_index_is_read() -> None:
    body = bigwig(["chr1"], spaced(16), Layout(block_size=2))
    reader, _ = served(body)
    assert await reader.depth("chr1", 1201, 1202) == [13.0, 13.0]
    assert reader.reads == 2 + BIGWIG_MAX_RTREE_DEPTH + 1


async def test_a_region_one_base_over_the_bound_is_refused_unread() -> None:
    reader, store = served(TWO_CHROMS)
    with pytest.raises(TrackReadError, match="BIGWIG_MAX_REGION"):
        await reader.depth("chr1", 1, BIGWIG_MAX_REGION + 1)
    assert (reader.reads, store.requests) == (0, [])


async def test_a_region_at_the_bound_is_read() -> None:
    reader, _ = served(TWO_CHROMS)
    values = await reader.depth("chr1", 1, BIGWIG_MAX_REGION)
    assert len(values) == BIGWIG_MAX_REGION
    assert sum(values) == 3 * 2.0 + 3 * 5.5


async def test_a_region_over_three_blocks_is_refused_before_a_block_is_read() -> None:
    reader, store = served(bigwig(["chr1"], spaced(3)))
    with pytest.raises(TrackReadError, match=r"3 data blocks.*BIGWIG_MAX_BLOCKS"):
        await reader.depth("chr1", 1, 300)
    assert reader.reads == 3
    assert len(store.ranges()) == 3
    assert BIGWIG_MAX_BLOCKS == 2


async def test_a_level_with_three_nodes_over_the_region_is_refused_unread() -> None:
    reader, _ = served(bigwig(["chr1"], spaced(8), Layout(block_size=2)))
    with pytest.raises(TrackReadError, match="BIGWIG_MAX_BLOCKS") as raised:
        await reader.depth("chr1", 1, 600)
    assert "3 R-tree nodes at one level" in str(raised.value.detail)
    assert reader.reads == 4


async def test_a_big_endian_file_is_refused_after_its_header() -> None:
    swapped = int.from_bytes((0x888FFC26).to_bytes(4, "big"), "little")
    reader, _ = served(bigwig(["chr1"], spaced(1), Layout(magic=swapped)))
    with pytest.raises(TrackReadError, match="BIGWIG_BYTE_ORDER") as raised:
        await reader.depth("chr1", 1, 10)
    assert "big-endian" in str(raised.value.detail)
    assert BIGWIG_BYTE_ORDER == "<"
    assert reader.reads == 1


async def test_a_header_past_the_zoom_level_bound_is_refused() -> None:
    body = bigwig(["chr1"], spaced(1), Layout(zoom_levels=BIGWIG_MAX_ZOOM_LEVELS + 1))
    reader, _ = served(body)
    with pytest.raises(TrackReadError, match="BIGWIG_MAX_ZOOM_LEVELS"):
        await reader.depth("chr1", 1, 10)
    assert reader.reads == 1
    assert BIGWIG_MAX_ZOOM_LEVELS == 10


async def test_a_header_at_the_zoom_level_bound_is_read() -> None:
    body = bigwig(["chr1"], spaced(1), Layout(zoom_levels=BIGWIG_MAX_ZOOM_LEVELS))
    reader, _ = served(body)
    assert await reader.depth("chr1", 1, 2) == [1.0, 1.0]


async def test_an_index_past_the_node_item_bound_is_refused_after_its_root() -> None:
    body = bigwig(["chr1"], spaced(1), Layout(block_size=BIGWIG_MAX_NODE_ITEMS + 1))
    reader, _ = served(body)
    with pytest.raises(TrackReadError, match="BIGWIG_MAX_NODE_ITEMS"):
        await reader.depth("chr1", 1, 10)
    assert reader.reads == 3
    assert BIGWIG_MAX_NODE_ITEMS == 256


def with_block_size(body: bytes, size: int) -> bytes:
    index_at = offsets(body)[2]
    patched = bytearray(body)
    struct.pack_into("<Q", patched, index_at + 48 + 4 + 24, size)
    return bytes(patched)


async def test_a_block_past_the_block_byte_bound_is_refused_unread() -> None:
    body = with_block_size(bigwig(["chr1"], spaced(1)), BIGWIG_MAX_BLOCK_BYTES + 1)
    reader, store = served(body)
    with pytest.raises(TrackReadError, match="BIGWIG_MAX_BLOCK_BYTES"):
        await reader.depth("chr1", 1, 10)
    assert reader.reads == 3
    assert len(store.ranges()) == 3
    assert BIGWIG_MAX_BLOCK_BYTES == 262_144


async def test_a_file_with_another_magic_number_is_refused() -> None:
    reader, _ = served(bigwig(["chr1"], spaced(1), Layout(magic=0x12345678)))
    with pytest.raises(TrackReadError, match="magic"):
        await reader.depth("chr1", 1, 10)
    assert reader.reads == 1


async def test_an_unknown_section_type_is_refused() -> None:
    reader, _ = served(bigwig(["chr1"], [typed(spaced(1)[0], 7)]))
    with pytest.raises(TrackReadError, match="section type 7"):
        await reader.depth("chr1", 1, 10)


async def test_a_variable_step_section_is_read() -> None:
    reader, _ = served(bigwig(["chr1"], [varstep(0, 3, [(2, 1.5), (10, 4.0)])]))
    assert await reader.depth("chr1", 1, 14) == [0.0, 0.0] + [1.5] * 3 + [0.0] * 5 + [
        4.0
    ] * 3 + [0.0]


async def test_a_fixed_step_section_is_read() -> None:
    reader, _ = served(bigwig(["chr1"], [fixedstep(0, 4, 5, 2, [1.0, 2.0, 3.0])]))
    assert await reader.depth("chr1", 5, 18) == [
        1.0,
        1.0,
        0.0,
        0.0,
        0.0,
        2.0,
        2.0,
        0.0,
        0.0,
        0.0,
        3.0,
        3.0,
        0.0,
        0.0,
    ]


async def test_an_uncompressed_file_is_read() -> None:
    reader, _ = served(bigwig(["chr1"], spaced(2), Layout(compressed=False)))
    assert await reader.depth("chr1", 99, 102) == [0.0, 0.0, 2.0, 2.0]


async def test_zoom_headers_move_the_chrom_tree_and_the_file_still_reads() -> None:
    reader, _ = served(bigwig(["chr1"], spaced(2), Layout(zoom_levels=4)))
    assert await reader.depth("chr1", 1, 2) == [1.0, 1.0]


async def test_a_chrom_tree_with_a_branch_node_names_every_sequence() -> None:
    body = bigwig(
        ["chrA", "chrB", "chrC"],
        [bedgraph(2, [(0, 3, 9.0)])],
        Layout(chrom_block_size=2),
    )
    reader, _ = served(body)
    assert await reader.depth("chrC", 1, 4) == [9.0, 9.0, 9.0, 0.0]


async def test_a_chrom_tree_past_its_bound_is_refused_after_the_header() -> None:
    body = bytearray(bigwig(["chr1"], spaced(1)))
    chrom_at = offsets(bytes(body))[0]
    struct.pack_into("<Q", body, 16, chrom_at + BIGWIG_MAX_CHROM_TREE_BYTES + 1)
    reader, _ = served(bytes(body))
    with pytest.raises(TrackReadError, match="BIGWIG_MAX_CHROM_TREE_BYTES"):
        await reader.depth("chr1", 1, 10)
    assert reader.reads == 1


async def test_a_chrom_tree_whose_values_are_not_8_bytes_is_refused() -> None:
    body = bytearray(TWO_CHROMS)
    chrom_at = offsets(TWO_CHROMS)[0]
    struct.pack_into("<I", body, chrom_at + 12, 12)
    reader, _ = served(bytes(body))
    with pytest.raises(TrackReadError, match="valSize 12"):
        await reader.depth("chr1", 1, 10)
    assert reader.reads == 2


async def test_a_sequence_the_chrom_tree_does_not_name_is_refused() -> None:
    reader, _ = served(TWO_CHROMS)
    with pytest.raises(SequenceNotIndexedError) as raised:
        await reader.depth("chr9", 1, 10)
    assert (raised.value.data_path, raised.value.seqid) == (DATA, "chr9")
    assert reader.reads == 2


async def test_a_region_that_ends_before_it_starts_is_refused_unread() -> None:
    reader, store = served(TWO_CHROMS)
    with pytest.raises(ValidationError, match="ends before it starts"):
        await reader.depth("chr1", 10, 9)
    assert store.requests == []


async def test_a_file_cut_inside_its_header_is_refused() -> None:
    reader, _ = served(TWO_CHROMS[:40])
    with pytest.raises(TrackReadError, match="ends early"):
        await reader.depth("chr1", 1, 10)


RECORDED = FIXTURE_ROOT / "jbrowse"
RECORDED_READS = [
    f"agamPEST_AGAP003685_bigwig_read{index}.bin" for index in range(1, 7)
]


def recorded_ranges() -> dict[str, bytes]:
    provenance = load_provenance(RECORDED)
    return {
        "bytes=" + provenance[name].reads.rsplit("bytes=", 1)[1]: (
            RECORDED / name
        ).read_bytes()
        for name in RECORDED_READS
    }


def recorded_path() -> str:
    url = load_provenance(RECORDED)[RECORDED_READS[0]].url
    return httpx.URL(url).params["data"]


async def recorded_depth() -> tuple[list[float], BigWigReader, list[str]]:
    served_ranges = recorded_ranges()
    sent: list[str] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request.headers["Range"])
        assert request.url.params["data"] == recorded_path()
        if request.headers["Range"] not in served_ranges:
            return httpx.Response(416)
        return httpx.Response(206, content=served_ranges[request.headers["Range"]])

    client = JBrowseClient(
        base_url="https://qa.vectorbase.org/vectorbase.qa",
        transport=httpx.MockTransport(answer),
    )
    reader = BigWigReader(client, recorded_path())
    values = await reader.depth("AgamP4_2R", 41950997, 41954101)
    return values, reader, sent


async def test_the_agap003685_region_reads_one_value_per_base_as_recorded() -> None:
    values, _, _ = await recorded_depth()
    assert len(values) == 41954101 - 41950997 + 1
    assert sum(values) == 36103.9900393188
    assert max(values) == 72.16000366210938
    assert sum(1 for value in values if value > 0) == 2849


async def test_the_agap003685_reads_are_the_recorded_ranges_in_order() -> None:
    _, reader, sent = await recorded_depth()
    provenance = load_provenance(RECORDED)
    assert sent == [
        "bytes=" + provenance[name].reads.rsplit("bytes=", 1)[1]
        for name in RECORDED_READS
    ]
    assert sent == [
        "bytes=0-303",
        "bytes=344-4129",
        "bytes=35018457-35026700",
        "bytes=35123005-35131200",
        "bytes=15030068-15034605",
        "bytes=15034606-15038943",
    ]
    assert reader.reads == 6
    assert reader.reads <= 2 + BIGWIG_MAX_RTREE_DEPTH + BIGWIG_MAX_BLOCKS


def test_the_recorded_blocks_lie_far_inside_the_block_byte_bound() -> None:
    sizes = [len(body) for body in list(recorded_ranges().values())[4:]]
    assert sizes == [4538, 4338]
    assert max(sizes) * 50 < BIGWIG_MAX_BLOCK_BYTES
