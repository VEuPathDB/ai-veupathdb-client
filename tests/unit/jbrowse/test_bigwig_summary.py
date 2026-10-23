import struct
from collections.abc import Iterator

import pytest
from pydantic import ValidationError
from tests.unit.jbrowse._bigwig_files import Layout, bedgraph, bigwig
from tests.unit.jbrowse._tabix_files import Store

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.jbrowse import BigWigReader, BigWigSummary, TrackReadError

DATA = "org1/genomeBrowser/bigwig/sample1.bw"
HEADER_READ = "bytes=0-343"
SUMMARY = (12, 0.5, 9.0, 30.0, 110.0)
SECTIONS = [bedgraph(0, [(9, 12, 2.0), (12, 15, 5.5)]), bedgraph(1, [(0, 4, 1.0)])]


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def served(layout: Layout) -> tuple[BigWigReader, Store, bytes]:
    body = bigwig(["chr1", "chr2"], SECTIONS, layout)
    store = Store({DATA: body})
    return BigWigReader(store.client(), DATA), store, body


def summary_offset(body: bytes) -> int:
    offset: int = struct.unpack_from("<Q", body, 44)[0]
    return offset


EXPECTED = BigWigSummary(
    bases_covered=12, min_value=0.5, max_value=9.0, sum_data=30.0, sum_squares=110.0
)


async def test_a_summary_after_the_header_arrives_in_the_header_read() -> None:
    reader, store, body = served(Layout(summary=SUMMARY))
    assert summary_offset(body) == 64
    assert await reader.summary() == EXPECTED
    assert store.ranges() == [HEADER_READ]
    assert reader.reads == 1


async def test_a_summary_after_ten_zoom_headers_arrives_in_the_header_read() -> None:
    reader, store, body = served(Layout(summary=SUMMARY, zoom_levels=10))
    assert summary_offset(body) == 304
    assert await reader.summary() == EXPECTED
    assert store.ranges() == [HEADER_READ]
    assert reader.reads == 1


async def test_a_summary_past_the_header_read_takes_one_more_40_byte_read() -> None:
    reader, store, body = served(Layout(summary=SUMMARY, summary_at_end=True))
    at = summary_offset(body)
    assert at == len(body) - 40
    assert await reader.summary() == EXPECTED
    assert store.ranges() == [HEADER_READ, f"bytes={at}-{at + 39}"]
    assert reader.reads == 2


async def test_a_file_without_a_summary_reads_none_from_the_header_alone() -> None:
    reader, store, body = served(Layout())
    assert summary_offset(body) == 0
    assert await reader.summary() is None
    assert store.ranges() == [HEADER_READ]
    assert reader.reads == 1


async def test_a_summary_then_a_depth_read_the_header_once() -> None:
    reader, store, _ = served(Layout(summary=SUMMARY))
    assert await reader.summary() == EXPECTED
    assert await reader.depth("chr1", 10, 12) == [2.0, 2.0, 2.0]
    assert reader.reads == 4
    assert store.ranges().count(HEADER_READ) == 1


async def test_a_far_summary_then_a_depth_read_the_header_once() -> None:
    reader, store, _ = served(Layout(summary=SUMMARY, summary_at_end=True))
    assert await reader.summary() == EXPECTED
    assert await reader.depth("chr1", 10, 12) == [2.0, 2.0, 2.0]
    assert reader.reads == 5
    assert store.ranges().count(HEADER_READ) == 1


async def test_a_depth_then_a_summary_read_the_header_once() -> None:
    reader, _, _ = served(Layout(summary=SUMMARY))
    await reader.depth("chr1", 10, 12)
    assert await reader.summary() == EXPECTED
    assert reader.reads == 4


async def test_a_summary_cut_by_the_end_of_the_file_is_refused() -> None:
    body = bigwig(["chr1", "chr2"], SECTIONS, Layout(summary=SUMMARY))
    reader = BigWigReader(Store({DATA: body[:80]}).client(), DATA)
    with pytest.raises(TrackReadError, match="at byte 80 of 104"):
        await reader.summary()


def test_the_mean_depth_is_the_sum_over_the_bases_covered() -> None:
    assert EXPECTED.mean_depth == 2.5


def test_a_summary_that_covers_no_base_has_a_mean_depth_of_zero() -> None:
    empty = BigWigSummary(
        bases_covered=0, min_value=0.0, max_value=0.0, sum_data=0.0, sum_squares=0.0
    )
    assert empty.mean_depth == 0.0


def test_a_summary_is_frozen() -> None:
    with pytest.raises(ValidationError, match="frozen"):
        EXPECTED.__setattr__("sum_data", 1.0)


def with_summary_offset(body: bytes, at: int) -> bytes:
    patched = bytearray(body)
    struct.pack_into("<Q", patched, 44, at)
    return bytes(patched)


@pytest.mark.parametrize(("zoom_levels", "at"), [(0, 1), (0, 63), (10, 64), (10, 303)])
async def test_a_summary_inside_the_header_is_refused_after_the_header_read(
    zoom_levels: int, at: int
) -> None:
    layout = Layout(summary=SUMMARY, zoom_levels=zoom_levels)
    body = with_summary_offset(bigwig(["chr1", "chr2"], SECTIONS, layout), at)
    store = Store({DATA: body})
    reader = BigWigReader(store.client(), DATA)
    with pytest.raises(TrackReadError, match=f"totalSummaryOffset {at}"):
        await reader.summary()
    assert store.ranges() == [HEADER_READ]
    assert reader.reads == 1


async def test_a_depth_read_refuses_a_summary_inside_the_header_too() -> None:
    body = with_summary_offset(bigwig(["chr1", "chr2"], SECTIONS), 32)
    reader = BigWigReader(Store({DATA: body}).client(), DATA)
    with pytest.raises(TrackReadError, match="totalSummaryOffset 32"):
        await reader.depth("chr1", 10, 12)
    assert reader.reads == 1
