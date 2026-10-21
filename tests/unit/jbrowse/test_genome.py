from collections.abc import Iterator

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.errors import ExternalServiceError, VEuPathDBError, VEuPathDBErrorCode
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.genome import (
    GenomeIndexError,
    GenomeReader,
    data_prefix,
    parse_fai,
)
from veupathdb.jbrowse.models import TrackList

FAI = "chr1\t25\t6\t10\t11\nchr2\t8\t41\t10\t12\n"
FASTA = b">chr1\nACGTACGTAC\nacgtacgtac\nNNNNN\n>chr2\r\nTTTTGGGG\r\n"
TRACKS = {
    "tracks": [
        {
            "urlTemplate": "/a/service/jbrowse/store?data=org1%2FgenomeAndProteome%2Fgff%2Fx.gff.gz"
        }
    ]
}


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


def test_the_index_maps_a_position_to_its_byte() -> None:
    entry = parse_fai(FAI)["chr1"]
    assert entry.byte_of(1) == 6
    assert entry.byte_of(10) == 15
    assert entry.byte_of(11) == 17


def test_the_index_skips_a_line_without_five_columns() -> None:
    assert sorted(parse_fai(FAI + "\nbroken\t1\n")) == ["chr1", "chr2"]


def test_the_data_prefix_is_the_first_directory_of_a_store_path() -> None:
    assert data_prefix(TrackList.model_validate(TRACKS)) == "org1"


def test_a_track_list_with_no_store_path_has_no_prefix() -> None:
    with pytest.raises(GenomeIndexError):
        data_prefix(TrackList.model_validate({"tracks": [{"urlTemplate": ""}]}))


def test_a_genome_index_error_is_a_not_found_refusal() -> None:
    error = GenomeIndexError("the genome index of org1 has no sequence chr9")
    assert isinstance(error, VEuPathDBError)
    assert error.code == VEuPathDBErrorCode.VALIDATION_ERROR
    assert error.status == 404
    assert error.title == "Genome sequence not found"
    assert error.detail == "the genome index of org1 has no sequence chr9"


def reader(fasta: bytes = FASTA) -> GenomeReader:
    def answer(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/organismSpecific/org1"):
            return httpx.Response(200, json=TRACKS)
        data = request.url.params["data"]
        if data.endswith(".fai"):
            return httpx.Response(200, content=FAI.encode())
        assert data == "org1/genomeAndProteome/fasta/genome.fasta"
        first, last = (
            int(v) for v in request.headers["Range"].removeprefix("bytes=").split("-")
        )
        return httpx.Response(206, content=fasta[first : last + 1])

    return GenomeReader(
        JBrowseClient(
            base_url="https://qa.example.org/x.qa",
            transport=httpx.MockTransport(answer),
        )
    )


async def test_a_window_is_uppercase_without_line_breaks() -> None:
    window = await reader().window("org1", "chr1", 9, 14)
    assert window.sequence == "ACACGT"
    assert (window.start, window.end) == (9, 14)


async def test_a_window_past_the_contig_ends_is_clamped() -> None:
    window = await reader().window("org1", "chr2", -5, 100)
    assert (window.start, window.end, window.sequence) == (1, 8, "TTTTGGGG")


async def test_a_window_reads_across_a_line_break() -> None:
    window = await reader().window("org1", "chr1", 20, 25)
    assert window.sequence == "CNNNNN"


async def test_a_window_outside_the_contig_is_refused() -> None:
    with pytest.raises(GenomeIndexError):
        await reader().window("org1", "chr2", 9, 20)


async def test_a_short_read_is_refused() -> None:
    with pytest.raises(ExternalServiceError, match="chr1:9-25 read 5 of 17 bases"):
        await reader(FASTA[:20]).window("org1", "chr1", 9, 25)


async def test_an_unknown_sequence_is_refused() -> None:
    with pytest.raises(GenomeIndexError):
        await reader().window("org1", "chr9", 1, 5)


async def test_the_sequence_length_is_read_from_the_index() -> None:
    assert await reader().sequence_length("org1", "chr1") == 25
