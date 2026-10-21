from collections.abc import Iterator

import pytest
from tests.unit.jbrowse._tabix_files import (
    Store,
    bgzf,
    bgzf_block,
    gff,
    tbi,
    virtual,
)

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import ValidationError
from veupathdb.jbrowse.errors import JBrowseError, TrackReadError
from veupathdb.jbrowse.models import TrackConfig
from veupathdb.jbrowse.tabix import (
    Chunk,
    RefIndex,
    TabixReader,
    parse_index,
    region_bins,
    region_chunks,
)

DATA = "org1/genomeBrowser/gff/junctions.gff.gz"
TRACK = TrackConfig.model_validate(
    {
        "storeClass": "JBrowse/Store/SeqFeature/GFF3Tabix",
        "urlTemplate": "/a/service/jbrowse/store?data=org1%2FgenomeBrowser%2Fgff%2Fjunctions.gff.gz",
    }
)
FIRST = gff("chr1", 100, 200, "a") + gff("chr1", 150, 400, "b")
SECOND = gff("chr1", 300, 350, "c")
THIRD = gff("chr1", 401, 500, "d") + gff("chr1", 9000, 9100, "e")


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def split_across_blocks() -> tuple[bytes, list[int], bytes]:
    whole = FIRST + SECOND + THIRD
    cut = len(FIRST) + 10
    data, starts = bgzf(whole[:cut], whole[cut:])
    end = virtual(starts[1], len(whole) - cut)
    index = tbi({"chr1": ({4681: [(virtual(starts[0], 0), end)]}, [0])})
    return data, starts, index


def store() -> Store:
    data, _, index = split_across_blocks()
    return Store({DATA: data, f"{DATA}.tbi": index})


def idents(lines: list[str]) -> list[str]:
    return [line.rsplit("ID=", 1)[1] for line in lines]


def test_spec_5_3_reg2bins_a_16kb_region_at_offset_0_is_bin_4681_and_its_parents() -> (
    None
):
    assert region_bins(0, 16384) == [0, 1, 9, 73, 585, 4681]


def test_spec_5_3_reg2bins_a_region_across_a_16kb_boundary_takes_both_leaf_bins() -> (
    None
):
    assert region_bins(16383, 16385) == [0, 1, 9, 73, 585, 4681, 4682]


def test_spec_5_3_reg2bins_a_region_across_the_64mb_boundary_takes_two_bins_a_level() -> (
    None
):
    assert region_bins(2**26 - 1, 2**26 + 1) == [
        0,
        1,
        2,
        16,
        17,
        136,
        137,
        1096,
        1097,
        8776,
        8777,
    ]


def test_spec_5_3_reg2bins_the_pcym_0736700_region() -> None:
    assert region_bins(1379999, 1384000) == [0, 1, 9, 74, 595, 4765]


def test_tabix_spec_the_linear_index_drops_chunks_that_end_before_the_window() -> None:
    ref = RefIndex(
        bins={
            4681: (Chunk(begin=100, end=200),),
            4682: (Chunk(begin=500, end=900),),
            585: (Chunk(begin=850, end=1000), Chunk(begin=50, end=90)),
        },
        linear=(0, 400),
    )
    assert region_chunks(ref, 16384, 16400) == [Chunk(begin=500, end=1000)]


def test_tabix_spec_the_linear_index_window_is_the_region_start_window() -> None:
    ref = RefIndex(
        bins={585: (Chunk(begin=450, end=800), Chunk(begin=1000, end=1200))},
        linear=(0, 400, 900),
    )
    assert region_chunks(ref, 16384, 16400) == [
        Chunk(begin=450, end=800),
        Chunk(begin=1000, end=1200),
    ]


def test_overlapping_chunks_merge_and_disjoint_ones_stay_apart() -> None:
    ref = RefIndex(
        bins={
            4681: (Chunk(begin=100, end=200), Chunk(begin=300, end=400)),
            0: (Chunk(begin=150, end=250),),
        },
        linear=(0,),
    )
    assert region_chunks(ref, 0, 10) == [
        Chunk(begin=100, end=250),
        Chunk(begin=300, end=400),
    ]


def test_a_window_past_the_linear_index_uses_its_last_offset() -> None:
    ref = RefIndex(
        bins={0: (Chunk(begin=10, end=20), Chunk(begin=30, end=40))},
        linear=(0, 25),
    )
    assert region_chunks(ref, 2**20, 2**20 + 1) == [Chunk(begin=30, end=40)]


def test_a_chunk_that_ends_before_it_begins_is_refused() -> None:
    with pytest.raises(ValueError, match="ends before it begins"):
        Chunk(begin=20, end=10)


def test_the_index_names_its_sequences_and_their_bins() -> None:
    _, _, index = split_across_blocks()
    parsed = parse_index(index)
    assert parsed.names == ("chr1",)
    ref = parsed.ref("chr1")
    assert ref is not None
    assert list(ref.bins) == [4681]
    assert parsed.ref("chr9") is None


def test_an_index_without_the_magic_is_refused() -> None:
    with pytest.raises(TrackReadError, match="magic"):
        parse_index(bgzf_block(b"BAI\x01" + b"\x00" * 40))


def test_an_index_that_ends_early_is_refused() -> None:
    with pytest.raises(TrackReadError, match="ends early"):
        parse_index(bgzf_block(b"TBI\x01" + b"\x01\x00\x00\x00" + b"\x00" * 10))


def test_a_vcf_index_is_refused() -> None:
    index = tbi({"chr1": ({}, [])}, file_format=2)
    with pytest.raises(TrackReadError, match="generic"):
        parse_index(index)


def test_the_bin_37450_metadata_is_not_a_bin() -> None:
    index = tbi({"chr1": ({4681: [(0, 10)], 37450: [(0, 10), (5, 0)]}, [0])})
    ref = parse_index(index).ref("chr1")
    assert ref is not None
    assert list(ref.bins) == [4681]


async def test_a_line_split_across_two_blocks_is_read_once_and_whole() -> None:
    lines = await TabixReader(store().client()).lines(TRACK, "chr1", 140, 160)
    assert idents(lines) == ["a", "b"]


async def test_a_region_returns_only_the_lines_that_overlap_it() -> None:
    reader = TabixReader(store().client())
    assert idents(await reader.lines(TRACK, "chr1", 201, 299)) == ["b"]
    assert idents(await reader.lines(TRACK, "chr1", 1, 99)) == []
    assert idents(await reader.lines(TRACK, "chr1", 1, 20000)) == [
        "a",
        "b",
        "c",
        "d",
        "e",
    ]


async def test_a_feature_on_the_region_edge_is_included() -> None:
    reader = TabixReader(store().client())
    assert idents(await reader.lines(TRACK, "chr1", 400, 400)) == ["b"]
    assert idents(await reader.lines(TRACK, "chr1", 350, 350)) == ["b", "c"]
    assert idents(await reader.lines(TRACK, "chr1", 351, 400)) == ["b"]
    assert idents(await reader.lines(TRACK, "chr1", 500, 8999)) == ["d"]


async def test_a_region_on_a_16kb_window_edge_reads_the_bins_on_both_sides() -> None:
    first = gff("chr1", 16000, 16384, "f")
    second = gff("chr1", 16385, 16400, "g")
    data, starts = bgzf(first, second)
    index = tbi(
        {
            "chr1": (
                {
                    4681: [(virtual(starts[0], 0), virtual(starts[0], len(first)))],
                    4682: [(virtual(starts[1], 0), virtual(starts[1], len(second)))],
                },
                [virtual(starts[0], 0), virtual(starts[1], 0)],
            )
        }
    )
    served = Store({DATA: data, f"{DATA}.tbi": index})
    reader = TabixReader(served.client())
    assert idents(await reader.lines(TRACK, "chr1", 16050, 16385)) == ["f", "g"]
    assert idents(await reader.lines(TRACK, "chr1", 16385, 16385)) == ["g"]
    assert idents(await reader.lines(TRACK, "chr1", 16050, 16384)) == ["f"]
    assert idents(await reader.lines(TRACK, "chr1", 16384, 16384)) == ["f"]


async def test_tabix_spec_an_end_column_equal_to_the_start_column_is_one_base() -> None:
    text = b"chr1\t99\tx\nchr1\t100\ty\nchr1\t101\tz\n"
    data, starts = bgzf(text)
    index = tbi(
        {
            "chr1": (
                {4681: [(virtual(starts[0], 0), virtual(starts[0], len(text)))]},
                [0],
            )
        },
        file_format=0x10000,
        columns=(1, 2, 2),
    )
    served = Store({DATA: data, f"{DATA}.tbi": index})
    lines = await TabixReader(served.client()).lines(TRACK, "chr1", 101, 101)
    assert lines == ["chr1\t100\ty"]


async def test_tabix_spec_a_bed_index_reads_zero_based_half_open_columns() -> None:
    text = b"chr1\t99\t100\tx\nchr1\t100\t101\ty\n"
    data, starts = bgzf(text)
    index = tbi(
        {
            "chr1": (
                {4681: [(virtual(starts[0], 0), virtual(starts[0], len(text)))]},
                [0],
            )
        },
        file_format=0x10000,
        columns=(1, 2, 3),
    )
    served = Store({DATA: data, f"{DATA}.tbi": index})
    lines = await TabixReader(served.client()).lines(TRACK, "chr1", 100, 100)
    assert lines == ["chr1\t99\t100\tx"]


async def test_a_region_whose_chunks_span_over_16_mib_is_refused_unread() -> None:
    data, _, _ = split_across_blocks()
    far = virtual(17 * 1024 * 1024, 0)
    index = tbi({"chr1": ({4681: [(virtual(0, 0), far)]}, [0])})
    served = Store({DATA: data, f"{DATA}.tbi": index})
    with pytest.raises(TrackReadError, match="compressed bytes"):
        await TabixReader(served.client()).lines(TRACK, "chr1", 1, 100)
    assert served.ranges() == []


async def test_a_block_that_is_not_text_is_refused() -> None:
    text = b"chr1\t1\tx\t\xff\n"
    data, starts = bgzf(text)
    index = tbi(
        {
            "chr1": (
                {4681: [(virtual(starts[0], 0), virtual(starts[0], len(text)))]},
                [0],
            )
        },
        columns=(1, 2, 2),
    )
    served = Store({DATA: data, f"{DATA}.tbi": index})
    with pytest.raises(TrackReadError, match="not UTF-8"):
        await TabixReader(served.client()).lines(TRACK, "chr1", 1, 1)


async def test_the_index_is_read_once_for_two_regions() -> None:
    served = store()
    reader = TabixReader(served.client())
    await reader.lines(TRACK, "chr1", 1, 100)
    await reader.lines(TRACK, "chr1", 300, 300)
    indexes = [r for r in served.requests if r.url.params["data"].endswith(".tbi")]
    assert len(indexes) == 1


async def test_the_data_read_spans_the_chunk_blocks_and_one_block_more() -> None:
    served = store()
    _, starts, _ = split_across_blocks()
    await TabixReader(served.client()).lines(TRACK, "chr1", 1, 100)
    assert served.ranges() == [f"bytes=0-{starts[1] + 65535}"]


async def test_the_index_path_follows_the_tbi_url_template() -> None:
    data, _, index = split_across_blocks()
    served = Store({DATA: data, "elsewhere/junctions.tbi": index})
    track = TRACK.model_copy(
        update={
            "tbi_url_template": "/a/service/jbrowse/store?data=elsewhere%2Fjunctions.tbi"
        }
    )
    lines = await TabixReader(served.client()).lines(track, "chr1", 300, 300)
    assert idents(lines) == ["b", "c"]


async def test_a_bgzf_block_cut_short_is_refused() -> None:
    served = store()
    _, starts, _ = split_across_blocks()
    served.cut_at = starts[1] + 10
    with pytest.raises(TrackReadError, match="ends inside the block"):
        await TabixReader(served.client()).lines(TRACK, "chr1", 1, 20000)


async def test_a_block_whose_checksum_does_not_match_is_refused() -> None:
    served = store()
    _, starts, _ = split_across_blocks()
    corrupt = bytearray(served.files[DATA])
    corrupt[starts[1] - 8] ^= 0xFF
    served.files[DATA] = bytes(corrupt)
    with pytest.raises(TrackReadError, match="checksum"):
        await TabixReader(served.client()).lines(TRACK, "chr1", 1, 20000)


async def test_bytes_that_are_not_bgzf_are_refused() -> None:
    served = store()
    served.files[DATA] = b"chr1\tx\n" * 100
    with pytest.raises(TrackReadError, match="gzip magic"):
        await TabixReader(served.client()).lines(TRACK, "chr1", 1, 20000)


async def test_a_store_that_ignores_the_range_is_refused() -> None:
    served = store()
    served.whole_answer = True
    with pytest.raises(JBrowseError) as raised:
        await TabixReader(served.client()).lines(TRACK, "chr1", 1, 100)
    assert raised.value.upstream_status == 200


async def test_a_region_that_ends_before_it_starts_is_refused() -> None:
    with pytest.raises(ValidationError, match="ends before it starts") as raised:
        await TabixReader(store().client()).lines(TRACK, "chr1", 200, 100)
    assert raised.value.status == 422


async def test_a_region_before_the_first_base_is_refused() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 1") as raised:
        await TabixReader(store().client()).lines(TRACK, "chr1", 0, 100)
    assert raised.value.status == 422


def test_an_index_whose_names_are_not_text_is_refused() -> None:
    raw = (
        b"TBI\x01"
        + b"".join(n.to_bytes(4, "little") for n in (1, 0, 1, 4, 5, 35, 0, 2))
        + b"\xff\x00"
    )
    with pytest.raises(TrackReadError, match="sequence names"):
        parse_index(bgzf_block(raw) + bgzf_block(b""))


def test_tabix_spec_a_chunk_that_begins_before_the_linear_floor_starts_at_it() -> None:
    ref = RefIndex(bins={0: (Chunk(begin=100, end=900),)}, linear=(400,))
    assert region_chunks(ref, 10, 20) == [Chunk(begin=400, end=900)]
