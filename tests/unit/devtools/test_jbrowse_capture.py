"""What ``jbrowse_capture record`` asks the QA site and what it writes."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
import respx

from veupathdb.devtools import jbrowse_capture
from veupathdb.devtools.jbrowse_capture import load_provenance, record

QA_JBROWSE = "https://qa.plasmodb.org/plasmo.qa/service/jbrowse"
FASTA = "pfal3D7/genomeAndProteome/fasta/genome.fasta"
TRACKS = (
    b'{"tracks": [{"label": "genes", "urlTemplate": '
    b'"/a/service/jbrowse/store?data=pfal3D7%2FgenomeAndProteome%2Fgff%2Fx.gff.gz"}]}'
)
FAI = b"Pf3D7_07_v3\t403320\t13\t60\t61\n"
EXON = b"ATGAAATTC"


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


def test_the_command_names_its_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert jbrowse_capture.main(["verify"]) == 2
    assert "jbrowse_capture record" in capsys.readouterr().out
