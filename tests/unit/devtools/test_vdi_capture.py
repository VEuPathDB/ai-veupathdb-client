"""What ``vdi_capture record`` sends, what it writes, and what it removes afterwards."""

from __future__ import annotations

import copy
import gzip
import io
import json
from collections.abc import Iterator
from pathlib import Path

import httpx
import pytest
from tests.unit.wdk.vdi._wire import BASE_URL, recorded

from veupathdb.auth_context import veupathdb_auth_token_ctx
from veupathdb.devtools.vdi_capture import (
    CapturedInstall,
    ResponseRecorder,
    capture_install,
    load_provenance,
    status_label,
    write_install,
)
from veupathdb.json_types import JSONObject
from veupathdb.testing import FIXTURE_ROOT
from veupathdb.wdk.vdi.client import VdiClient
from veupathdb.wdk.vdi.models import (
    RNASEQRC,
    VdiDatasetDetails,
    VdiDatasetPostMeta,
    VdiInstallDisposition,
)
from veupathdb.wdk.vdi.rnaseqrc import RnaSeqCountFile, RnaSeqRcUpload

_INSTALL = (
    "rnaseqrc_import_in_progress",
    "rnaseqrc_import_in_progress",
    "rnaseqrc_import_complete_data_absent",
    "rnaseqrc_data_running",
    "rnaseqrc_installed",
)
_ACCOUNT = 424242


@pytest.fixture(autouse=True)
def _registered_token() -> Iterator[None]:
    token = veupathdb_auth_token_ctx.set("token-hermetic")
    yield
    veupathdb_auth_token_ctx.reset(token)


def _body(name: str) -> JSONObject:
    raw = copy.deepcopy(recorded(name))
    assert isinstance(raw, dict)
    return raw


class _Service:
    """Serves one recorded install in order, then answers as a deleted dataset."""

    def __init__(self, bodies: list[JSONObject]) -> None:
        self._bodies = bodies
        self._deleted = False
        self.requests: list[tuple[str, str]] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append((request.method, request.url.path))
        path = request.url.path
        if path == "/vdi/plugins":
            return httpx.Response(200, json=recorded("plugins"))
        if request.method == "POST":
            return httpx.Response(202, json=recorded("rnaseqrc_post_response"))
        if request.method == "DELETE":
            self._deleted = True
            return httpx.Response(204)
        if path == "/vdi/datasets":
            return httpx.Response(200, json=[])
        if self._deleted:
            return httpx.Response(404, json={"status": "not-found"})
        return httpx.Response(200, json=self._bodies.pop(0))


def _client(service: _Service) -> tuple[VdiClient, ResponseRecorder]:
    recorder = ResponseRecorder(httpx.MockTransport(service.handle))
    return VdiClient(base_url=BASE_URL, transport=recorder), recorder


def _details() -> VdiDatasetPostMeta:
    return VdiDatasetPostMeta(
        type=RNASEQRC,
        install_targets=["PlasmoDB"],
        name="veupathdb-py fixture",
        summary="Deleted after the capture.",
    )


def _upload() -> RnaSeqRcUpload:
    return RnaSeqRcUpload(
        counts=(RnaSeqCountFile(name="c.tsv", content=io.BytesIO(b"g\tS1\n")),),
        sample_details="sample\tgroup\nS1\ta\n",
    )


async def _capture(service: _Service) -> tuple[CapturedInstall, list[float]]:
    client, recorder = _client(service)
    waits: list[float] = []

    async def sleep(seconds: float) -> None:
        waits.append(seconds)

    captured = await capture_install(
        client,
        recorder,
        details=_details(),
        upload=_upload(),
        project_id="PlasmoDB",
        sleep=sleep,
    )
    await client.close()
    return captured, waits


async def test_each_distinct_status_is_kept_once_and_the_dataset_is_deleted() -> None:
    service = _Service([_body(name) for name in _INSTALL])

    captured, waits = await _capture(service)

    assert captured.outcome is VdiInstallDisposition.INSTALLED
    assert [status.label for status in captured.statuses] == [
        "import_in_progress",
        "import_complete_data_absent",
        "data_running",
        "installed",
    ]
    assert captured.statuses[-1].body == recorded("rnaseqrc_installed")
    assert waits == [2.0, 2.0, 2.0, 2.0, 2.0]
    one = f"/vdi/datasets/{captured.dataset_id}"
    assert service.requests == [
        ("GET", "/vdi/plugins"),
        ("POST", "/vdi/datasets"),
        *[("GET", one)] * 5,
        ("DELETE", one),
        ("GET", one),
        ("GET", "/vdi/datasets"),
    ]


async def test_a_capture_that_fails_mid_poll_still_deletes() -> None:
    service = _Service([_body("rnaseqrc_import_in_progress")])
    client, recorder = _client(service)

    async def sleep(_: float) -> None:
        return None

    with pytest.raises(IndexError):
        await capture_install(
            client,
            recorder,
            details=_details(),
            upload=_upload(),
            project_id="PlasmoDB",
            sleep=sleep,
        )
    await client.close()

    one = "/vdi/datasets/x4Z5JRpM9F0M8"
    assert service.requests == [
        ("GET", "/vdi/plugins"),
        ("POST", "/vdi/datasets"),
        ("GET", one),
        ("GET", one),
        ("DELETE", one),
    ]


async def test_the_written_body_names_no_account(tmp_path: Path) -> None:
    failed = _body("rnaseqrc_import_failed")
    failed["owner"] = {"userId": _ACCOUNT, "firstName": "Ada", "email": "a@b.org"}
    failed_text = json.dumps(failed).replace("1000000001/", f"{_ACCOUNT}/")
    service = _Service([json.loads(failed_text)])
    captured, _ = await _capture(service)

    written = write_install(
        "probe",
        captured,
        site="plasmodb",
        base_url=BASE_URL,
        recorded_at="2026-01-01",
        into=tmp_path,
    )

    assert [path.name for path in written] == [
        "probe_post_response.json",
        "probe_import_failed.json",
    ]
    text = (tmp_path / "probe_import_failed.json").read_text()
    assert str(_ACCOUNT) not in text
    assert "a@b.org" not in text
    assert json.loads(text) == recorded("rnaseqrc_import_failed")
    provenance = load_provenance(tmp_path)
    assert provenance["probe_import_failed"].url == (
        f"{BASE_URL}/datasets/{captured.dataset_id}"
    )
    assert provenance["probe_post_response"].status == 202


def test_every_label_names_the_axis_that_moved_last() -> None:
    labels = [
        status_label(
            VdiDatasetDetails.model_validate(recorded(name)).status, "PlasmoDB"
        )
        for name in (
            "rnaseqrc_import_in_progress",
            "rnaseqrc_import_complete_data_absent",
            "rnaseqrc_data_running",
            "rnaseqrc_installed",
            "rnaseqrc_import_invalid",
            "dataset_import_queued",
        )
    ]

    assert labels == [
        "import_in_progress",
        "import_complete_data_absent",
        "data_running",
        "installed",
        "import_invalid",
        "import_queued",
    ]


def test_every_body_in_the_store_has_provenance_and_nothing_else_does() -> None:
    store = FIXTURE_ROOT / "vdi"

    bodies = {path.stem for path in store.glob("*.json")} - {"provenance"}

    assert set(load_provenance(store)) == bodies


async def test_a_compressed_response_is_recorded_decoded() -> None:
    plain = json.dumps(recorded("plugins")).encode()

    def handle(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200, headers={"Content-Encoding": "gzip"}, content=gzip.compress(plain)
        )

    recorder = ResponseRecorder(httpx.MockTransport(handle))
    client = VdiClient(base_url=BASE_URL, transport=recorder)

    plugins = await client.plugins()
    await client.close()

    assert recorder.last_body == plain
    assert len(plugins) == 6
