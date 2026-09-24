"""One site's VDI user-dataset service, called as the signed-in researcher."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from http import HTTPStatus
from typing import Literal

import httpx
from pydantic import ConfigDict, Field, RootModel

from veupathdb.auth_context import resolve_user_auth_token
from veupathdb.errors import (
    VEuPathDBError,
    VEuPathDBErrorCode,
    validate_response,
)
from veupathdb.model import CamelModel
from veupathdb.wdk.vdi.models import (
    RNASEQRC,
    VdiDatasetDetails,
    VdiDatasetListEntry,
    VdiDatasetPostMeta,
    VdiDatasetPostResponse,
    VdiPlugin,
    VdiPluginDataType,
)
from veupathdb.wdk.vdi.rnaseqrc import RnaSeqRcUpload

_SERVICE = "VEuPathDB user datasets"
_UPLOAD_FILE_NAME = "gene-list.txt"
_EMPTY_GENE_LIST = "A gene list with no genes cannot be published."
_FIRST_ERROR_STATUS = 400
_GONE_STATUSES = frozenset({HTTPStatus.NOT_FOUND, HTTPStatus.GONE})
_UPLOAD_PART_TYPE = "text/plain"
type VdiOwnership = Literal["any", "owned", "shared"]


class VdiServiceError(VEuPathDBError[VEuPathDBErrorCode]):
    """The dataset service refused a request or could not answer it."""

    def __init__(self, detail: str, status: int = 502) -> None:
        super().__init__(
            code=VEuPathDBErrorCode.EXTERNAL_SERVICE_ERROR,
            title=f"External service error: {_SERVICE}",
            status=status,
            detail=detail,
        )


class VdiDatasetGoneError(VdiServiceError):
    """No dataset with that identifier is readable by this account any more."""

    def __init__(self, vdi_id: str) -> None:
        super().__init__(
            f"Dataset {vdi_id} is deleted or no longer visible to this account.",
            status=HTTPStatus.NOT_FOUND,
        )


def _details_part(details: VdiDatasetPostMeta) -> tuple[str, tuple[None, str, str]]:
    return (
        "details",
        (
            None,
            details.model_dump_json(by_alias=True, exclude_none=True),
            "application/json",
        ),
    )


class _Listing(RootModel[list[VdiDatasetListEntry]]):
    pass


class _Plugins(RootModel[list[VdiPlugin]]):
    pass


class _VdiInputErrors(CamelModel):
    model_config = ConfigDict(extra="ignore")

    general: list[str] = Field(default_factory=list)
    by_key: dict[str, list[str]] = Field(default_factory=dict)

    def text(self) -> str:
        keyed = (
            f"{key}: {reason}"
            for key, reasons in self.by_key.items()
            for reason in reasons
        )
        return "; ".join([*self.general, *keyed])


class _VdiProblem(CamelModel):
    """The refusal body the service returns for every non-2xx status."""

    model_config = ConfigDict(extra="ignore")

    status: str = ""
    message: str = ""
    errors: _VdiInputErrors = Field(default_factory=_VdiInputErrors)


class VdiClient:
    """One site's VDI service. The request's own registered token authenticates it.

    The deployment's service account is never a substitute: a dataset belongs
    to the researcher who published it.
    """

    def __init__(
        self,
        *,
        base_url: str,
        timeout: float = 60.0,
        transport: httpx.AsyncBaseTransport | None = None,
        auth_token: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.auth_token = auth_token
        self._client: httpx.AsyncClient | None = None
        self._transport = transport
        self._lock = asyncio.Lock()

    async def close(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def _http(self) -> httpx.AsyncClient:
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._lock:
            if self._client is None or self._client.is_closed:
                self._client = httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(self.timeout),
                    transport=self._transport,
                )
            return self._client

    def _auth(self) -> dict[str, str]:
        """The bearer header the service accepts, from the token this request carries."""
        token = resolve_user_auth_token(self.auth_token)
        return {"Authorization": f"Bearer {token}", "Accept": "application/json"}

    async def _send(self, request: httpx.Request) -> httpx.Response:
        client = await self._http()
        try:
            response = await client.send(request)
        except httpx.HTTPError as exc:
            msg = f"{request.method} {request.url.path} could not be reached: {exc}"
            raise VdiServiceError(msg) from exc
        if response.status_code >= _FIRST_ERROR_STATUS:
            raise self._failure(request, response)
        return response

    def _failure(
        self, request: httpx.Request, response: httpx.Response
    ) -> VdiServiceError:
        problem = self._problem(response.text)
        detail = (
            f"{request.method} {request.url.path}: "
            f"{problem.message or problem.errors.text() or problem.status or response.text[:500]}"
        )
        return VdiServiceError(detail, response.status_code)

    def _problem(self, body: str) -> _VdiProblem:
        try:
            return _VdiProblem.model_validate_json(body)
        except ValueError:
            return _VdiProblem()

    async def create_genelist(
        self, *, details: VdiDatasetPostMeta, gene_ids: Sequence[str]
    ) -> VdiDatasetPostResponse:
        """Publish a gene list. The service answers before it is installed."""
        if not gene_ids:
            raise VdiServiceError(_EMPTY_GENE_LIST, HTTPStatus.UNPROCESSABLE_ENTITY)
        client = await self._http()
        body = "".join(f"{gene_id}\n" for gene_id in gene_ids)
        request = client.build_request(
            "POST",
            "/datasets",
            headers=self._auth(),
            files=[
                _details_part(details),
                ("dataFile", (_UPLOAD_FILE_NAME, body.encode(), _UPLOAD_PART_TYPE)),
            ],
        )
        response = await self._send(request)
        return validate_response(
            VdiDatasetPostResponse, response.json(), "VDI create response"
        )

    async def create_rnaseqrc(
        self, *, details: VdiDatasetPostMeta, upload: RnaSeqRcUpload
    ) -> VdiDatasetPostResponse:
        """Upload RNA-Seq raw counts: one part per file, streamed, with the manifest.

        The file extensions are checked against the plugin's own list first.
        """
        if details.type != RNASEQRC:
            msg = f"create_rnaseqrc sends rnaseqrc details, not {details.type.name}."
            raise ValueError(msg)
        headers = self._auth()
        data_type = await self._served(details)
        files = upload.files(data_type.allowed_file_extensions)
        client = await self._http()
        request = client.build_request(
            "POST",
            "/datasets",
            headers=headers,
            files=[
                _details_part(details),
                *(
                    ("dataFile", (name, content, _UPLOAD_PART_TYPE))
                    for name, content in files
                ),
            ],
        )
        response = await self._send(request)
        return validate_response(
            VdiDatasetPostResponse, response.json(), "VDI create response"
        )

    async def _served(self, details: VdiDatasetPostMeta) -> VdiPluginDataType:
        for plugin in await self.plugins():
            data_type = plugin.data_type(details.type)
            if data_type is not None:
                return data_type
        msg = f"No VDI plugin serves {details.type.name} {details.type.version}."
        raise VdiServiceError(msg, HTTPStatus.UNPROCESSABLE_ENTITY)

    async def list_datasets(
        self, install_target: str, ownership: VdiOwnership = "owned"
    ) -> list[VdiDatasetListEntry]:
        """The datasets this account owns, or that are shared with it, on one site."""
        client = await self._http()
        request = client.build_request(
            "GET",
            "/datasets",
            headers=self._auth(),
            params={"install_target": install_target, "ownership": ownership},
        )
        response = await self._send(request)
        return validate_response(_Listing, response.json(), "VDI dataset listing").root

    async def plugins(self) -> list[VdiPlugin]:
        """The plugins and the types they serve. The service needs no credential."""
        client = await self._http()
        request = client.build_request(
            "GET", "/plugins", headers={"Accept": "application/json"}
        )
        response = await self._send(request)
        return validate_response(_Plugins, response.json(), "VDI plugin listing").root

    async def get(self, vdi_id: str) -> VdiDatasetDetails:
        """Read one dataset and its three status axes."""
        client = await self._http()
        request = client.build_request(
            "GET", f"/datasets/{vdi_id}", headers=self._auth()
        )
        try:
            response = await self._send(request)
        except VdiServiceError as exc:
            if exc.status in _GONE_STATUSES:
                raise VdiDatasetGoneError(vdi_id) from exc
            raise
        return validate_response(
            VdiDatasetDetails, response.json(), "VDI dataset details"
        )

    async def delete(self, vdi_id: str) -> None:
        """Mark a dataset deleted. Every install target drops it."""
        client = await self._http()
        request = client.build_request(
            "DELETE", f"/datasets/{vdi_id}", headers=self._auth()
        )
        await self._send(request)
