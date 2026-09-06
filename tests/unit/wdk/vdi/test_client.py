"""The VDI client: what it sends, what it refuses, and how it reports a failure."""

from __future__ import annotations

import inspect
import json
import re
from pathlib import Path

import httpx
import pytest
from tests.unit.wdk.vdi._wire import (
    BASE_URL,
    PROBE_ID,
    TOKEN,
    recorded,
    registered_token,
    vdi_client,
)

from veupathdb.errors import WDKLoginRequiredError
from veupathdb.wdk.vdi.client import (
    VdiClient,
    VdiDatasetGoneError,
    VdiServiceError,
)
from veupathdb.wdk.vdi.models import (
    VdiDatasetPostMeta,
    VdiDatasetType,
    VdiVisibility,
)

__all__ = ["registered_token"]

GENELIST = VdiDatasetType(name="genelist", version="1.0")

_DETAILS_PART = re.compile(r'name="details".*?\r\n\r\n(?P<body>.*?)\r\n--', re.DOTALL)


def _details_part(body: str) -> object:
    match = _DETAILS_PART.search(body)
    assert match is not None
    return json.loads(match.group("body"))


def _meta() -> VdiDatasetPostMeta:
    return VdiDatasetPostMeta(
        type=GENELIST,
        install_targets=["PlasmoDB"],
        name="Kinases with a signal peptide",
        summary="Three genes from PathFinder.",
        visibility=VdiVisibility.PRIVATE,
    )


class _Recorder:
    """Answers every request with one response and keeps what it was sent."""

    def __init__(self, status: int, body: object) -> None:
        self._status = status
        self._body = body
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            if self._body is None:
                return httpx.Response(self._status)
            return httpx.Response(self._status, json=self._body)

        return httpx.MockTransport(handle)


@pytest.mark.usefixtures("registered_token")
class TestCreatingAGeneList:
    async def test_the_request_is_a_multipart_post_carrying_details_and_the_file(
        self,
    ) -> None:
        recorder = _Recorder(202, recorded("dataset_post_response"))
        client = vdi_client(recorder.transport())

        created = await client.create_genelist(
            details=_meta(), gene_ids=["PF3D7_1133400", "PF3D7_0709000"]
        )
        await client.close()

        request = recorder.requests[0]
        sent = request.content.decode()
        assert created.dataset_id == PROBE_ID
        assert request.method == "POST"
        assert str(request.url) == f"{BASE_URL}/datasets"
        assert request.headers["content-type"].startswith("multipart/form-data")
        assert 'name="details"' in sent
        assert 'name="dataFile"' in sent
        assert _details_part(sent) == {
            "type": {"name": "genelist", "version": "1.0"},
            "installTargets": ["PlasmoDB"],
            "name": "Kinases with a signal peptide",
            "summary": "Three genes from PathFinder.",
            "origin": "direct-upload",
            "visibility": "private",
            "dependencies": [],
        }
        assert "PF3D7_1133400\nPF3D7_0709000\n" in sent

    async def test_the_uploaded_file_holds_one_gene_id_per_line(self) -> None:
        recorder = _Recorder(202, recorded("dataset_post_response"))
        client = vdi_client(recorder.transport())

        await client.create_genelist(
            details=_meta(), gene_ids=["PF3D7_1133400", "PF3D7_0709000"]
        )
        await client.close()

        body = recorder.requests[0].content.decode()
        assert body.count("PF3D7_") == 2
        assert ".txt" in body

    async def test_a_gene_list_with_no_ids_is_refused_before_the_call(self) -> None:
        recorder = _Recorder(202, recorded("dataset_post_response"))
        client = vdi_client(recorder.transport())

        with pytest.raises(VdiServiceError):
            await client.create_genelist(details=_meta(), gene_ids=[])
        await client.close()

        assert recorder.requests == []

    async def test_the_request_carries_the_bearer_the_service_accepted(self) -> None:
        recorder = _Recorder(202, recorded("dataset_post_response"))
        client = vdi_client(recorder.transport())

        await client.create_genelist(details=_meta(), gene_ids=["PF3D7_1133400"])
        await client.close()

        assert recorder.requests[0].headers["authorization"] == f"Bearer {TOKEN}"


@pytest.mark.usefixtures("registered_token")
class TestReadingAndRemoving:
    async def test_get_reads_the_three_status_axes(self) -> None:
        recorder = _Recorder(200, recorded("dataset_installed"))
        client = vdi_client(recorder.transport())

        details = await client.get(PROBE_ID)
        await client.close()

        assert str(recorder.requests[0].url) == f"{BASE_URL}/datasets/{PROBE_ID}"
        assert details.installed_targets() == ["PlasmoDB"]

    async def test_a_deleted_dataset_is_reported_as_gone(self) -> None:
        recorder = _Recorder(404, {"status": "not-found"})
        client = vdi_client(recorder.transport())

        with pytest.raises(VdiDatasetGoneError):
            await client.get(PROBE_ID)
        await client.close()

    async def test_a_dataset_the_service_removed_is_also_reported_as_gone(self) -> None:
        recorder = _Recorder(410, {"status": "gone"})
        client = vdi_client(recorder.transport())

        with pytest.raises(VdiDatasetGoneError):
            await client.get(PROBE_ID)
        await client.close()

    async def test_delete_sends_a_delete_and_reads_the_empty_body(self) -> None:
        recorder = _Recorder(204, None)
        client = vdi_client(recorder.transport())

        await client.delete(PROBE_ID)
        await client.close()

        assert recorder.requests[0].method == "DELETE"
        assert str(recorder.requests[0].url) == f"{BASE_URL}/datasets/{PROBE_ID}"


class TestTheClientNeverActsWithoutTheUsersOwnLogin:
    async def test_a_call_with_no_registered_token_is_refused(self) -> None:
        recorder = _Recorder(200, recorded("dataset_installed"))
        client = vdi_client(recorder.transport())

        with pytest.raises(WDKLoginRequiredError):
            await client.get(PROBE_ID)
        await client.close()

        assert recorder.requests == []

    def test_the_client_module_never_reads_the_deployment_settings(self) -> None:
        source = Path(inspect.getfile(VdiClient)).read_text()

        assert "settings" not in source


@pytest.mark.usefixtures("registered_token")
class TestAFailureNamesTheServiceAndTheStatus:
    async def test_a_refusal_becomes_a_typed_error_carrying_the_status(self) -> None:
        recorder = _Recorder(422, {"status": "bad-request", "message": "no such type"})
        client = vdi_client(recorder.transport())

        with pytest.raises(VdiServiceError) as caught:
            await client.create_genelist(details=_meta(), gene_ids=["PF3D7_1133400"])
        await client.close()

        assert caught.value.status == 422
        assert caught.value.detail is not None
        assert "no such type" in caught.value.detail

    async def test_a_server_error_is_reported_with_its_own_status(self) -> None:
        recorder = _Recorder(500, {"status": "server-error"})
        client = vdi_client(recorder.transport())

        with pytest.raises(VdiServiceError) as caught:
            await client.get(PROBE_ID)
        await client.close()

        assert caught.value.status == 500
