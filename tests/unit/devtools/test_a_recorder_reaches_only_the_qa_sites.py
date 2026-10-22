import io
from collections.abc import Awaitable, Callable
from pathlib import Path

import httpx
import pytest
import respx

from veupathdb.devtools import eda_capture, jbrowse_capture, vdi_capture
from veupathdb.devtools.fixtures import record_all, record_one
from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.testing import QA_SITES_FILE, wdk_fixtures
from veupathdb.wdk import list_sites, load_sites_config
from veupathdb.wdk.vdi.models import VdiInstallDisposition
from veupathdb.wdk.vdi.rnaseqrc import RnaSeqCountFile, RnaSeqRcUpload

QA_SITE_IDS = sorted(load_sites_config(str(QA_SITES_FILE)).sites)
QA_PLASMODB = "https://qa.plasmodb.org/plasmo.qa/service"

type Recorder = Callable[..., Awaitable[int]]


@pytest.fixture(autouse=True)
def another_site_list(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for variable in ("WDK_TEST_TOKEN", "WDK_TEST_EMAIL", "WDK_TEST_PASSWORD"):
        monkeypatch.delenv(variable, raising=False)
    sites = tmp_path / "sites.yaml"
    sites.write_text(
        "sites:\n"
        "  plasmodb:\n"
        "    base_url: https://demodb.example/demo/service\n"
        "    project_id: PlasmoDB\n"
    )
    installed = VEuPathDBSettings(veupathdb_sites_config=str(sites))
    use_veupathdb_settings_source(lambda: installed)


@respx.mock
async def test_a_wdk_recording_asks_the_qa_site(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(wdk_fixtures, "FIXTURE_DIR", tmp_path)
    route = respx.get(f"{QA_PLASMODB}/record-types").mock(
        return_value=httpx.Response(200, json=[])
    )

    recorded = await record_one(wdk_fixtures.fixture_request("record_types"))

    assert route.called
    assert recorded.provenance.url == f"{QA_PLASMODB}/record-types"
    assert (tmp_path / "record_types.json").is_file()


@respx.mock
async def test_a_wdk_recording_travels_as_the_test_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WDK_TEST_TOKEN", "recording.account.token")
    monkeypatch.setattr(wdk_fixtures, "FIXTURE_DIR", tmp_path)
    route = respx.get(f"{QA_PLASMODB}/record-types").mock(
        return_value=httpx.Response(200, json=[])
    )

    assert await record_all(["record_types"]) == 1

    assert route.calls.last.request.headers["cookie"] == (
        "Authorization=recording.account.token"
    )


@respx.mock
async def test_a_wdk_recording_needs_the_test_account() -> None:
    with pytest.raises(RuntimeError, match="WDK_TEST_TOKEN"):
        await record_all(["record_types"])

    assert not respx.calls


@pytest.mark.parametrize(
    ("record", "captures"),
    [
        (eda_capture.record_distributions, eda_capture.DISTRIBUTION_CAPTURES[:1]),
        (eda_capture.record_posts, eda_capture.POST_CAPTURES[:1]),
    ],
)
@respx.mock
async def test_an_eda_recording_needs_the_test_account(
    record: Recorder, captures: list[object]
) -> None:
    with pytest.raises(RuntimeError, match="WDK_TEST_TOKEN"):
        await record(captures)

    assert not respx.calls


@pytest.mark.parametrize(
    "record",
    [
        eda_capture.record_analyses,
        eda_capture.record_distributions,
        eda_capture.record_posts,
    ],
)
async def test_an_eda_recording_reads_the_qa_list(record: Recorder) -> None:
    assert await record([]) == 0

    assert sorted(site.id for site in list_sites()) == QA_SITE_IDS


async def test_a_vdi_recording_reads_the_qa_list() -> None:
    upload = RnaSeqRcUpload(
        counts=(RnaSeqCountFile(name="counts.txt", content=io.BytesIO(b"g1\t1\n")),),
        sample_details="sample\n",
    )

    with pytest.raises(RuntimeError):
        await vdi_capture.record_install(
            "probe", site_id="plasmodb", upload=upload, genome=None
        )

    assert sorted(site.id for site in list_sites()) == QA_SITE_IDS


def test_a_vdi_recording_creates_the_store_it_writes_into(tmp_path: Path) -> None:
    store = tmp_path / "vdi"
    created = vdi_capture.CapturedStatus(
        label="post_response", elapsed_s=0.0, body={"datasetId": "d1"}
    )
    captured = vdi_capture.CapturedInstall(
        dataset_id="d1",
        post=created,
        statuses=[],
        outcome=VdiInstallDisposition.INSTALLED,
    )

    written = vdi_capture.write_install(
        "probe",
        captured,
        site="plasmodb",
        base_url="https://qa.plasmodb.org/vdi",
        recorded_at="2026-10-09",
        into=store,
    )

    assert written == [store / "probe_post_response.json"]
    assert vdi_capture.load_provenance(store)["probe_post_response"].url == (
        "https://qa.plasmodb.org/vdi/datasets"
    )


@respx.mock
async def test_a_jbrowse_recording_needs_the_test_account(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="WDK_TEST_TOKEN"):
        await jbrowse_capture.record(tmp_path)

    assert not respx.calls
    assert sorted(site.id for site in list_sites()) == QA_SITE_IDS


@respx.mock
async def test_a_junction_recording_needs_the_test_account(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="WDK_TEST_TOKEN"):
        await jbrowse_capture.record_junctions(tmp_path)

    assert not respx.calls
    assert sorted(site.id for site in list_sites()) == QA_SITE_IDS


@respx.mock
async def test_a_coverage_recording_needs_the_test_account(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="WDK_TEST_TOKEN"):
        await jbrowse_capture.record_coverage(tmp_path)

    assert not respx.calls
    assert sorted(site.id for site in list_sites()) == QA_SITE_IDS
