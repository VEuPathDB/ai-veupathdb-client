"""The VDI client: what it sends, what it refuses, and how it reports a failure."""

from __future__ import annotations

import io
import json
import re

import httpx
import pytest
from tests.unit.wdk.vdi._wire import (
    BASE_URL,
    PROBE_ID,
    TOKEN,
    deployment_token,
    form_parts,
    no_request_transport,
    recorded,
    registered_token,
    vdi_client,
)

from veupathdb.errors import WDKLoginRequiredError
from veupathdb.wdk.vdi.client import (
    VdiDatasetGoneError,
    VdiServiceError,
)
from veupathdb.wdk.vdi.models import (
    RNASEQRC,
    VdiDatasetDependency,
    VdiDatasetPostMeta,
    VdiDatasetType,
    VdiInstallDisposition,
    VdiVisibility,
)
from veupathdb.wdk.vdi.rnaseqrc import RnaSeqCountFile, RnaSeqRcUpload

__all__ = ["deployment_token", "registered_token"]

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


GENOME = VdiDatasetDependency(
    resource_identifier="PlasmoDB-71_Pfalciparum3D7_Genome",
    resource_display_name="Plasmodium falciparum 3D7",
    resource_version="71",
)
SENSE = b"gene_id\tWT_37C_Rep1\nPF3D7_0100100\t472\n"
ANTISENSE = b"gene_id\tWT_37C_Rep1\nPF3D7_0100100\t9\n"
DETAILS = "sample\tgenotype\nWT_37C_Rep1\twildtype\n"


def _rnaseqrc_meta() -> VdiDatasetPostMeta:
    return VdiDatasetPostMeta(
        type=RNASEQRC,
        install_targets=["PlasmoDB"],
        name="Heat shock counts",
        summary="Twelve samples.",
        dependencies=[GENOME],
    )


def _stranded() -> RnaSeqRcUpload:
    return RnaSeqRcUpload(
        counts=(
            RnaSeqCountFile(name="HS_counts_sense.tsv", content=io.BytesIO(SENSE)),
            RnaSeqCountFile(
                name="HS_counts_antisense.tsv", content=io.BytesIO(ANTISENSE)
            ),
        ),
        sample_details=DETAILS,
    )


class _Router:
    """Answers each method and path with a recorded body and keeps every request."""

    def __init__(self, routes: dict[tuple[str, str], tuple[int, object]]) -> None:
        self._routes = routes
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handle(request: httpx.Request) -> httpx.Response:
            request.read()
            self.requests.append(request)
            status, body = self._routes[(request.method, request.url.path)]
            return httpx.Response(status, json=body)

        return httpx.MockTransport(handle)


def _upload_routes() -> dict[tuple[str, str], tuple[int, object]]:
    return {
        ("GET", "/vdi/plugins"): (200, recorded("plugins")),
        ("POST", "/vdi/datasets"): (202, recorded("rnaseqrc_post_response")),
    }


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

        parts = form_parts(recorder.requests[0])
        assert [(part.name, part.filename) for part in parts] == [
            ("details", None),
            ("dataFile", "gene-list.txt"),
        ]
        assert parts[1].body == b"PF3D7_1133400\nPF3D7_0709000\n"

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


@pytest.mark.usefixtures("registered_token")
class TestCreatingAnRnaSeqRcDataset:
    async def test_create_rnaseqrc_sends_details_and_one_part_per_file(self) -> None:
        router = _Router(_upload_routes())
        client = vdi_client(router.transport())

        created = await client.create_rnaseqrc(
            details=_rnaseqrc_meta(), upload=_stranded()
        )
        await client.close()

        post = router.requests[-1]
        parts = form_parts(post)
        assert {"datasetId": created.dataset_id} == recorded("rnaseqrc_post_response")
        assert post.headers["authorization"] == f"Bearer {TOKEN}"
        assert [part.name for part in parts] == ["details"] + ["dataFile"] * 4
        assert json.loads(parts[0].body) == {
            "type": {"name": "rnaseqrc", "version": "1.0"},
            "installTargets": ["PlasmoDB"],
            "name": "Heat shock counts",
            "summary": "Twelve samples.",
            "origin": "direct-upload",
            "visibility": "private",
            "dependencies": [
                {
                    "resourceIdentifier": "PlasmoDB-71_Pfalciparum3D7_Genome",
                    "resourceVersion": "71",
                    "resourceDisplayName": "Plasmodium falciparum 3D7",
                }
            ],
        }
        assert [(part.filename, part.body) for part in parts[1:]] == [
            ("HS_counts_sense.tsv", SENSE),
            ("HS_counts_antisense.tsv", ANTISENSE),
            ("sample-info.txt", DETAILS.encode()),
            (
                "manifest.tsv",
                (
                    b"sense\tHS_counts_sense.tsv\n"
                    b"antisense\tHS_counts_antisense.tsv\n"
                    b"sample-info\tsample-info.txt\n"
                ),
            ),
        ]

    async def test_the_extensions_come_from_the_plugin_listing(self) -> None:
        router = _Router(_upload_routes())
        client = vdi_client(router.transport())
        upload = RnaSeqRcUpload(
            counts=(RnaSeqCountFile(name="counts.xlsx", content=io.BytesIO(SENSE)),),
            sample_details=DETAILS,
        )

        with pytest.raises(ValueError, match=r"\.txt, \.tsv, \.csv, \.tab"):
            await client.create_rnaseqrc(details=_rnaseqrc_meta(), upload=upload)
        await client.close()

        assert [(r.method, r.url.path) for r in router.requests] == [
            ("GET", "/vdi/plugins")
        ]

    async def test_details_for_another_type_are_refused_before_any_call(
        self,
    ) -> None:
        router = _Router(_upload_routes())
        client = vdi_client(router.transport())
        genelist = _rnaseqrc_meta().model_copy(update={"type": GENELIST})

        with pytest.raises(ValueError, match="rnaseqrc"):
            await client.create_rnaseqrc(details=genelist, upload=_stranded())
        await client.close()

        assert router.requests == []


@pytest.mark.usefixtures("registered_token")
class TestListingAndPlugins:
    async def test_list_datasets_sends_the_target_and_owned(self) -> None:
        router = _Router({("GET", "/vdi/datasets"): (200, recorded("datasets_owned"))})
        client = vdi_client(router.transport())

        entries = await client.list_datasets("PlasmoDB")
        await client.close()

        request = router.requests[0]
        raw = recorded("datasets_owned")
        assert isinstance(raw, list)
        assert dict(request.url.params) == {
            "install_target": "PlasmoDB",
            "ownership": "owned",
        }
        assert request.headers["authorization"] == f"Bearer {TOKEN}"
        assert [entry.dataset_id for entry in entries] == [
            row["datasetId"] for row in raw
        ]
        installed = VdiInstallDisposition.INSTALLED
        failed = VdiInstallDisposition.FAILED
        assert [entry.status.disposition("PlasmoDB") for entry in entries] == [
            installed,
            installed,
            failed,
            installed,
            failed,
            installed,
            installed,
            failed,
            installed,
        ]

    async def test_list_datasets_passes_another_ownership(self) -> None:
        router = _Router({("GET", "/vdi/datasets"): (200, [])})
        client = vdi_client(router.transport())

        assert await client.list_datasets("ToxoDB", ownership="shared") == []
        await client.close()

        assert dict(router.requests[0].url.params) == {
            "install_target": "ToxoDB",
            "ownership": "shared",
        }

    @pytest.mark.usefixtures("deployment_token")
    async def test_plugins_carries_no_credential(self) -> None:
        router = _Router({("GET", "/vdi/plugins"): (200, recorded("plugins"))})
        client = vdi_client(router.transport())

        plugins = await client.plugins()
        await client.close()

        assert "authorization" not in router.requests[0].headers
        assert [plugin.plugin_name for plugin in plugins] == [
            "noop",
            "genelist",
            "bigwig",
            "biom",
            "wrangler",
            "rnaseq",
        ]


class TestTheClientNeverActsWithoutTheUsersOwnLogin:
    @pytest.mark.usefixtures("deployment_token")
    async def test_a_read_never_travels_as_the_deployment(self) -> None:
        client = vdi_client(no_request_transport())

        with pytest.raises(WDKLoginRequiredError):
            await client.get(PROBE_ID)
        await client.close()

    async def test_a_call_with_no_registered_token_is_refused(self) -> None:
        recorder = _Recorder(200, recorded("dataset_installed"))
        client = vdi_client(recorder.transport())

        with pytest.raises(WDKLoginRequiredError):
            await client.get(PROBE_ID)
        await client.close()

        assert recorder.requests == []

    @pytest.mark.usefixtures("deployment_token")
    async def test_a_publish_never_travels_as_the_deployment(self) -> None:
        client = vdi_client(no_request_transport())

        with pytest.raises(WDKLoginRequiredError):
            await client.create_genelist(details=_meta(), gene_ids=["PF3D7_1133400"])
        await client.close()

    @pytest.mark.usefixtures("deployment_token")
    async def test_a_delete_never_travels_as_the_deployment(self) -> None:
        client = vdi_client(no_request_transport())

        with pytest.raises(WDKLoginRequiredError):
            await client.delete(PROBE_ID)
        await client.close()

    @pytest.mark.usefixtures("deployment_token")
    async def test_a_listing_never_travels_as_the_deployment(self) -> None:
        client = vdi_client(no_request_transport())

        with pytest.raises(WDKLoginRequiredError):
            await client.list_datasets("PlasmoDB")
        await client.close()

    @pytest.mark.usefixtures("deployment_token")
    async def test_an_rnaseqrc_upload_never_travels_as_the_deployment(self) -> None:
        router = _Router(_upload_routes())
        client = vdi_client(router.transport())

        with pytest.raises(WDKLoginRequiredError):
            await client.create_rnaseqrc(details=_rnaseqrc_meta(), upload=_stranded())
        await client.close()

        assert router.requests == []


@pytest.mark.usefixtures("registered_token")
class TestAFailureNamesTheServiceAndTheStatus:
    async def test_a_refusal_becomes_a_typed_error_carrying_the_status(self) -> None:
        recorder = _Recorder(422, {"status": "bad-request", "message": "no such type"})
        client = vdi_client(recorder.transport())

        with pytest.raises(VdiServiceError) as caught:
            await client.create_genelist(details=_meta(), gene_ids=["PF3D7_1133400"])
        await client.close()

        assert caught.value.status == 422
        assert caught.value.detail == "POST /vdi/datasets: no such type"

    async def test_an_invalid_input_refusal_carries_the_services_reason(
        self,
    ) -> None:
        router = _Router(
            {
                ("GET", "/vdi/plugins"): (200, recorded("plugins")),
                ("POST", "/vdi/datasets"): (
                    422,
                    recorded("rnaseqrc_post_long_dependency"),
                ),
            }
        )
        client = vdi_client(router.transport())

        with pytest.raises(VdiServiceError) as caught:
            await client.create_rnaseqrc(details=_rnaseqrc_meta(), upload=_stranded())
        await client.close()

        assert caught.value.status == 422
        assert caught.value.detail == (
            "POST /vdi/datasets: $.details.dependencies[0]: "
            "exceeds the max allowed length of 50 bytes"
        )

    async def test_a_server_error_is_reported_with_its_own_status(self) -> None:
        recorder = _Recorder(500, {"status": "server-error"})
        client = vdi_client(recorder.transport())

        with pytest.raises(VdiServiceError) as caught:
            await client.get(PROBE_ID)
        await client.close()

        assert caught.value.status == 500
        assert caught.value.detail == f"GET /vdi/datasets/{PROBE_ID}: server-error"
