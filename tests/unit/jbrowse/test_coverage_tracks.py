from collections import Counter
from collections.abc import Iterator

import httpx
import pytest

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.jbrowse.models import SubTrack, TrackConfig
from veupathdb.testing import FIXTURE_ROOT

TRACKS = FIXTURE_ROOT / "jbrowse/agamPEST_coverage_tracks.json"
VB_WEB = "https://qa.vectorbase.org/vectorbase.qa"
STUDY = "agamPEST_Ruiz_RNAeq_Agambiae_MGs_SGs_infected_Pfalciparum_2021_ebi_rnaSeq_RSRC"


@pytest.fixture(autouse=True)
def registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    try:
        yield
    finally:
        veupathdb_auth_token_ctx.reset(token)


async def recorded_tracks() -> list[TrackConfig]:
    def answer(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/vectorbase.qa/service/jbrowse/rnaseq/agamPEST"
        return httpx.Response(200, content=TRACKS.read_bytes())

    client = JBrowseClient(base_url=VB_WEB, transport=httpx.MockTransport(answer))
    return await client.coverage_tracks("agamPEST")


async def test_the_recorded_rnaseq_list_is_all_bigwig_tracks() -> None:
    tracks = await recorded_tracks()
    assert Counter(track.store_class for track in tracks) == {
        "JBrowse/Store/SeqFeature/BigWig": 570,
        "MultiBigWig/Store/SeqFeature/MultiBigWig": 160,
    }


async def test_a_single_bigwig_track_is_its_one_subtrack() -> None:
    tracks = await recorded_tracks()
    singles = [t for t in tracks if t.store_class.endswith("/BigWig")]
    assert all(len(track.subtracks()) == 1 for track in singles)
    reverse = tracks[34]
    assert reverse.store_class == "JBrowse/Store/SeqFeature/BigWig"
    assert reverse.subtracks() == [
        SubTrack(url=reverse.url_template, name=reverse.key),
    ]
    assert reverse.key == (
        "Mosquito midguts (MGs) and salivary glands (SGs) infected with P. "
        "falciparum - 001.3 - midguts single-end (unique reverse) Coverage"
    )
    assert reverse.subtracks()[0].data_path == (
        f"AgambiaePEST/bulkrnaseq/bigwig/{STUDY}/1_midguts_single-end/"
        "unique_results.secondstrand_unlogged.bw"
    )


async def test_a_multi_bigwig_track_lists_its_url_templates_as_subtracks() -> None:
    tracks = await recorded_tracks()
    multis = [t for t in tracks if t.store_class.endswith("/MultiBigWig")]
    assert sum(len(track.subtracks()) for track in multis) == 1710
    first = multis[0]
    assert first.key == (
        "Developmental transcriptome of sexed Anopheles gambiae larvae and adult "
        "mosquitoes Density - Unique Only"
    )
    assert first.subtracks()[0] == SubTrack(
        url=(
            "/a/service/jbrowse/store?data=AgambiaePEST%2Fbulkrnaseq%2Fbigwig%2F"
            "agamPEST_ERP005646_ebi_rnaSeq_RSRC%2F1_E-MTAB-2527%3AL4_24h_M%2F"
            "unique_results_unlogged.bw"
        ),
        name="E-MTAB-2527:L4_24h_M (unique)",
    )


async def test_every_recorded_subtrack_reads_a_bigwig_file() -> None:
    tracks = await recorded_tracks()
    paths = [sub.data_path for track in tracks for sub in track.subtracks()]
    assert len(paths) == 570 + 1710
    assert all(path.startswith("AgambiaePEST/bulkrnaseq/bigwig/") for path in paths)
    assert all(path.endswith(".bw") for path in paths)


async def test_the_recorded_subtrack_names_carry_the_strand_words() -> None:
    tracks = await recorded_tracks()
    names = [sub.name.lower() for t in tracks for sub in t.subtracks()]
    assert sum("forward" in name for name in names) == sum(
        "reverse" in name for name in names
    )
    assert not any("antisense" in name or "(-)" in name for name in names)
