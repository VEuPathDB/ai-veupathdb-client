import random
import threading
from collections.abc import Iterator

import pytest
from tests.unit.jbrowse._tabix_files import Store, bgzf, gff, tbi, virtual

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.jbrowse import tabix
from veupathdb.jbrowse.errors import SequenceNotIndexedError, TrackReadError
from veupathdb.jbrowse.models import TrackConfig
from veupathdb.jbrowse.tabix import BgzfText, TabixReader

DATA = "org1/genomeBrowser/gff/junctions.gff.gz"
TRACK = TrackConfig.model_validate(
    {
        "storeClass": "JBrowse/Store/SeqFeature/GFF3Tabix",
        "urlTemplate": "/a/service/jbrowse/store?data=org1%2FgenomeBrowser%2Fgff%2Fjunctions.gff.gz",
    }
)
NEAR = gff("chr1", 100, 200, "near")
FAR = gff("chr1", 300, 400, "far")
FILLER = random.Random(15).randbytes(60000)


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def far_apart() -> tuple[Store, list[int]]:
    data, starts = bgzf(NEAR, FILLER, FILLER, FAR)
    index = tbi(
        {
            "chr1": (
                {
                    4681: [(virtual(starts[0], 0), virtual(starts[0], len(NEAR)))],
                    0: [(virtual(starts[3], 0), virtual(starts[3], len(FAR)))],
                },
                [0],
            )
        }
    )
    return Store({DATA: data, f"{DATA}.tbi": index}), starts


def one_block() -> Store:
    data, starts = bgzf(NEAR + FAR)
    index = tbi(
        {
            "chr1": (
                {4681: [(virtual(starts[0], 0), virtual(starts[0], len(NEAR + FAR)))]},
                [0],
            )
        }
    )
    return Store({DATA: data, f"{DATA}.tbi": index})


def idents(lines: list[str]) -> list[str]:
    return [line.rsplit("ID=", 1)[1] for line in lines]


async def test_a_sequence_the_index_does_not_name_is_refused_unread() -> None:
    served = one_block()
    with pytest.raises(SequenceNotIndexedError) as raised:
        await TabixReader(served.client()).lines(TRACK, "chr1_v1", 1, 100)
    assert isinstance(raised.value, TrackReadError)
    assert (raised.value.data_path, raised.value.seqid) == (DATA, "chr1_v1")
    assert raised.value.detail == f"the index of {DATA} names no sequence chr1_v1"
    assert (raised.value.title, raised.value.status) == (
        "Sequence not in the track index",
        404,
    )
    assert served.ranges() == []


async def test_an_indexed_sequence_with_no_feature_in_the_window_reads_nothing() -> (
    None
):
    served = one_block()
    assert await TabixReader(served.client()).lines(TRACK, "chr1", 20000, 30000) == []
    assert served.ranges() == []


async def test_chunks_more_than_a_block_apart_are_read_apart() -> None:
    served, starts = far_apart()
    lines = await TabixReader(served.client()).lines(TRACK, "chr1", 1, 1000)
    assert idents(lines) == ["near", "far"]
    assert served.ranges() == [
        f"bytes=0-{65535}",
        f"bytes={starts[3]}-{starts[3] + 65535}",
    ]
    assert starts[3] > 65536


async def test_chunks_in_one_block_are_read_once() -> None:
    served = one_block()
    lines = await TabixReader(served.client()).lines(TRACK, "chr1", 1, 1000)
    assert idents(lines) == ["near", "far"]
    assert served.ranges() == ["bytes=0-65535"]


async def test_blocks_are_inflated_off_the_event_loop_thread(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    threads: list[int] = []
    inflate = tabix.inflate_blocks

    def watched(raw: bytes, base: int) -> BgzfText:
        threads.append(threading.get_ident())
        return inflate(raw, base)

    monkeypatch.setattr(tabix, "inflate_blocks", watched)
    await TabixReader(one_block().client()).lines(TRACK, "chr1", 1, 1000)
    assert threads
    assert threading.get_ident() not in threads


async def test_a_read_that_fails_drops_the_index_it_used() -> None:
    served = one_block()
    good = served.files[DATA]
    served.files[DATA] = good[:20] + bytes([good[20] ^ 0xFF]) + good[21:]
    reader = TabixReader(served.client())
    with pytest.raises(TrackReadError):
        await reader.lines(TRACK, "chr1", 1, 1000)
    served.files[DATA] = good
    assert idents(await reader.lines(TRACK, "chr1", 1, 1000)) == ["near", "far"]
    indexes = [r for r in served.requests if r.url.params["data"].endswith(".tbi")]
    assert len(indexes) == 2


async def test_a_sequence_not_indexed_keeps_the_index() -> None:
    served = one_block()
    reader = TabixReader(served.client())
    for _ in range(2):
        with pytest.raises(SequenceNotIndexedError):
            await reader.lines(TRACK, "chrX", 1, 100)
    indexes = [r for r in served.requests if r.url.params["data"].endswith(".tbi")]
    assert len(indexes) == 1


async def test_the_group_count_reads_the_index_and_no_track_data() -> None:
    served, _ = far_apart()
    reader = TabixReader(served.client())

    assert await reader.chunk_group_count(TRACK, "chr1", 1, 1000) == 2
    assert served.ranges() == []
    assert [r.url.params["data"] for r in served.requests] == [f"{DATA}.tbi"]


async def test_the_group_count_is_the_number_of_ranges_the_read_fetches() -> None:
    served, _ = far_apart()
    reader = TabixReader(served.client())

    counted = await reader.chunk_group_count(TRACK, "chr1", 1, 1000)
    await reader.lines(TRACK, "chr1", 1, 1000)

    assert len(served.ranges()) == counted


async def test_chunks_in_one_block_are_one_group() -> None:
    reader = TabixReader(one_block().client())

    assert await reader.chunk_group_count(TRACK, "chr1", 1, 1000) == 1


async def test_a_window_with_no_feature_has_no_group() -> None:
    reader = TabixReader(one_block().client())

    assert await reader.chunk_group_count(TRACK, "chr1", 20000, 30000) == 0


async def test_a_sequence_the_index_does_not_name_has_no_group_count() -> None:
    reader = TabixReader(one_block().client())

    with pytest.raises(SequenceNotIndexedError) as raised:
        await reader.chunk_group_count(TRACK, "chr1_v1", 1, 100)
    assert (raised.value.data_path, raised.value.seqid) == (DATA, "chr1_v1")
