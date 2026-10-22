"""What ``jbrowse_capture record`` asks the QA site and what it writes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from tests.unit.jbrowse._bigwig_files import bedgraph, bigwig
from tests.unit.jbrowse._tabix_files import bgzf, gff, tbi, virtual

from veupathdb.devtools import jbrowse_capture
from veupathdb.devtools.jbrowse_capture import (
    ExchangeRecorder,
    coverage_subtrack,
    load_provenance,
    record,
    record_coverage,
    record_junctions,
    strand_of,
)
from veupathdb.jbrowse.errors import JBrowseError
from veupathdb.jbrowse.models import SubTrack, TrackConfig

QA_JBROWSE = "https://qa.plasmodb.org/plasmo.qa/service/jbrowse"
FASTA = "pfal3D7/genomeAndProteome/fasta/genome.fasta"
TRACKS = (
    b'{"tracks": [{"label": "genes", "urlTemplate": '
    b'"/a/service/jbrowse/store?data=pfal3D7%2FgenomeAndProteome%2Fgff%2Fx.gff.gz"}]}'
)
FAI = b"Pf3D7_07_v3\t403320\t13\t60\t61\n"
EXON = b"ATGAAATTC"
JUNCTIONS = "PcynomolgiM/genomeBrowser/gff/unifiedIntronJunction.gff.gz"
JUNCTION_TRACKS = (
    b'{"tracks": [{"label": "RNA-Seq Evidence for Introns", '
    b'"storeClass": "JBrowse/Store/SeqFeature/GFF3Tabix", "urlTemplate": '
    b'"/a/service/jbrowse/store?data=PcynomolgiM%2FgenomeBrowser%2Fgff%2F'
    b'unifiedIntronJunction.gff.gz"}]}'
)
LINES = gff("PcyM_07", 1381746, 1381886, "a") + gff("PcyM_07", 1382045, 1382280, "b")
JUNCTION_DATA, _ = bgzf(LINES)
JUNCTION_INDEX = tbi(
    {
        "PcyM_07": (
            {4765: [(virtual(0, 0), virtual(0, len(LINES)))]},
            [0] * 85,
        )
    }
)


@pytest.fixture(autouse=True)
def the_test_account(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("WDK_TEST_EMAIL", raising=False)
    monkeypatch.delenv("WDK_TEST_PASSWORD", raising=False)
    monkeypatch.setenv("WDK_TEST_TOKEN", "recording.account.token")


def qa_site() -> respx.MockRouter:
    router = respx.mock(assert_all_called=True)
    router.get(f"{QA_JBROWSE}/organismSpecific/pfal3D7").mock(
        return_value=httpx.Response(200, content=TRACKS)
    )
    router.get(f"{QA_JBROWSE}/store", params={"data": f"{FASTA}.fai"}).mock(
        return_value=httpx.Response(200, content=FAI)
    )
    router.get(
        f"{QA_JBROWSE}/store",
        params={"data": FASTA},
        headers={"Range": "bytes=409954-410045"},
    ).mock(return_value=httpx.Response(206, content=EXON))
    return router


async def test_a_recording_writes_each_body_as_the_site_sent_it(
    tmp_path: Path,
) -> None:
    with qa_site() as router:
        assert await record(tmp_path) == 0
        cookies = {call.request.headers["Cookie"] for call in router.calls}

    assert cookies == {"Authorization=recording.account.token"}
    assert (tmp_path / "pfal3D7_organism_tracks.json").read_bytes() == TRACKS
    assert (tmp_path / "pfal3D7_genome.fasta.fai").read_bytes() == FAI
    assert (tmp_path / "pfal3D7_crt_exon1.fasta").read_bytes() == EXON


async def test_a_recording_keeps_where_each_body_came_from(tmp_path: Path) -> None:
    with qa_site():
        await record(tmp_path)

    provenance = load_provenance(tmp_path)
    assert {name: entry.status for name, entry in provenance.items()} == {
        "pfal3D7_crt_exon1.fasta": 206,
        "pfal3D7_genome.fasta.fai": 200,
        "pfal3D7_organism_tracks.json": 200,
    }
    assert {entry.site for entry in provenance.values()} == {"plasmodb"}
    assert provenance["pfal3D7_organism_tracks.json"].url == (
        f"{QA_JBROWSE}/organismSpecific/pfal3D7"
    )
    assert provenance["pfal3D7_crt_exon1.fasta"].reads == (
        "Pf3D7_07_v3:403222-403312, bytes=409954-410045"
    )


def junction_site() -> respx.MockRouter:
    router = respx.mock(assert_all_called=True)
    router.get(f"{QA_JBROWSE}/rnaseqJunctions/pcynM").mock(
        return_value=httpx.Response(200, content=JUNCTION_TRACKS)
    )
    router.get(f"{QA_JBROWSE}/store", params={"data": f"{JUNCTIONS}.tbi"}).mock(
        return_value=httpx.Response(200, content=JUNCTION_INDEX)
    )
    router.get(
        f"{QA_JBROWSE}/store",
        params={"data": JUNCTIONS},
        headers={"Range": "bytes=0-65535"},
    ).mock(return_value=httpx.Response(206, content=JUNCTION_DATA))
    return router


async def test_a_junction_recording_writes_the_list_the_index_and_the_blocks(
    tmp_path: Path,
) -> None:
    with junction_site():
        assert await record_junctions(tmp_path) == 0

    assert (tmp_path / "pcynM_junction_tracks.json").read_bytes() == JUNCTION_TRACKS
    assert (tmp_path / "pcynM_junctions.gff.gz.tbi").read_bytes() == JUNCTION_INDEX
    assert (
        tmp_path / "pcynM_junctions_PcyM_07_1380000_1384000.gff.gz"
    ).read_bytes() == JUNCTION_DATA
    blocks = load_provenance(tmp_path)["pcynM_junctions_PcyM_07_1380000_1384000.gff.gz"]
    assert (blocks.status, blocks.reads) == (
        206,
        "PcyM_07:1380000-1384000, bytes=0-65535",
    )


async def test_a_junction_recording_keeps_the_genome_recording(
    tmp_path: Path,
) -> None:
    with qa_site():
        await record(tmp_path)
    with junction_site():
        await record_junctions(tmp_path)

    assert sorted(load_provenance(tmp_path)) == [
        "pcynM_junction_tracks.json",
        "pcynM_junctions.gff.gz.tbi",
        "pcynM_junctions_PcyM_07_1380000_1384000.gff.gz",
        "pfal3D7_crt_exon1.fasta",
        "pfal3D7_genome.fasta.fai",
        "pfal3D7_organism_tracks.json",
    ]


def test_the_command_names_its_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert jbrowse_capture.main(["verify"]) == 2
    usage = capsys.readouterr().out
    assert "jbrowse_capture record" in usage
    assert "jbrowse_capture junctions" in usage
    assert "jbrowse_capture coverage" in usage


VB_JBROWSE = "https://qa.vectorbase.org/vectorbase.qa/service/jbrowse"
REVERSE = "AgambiaePEST/bigwig/s1/reverse.bw"
COVERAGE_TRACKS = (
    b'{"tracks": [{"key": "Example study", '
    b'"storeClass": "MultiBigWig/Store/SeqFeature/MultiBigWig", "urlTemplates": ['
    b'{"url": "/a/service/jbrowse/store?data=AgambiaePEST%2Fbigwig%2Fs1%2Fforward.bw",'
    b' "name": "s1 forward"},'
    b'{"url": "/a/service/jbrowse/store?data=AgambiaePEST%2Fbigwig%2Fs1%2Freverse.bw",'
    b' "name": "s1 reverse"}]}]}'
)
COVERAGE_FILE = bigwig(["AgamP4_2R"], [bedgraph(0, [(41951000, 41951010, 3.0)])])


def coverage_site() -> respx.MockRouter:
    def ranged(request: httpx.Request) -> httpx.Response:
        first, last = request.headers["Range"].removeprefix("bytes=").split("-")
        return httpx.Response(206, content=COVERAGE_FILE[int(first) : int(last) + 1])

    router = respx.mock(assert_all_called=True)
    router.get(f"{VB_JBROWSE}/rnaseq/agamPEST").mock(
        return_value=httpx.Response(200, content=COVERAGE_TRACKS)
    )
    router.get(f"{VB_JBROWSE}/store", params={"data": REVERSE}).mock(side_effect=ranged)
    return router


async def test_a_coverage_recording_keeps_the_list_and_each_read_in_order(
    tmp_path: Path,
) -> None:
    with coverage_site() as router:
        assert await record_coverage(tmp_path) == 0
        ranges = [call.request.headers["Range"] for call in router.calls[1:]]

    provenance = load_provenance(tmp_path)
    assert (tmp_path / "agamPEST_coverage_tracks.json").read_bytes() == COVERAGE_TRACKS
    names = [f"agamPEST_AGAP003685_bigwig_read{index}.bin" for index in (1, 2, 3, 4)]
    assert sorted(provenance) == sorted([*names, "agamPEST_coverage_tracks.json"])
    roles = [
        "the header, zoom headers and total summary",
        "the chromosome tree",
        "the R-tree header and root",
        "a data block",
    ]
    assert [provenance[name].reads for name in names] == [
        f"AGAP003685 AgamP4_2R:41950997-41954101 on s1 reverse, read {index} of 4, "
        f"{role}, {byte_range}"
        for index, (role, byte_range) in enumerate(zip(roles, ranges, strict=True), 1)
    ]
    assert {provenance[name].site for name in names} == {"vectorbase"}
    assert [provenance[name].status for name in names] == [206] * 4


def sub(name: str) -> SubTrack:
    return SubTrack(url=f"/a/service/jbrowse/store?data={name}.bw", name=name)


def test_a_subtrack_reads_its_strand_from_its_name() -> None:
    assert [
        strand_of(sub(name))
        for name in ("s1 forward", "s1 Plus", "s1 (+)", "s1 reverse", "s1 minus")
    ] == ["+", "+", "+", "-", "-"]
    assert strand_of(sub("s1 unique")) is None
    assert strand_of(sub("s1 antisense")) == "unread"
    assert strand_of(sub("s1 sense")) == "unread"


def test_the_strand_subtrack_comes_before_a_unified_track() -> None:
    unified = TrackConfig(key="Unified coverage", url_template="/s?data=u.bw")
    stranded = TrackConfig(
        key="Study", url_templates=[sub("x forward"), sub("x minus")]
    )
    assert coverage_subtrack([unified, stranded], "-") == sub("x minus")
    assert coverage_subtrack([unified, stranded], "+") == sub("x forward")


def test_without_a_strand_subtrack_the_unified_track_is_read() -> None:
    plain = TrackConfig(key="Study", url_templates=[sub("y unique"), sub("y sense")])
    unified = TrackConfig(label="unified_rnaseq", url_templates=[sub("u all")])
    assert coverage_subtrack([plain, unified], "+") == sub("u all")


def test_without_a_unified_track_the_first_unstranded_subtrack_is_read() -> None:
    plain = TrackConfig(key="Study", url_templates=[sub("z antisense"), sub("z all")])
    assert coverage_subtrack([plain], "-") == sub("z all")
    assert coverage_subtrack([], "-") is None


async def test_a_recorder_refuses_a_request_past_its_budget_unsent() -> None:
    sent: list[httpx.Request] = []

    def answer(request: httpx.Request) -> httpx.Response:
        sent.append(request)
        return httpx.Response(200)

    recorder = ExchangeRecorder(httpx.MockTransport(answer), budget=1)
    async with httpx.AsyncClient(transport=recorder) as client:
        await client.get("https://qa.vectorbase.org/a")
        with pytest.raises(RuntimeError, match="budget of 1 requests"):
            await client.get("https://qa.vectorbase.org/b")
    assert [str(r.url) for r in sent] == ["https://qa.vectorbase.org/a"]
    assert len(recorder.exchanges) == 1


def written(directory: Path) -> list[str]:
    return sorted(path.name for path in directory.iterdir())


async def test_a_coverage_recording_stops_at_its_budget_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(jbrowse_capture, "COVERAGE_BUDGET", 3)
    with coverage_site() as router:
        with pytest.raises(RuntimeError, match="budget of 3 requests"):
            await record_coverage(tmp_path)
        sent = len(router.calls)
    assert sent == 3
    assert written(tmp_path) == []


def test_the_coverage_budget_is_the_track_list_and_the_bounded_reads() -> None:
    assert jbrowse_capture.COVERAGE_BUDGET == 1 + 2 + 4 + 2


async def test_a_coverage_recording_stops_at_a_refused_read_and_writes_nothing(
    tmp_path: Path,
) -> None:
    router = respx.mock(assert_all_called=True)
    router.get(f"{VB_JBROWSE}/rnaseq/agamPEST").mock(
        return_value=httpx.Response(200, content=COVERAGE_TRACKS)
    )
    router.get(f"{VB_JBROWSE}/store", params={"data": REVERSE}).mock(
        return_value=httpx.Response(500)
    )
    with router:
        with pytest.raises(JBrowseError) as raised:
            await record_coverage(tmp_path)
        sent = len(router.calls)
    assert raised.value.upstream_status == 500
    assert sent == 2
    assert written(tmp_path) == []
