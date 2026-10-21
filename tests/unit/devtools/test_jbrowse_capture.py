"""What ``jbrowse_capture record`` asks the QA site and what it writes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx
from tests.unit.jbrowse._tabix_files import bgzf, gff, tbi, virtual

from veupathdb.devtools import jbrowse_capture
from veupathdb.devtools.jbrowse_capture import (
    load_provenance,
    record,
    record_junctions,
)

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
