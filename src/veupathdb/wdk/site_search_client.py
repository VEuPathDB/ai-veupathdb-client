"""HTTP client and response models for the VEuPathDB site-search service.

Site-search is a separate service from WDK. It has its own URL root, it
takes a JSON POST body, and it uses no cookie authentication. The ``Accept``
header picks between the paged JSON answer and the streamed tabular one.
"""

import asyncio
import time
from dataclasses import dataclass
from typing import Self

import httpx
from pydantic import ConfigDict, Field, TypeAdapter, field_validator
from tenacity import (
    AsyncRetrying,
    RetryError,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from veupathdb.errors import VEuPathDBError, VEuPathDBErrorCode
from veupathdb.logging import get_logger
from veupathdb.model import CamelModel
from veupathdb.observer import get_observer
from veupathdb.wdk._observability import (
    SiteSearchRequestTelemetry,
    site_search_retry_logger,
)

logger = get_logger(__name__)

STREAM_MEDIA_TYPE = "application/x-ndjson"
"""What the streaming form of the search answers to."""

_COLUMN_SEPARATOR = "\t"
_PRIMARY_KEY_ADAPTER: TypeAdapter[list[str]] = TypeAdapter(list[str])


class SiteSearchDocumentTypeField(CamelModel):
    """A field descriptor within a document type."""

    name: str
    display_name: str
    term: str
    is_subtitle: bool = False


class SiteSearchDocumentType(CamelModel):
    """A document type returned in the site-search response.

    A WDK record type also carries the search name that bridges the
    document type to WDK strategy creation.
    """

    id: str
    display_name: str
    display_name_plural: str
    count: int = 0
    has_organism_field: bool = False
    search_fields: list[SiteSearchDocumentTypeField] = Field(default_factory=list)
    summary_fields: list[SiteSearchDocumentTypeField] = Field(default_factory=list)
    is_wdk_record_type: bool = False
    wdk_search_name: str | None = None


class SiteSearchCategory(CamelModel):
    """A category that groups document types."""

    name: str
    document_types: list[str] = Field(default_factory=list)


class SiteSearchDocument(CamelModel):
    """A single document from site-search results."""

    document_type: str = ""
    primary_key: list[str] = Field(default_factory=list)
    wdk_primary_key_string: str = ""
    hyperlink_name: str = ""
    organism: list[str] = Field(default_factory=list)
    score: float = 0.0
    summary_field_data: dict[str, str | list[str]] = Field(default_factory=dict)
    found_in_fields: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("organism", mode="before")
    @classmethod
    def _coerce_organism(cls, v: object) -> list[str]:
        """The service sends the organism as either a string or a list."""
        if isinstance(v, str):
            return [v] if v else []
        if isinstance(v, list):
            return [str(x) for x in v if x]
        return []


class SiteSearchResults(CamelModel):
    """The results portion of a site-search response."""

    total_count: int = 0
    documents: list[SiteSearchDocument] = Field(default_factory=list)


class SiteSearchResponse(CamelModel):
    """Full response from the site-search service."""

    search_results: SiteSearchResults = Field(default_factory=SiteSearchResults)
    organism_counts: dict[str, int] = Field(default_factory=dict)
    document_types: list[SiteSearchDocumentType] = Field(default_factory=list)
    categories: list[SiteSearchCategory] = Field(default_factory=list)
    field_counts: dict[str, int] = Field(default_factory=dict)


class SiteSearchStreamRecord(CamelModel):
    """One record of the streaming form: a primary key, its score, its project.

    The service answers to a ND_JSON media type and writes tab separated
    columns whose first column is a JSON array.
    """

    model_config = ConfigDict(frozen=True)

    primary_key: list[str] = Field(default_factory=list)
    score: float = 0.0
    project: str = ""

    @classmethod
    def from_tabular_line(cls, line: str) -> Self | None:
        """One line of the stream, or None when the line carries no columns."""
        primary_key, separator, rest = line.partition(_COLUMN_SEPARATOR)
        if not separator:
            return None
        score, _, project = rest.partition(_COLUMN_SEPARATOR)
        return cls.model_validate(
            {
                "primary_key": _PRIMARY_KEY_ADAPTER.validate_json(primary_key),
                "score": score,
                "project": project.strip(),
            }
        )


@dataclass(frozen=True)
class DocumentTypeFilter:
    """Restricts a site-search query to one document type."""

    document_type: str
    found_only_in_fields: list[str] | None = None


class SiteSearchClient:
    """HTTP client for the VEuPathDB site-search service.

    The site router owns the lifecycle of each instance.
    """

    def __init__(
        self,
        base_url: str,
        project_id: str,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._project_id = project_id
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._client_lock = asyncio.Lock()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is not None and not self._client.is_closed:
            return self._client
        async with self._client_lock:
            if self._client is not None and not self._client.is_closed:
                return self._client
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout, read=90.0),
                follow_redirects=True,
                headers={
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
            )
            return self._client

    async def search(
        self,
        search_text: str,
        *,
        document_type_filter: DocumentTypeFilter | None = None,
        organisms: list[str] | None = None,
        restrict_metadata_to_organisms: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SiteSearchResponse:
        """Query the site-search service.

        Every failure surfaces as an application error.
        """
        telemetry = SiteSearchRequestTelemetry(
            method="POST",
            path="/site-search",
            base_url=self._base_url,
        )
        start = time.monotonic()
        retrying = AsyncRetrying(
            retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            before_sleep=site_search_retry_logger(telemetry),
            reraise=False,
        )
        try:
            result: SiteSearchResponse = await retrying(
                self._search_attempt,
                search_text,
                document_type_filter=document_type_filter,
                organisms=organisms,
                restrict_metadata_to_organisms=restrict_metadata_to_organisms,
                limit=limit,
                offset=offset,
            )
        except RetryError as exc:
            attrs = telemetry.metric_attrs(outcome="error")
            get_observer().on_site_search_request(time.monotonic() - start, attrs)
            raise VEuPathDBError(
                VEuPathDBErrorCode.WDK_ERROR,
                f"Site-search request failed after retries: {exc}",
            ) from exc
        except VEuPathDBError:
            attrs = telemetry.metric_attrs(outcome="error")
            get_observer().on_site_search_request(time.monotonic() - start, attrs)
            raise
        attrs = telemetry.metric_attrs(outcome="ok", status_code=200)
        get_observer().on_site_search_request(time.monotonic() - start, attrs)
        return result

    async def _search_attempt(
        self,
        search_text: str,
        *,
        document_type_filter: DocumentTypeFilter | None = None,
        organisms: list[str] | None = None,
        restrict_metadata_to_organisms: list[str] | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> SiteSearchResponse:
        """Post the query, and retry on transient errors."""
        url = f"{self._base_url}/site-search"
        body = self._request_body(
            search_text,
            document_type_filter=document_type_filter,
            organisms=organisms,
            restrict_metadata_to_organisms=restrict_metadata_to_organisms,
        )
        body["pagination"] = {"offset": offset, "numRecords": limit}

        try:
            client = await self._get_client()
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            if not resp.content:
                return SiteSearchResponse()
            return SiteSearchResponse.model_validate(resp.json())
        except httpx.TimeoutException, httpx.ConnectError:
            raise
        except httpx.HTTPError as exc:
            raise VEuPathDBError(
                VEuPathDBErrorCode.WDK_ERROR,
                f"Site-search request failed: {exc}",
            ) from exc

    def _request_body(
        self,
        search_text: str,
        *,
        document_type_filter: DocumentTypeFilter | None,
        organisms: list[str] | None,
        restrict_metadata_to_organisms: list[str] | None = None,
    ) -> dict[str, object]:
        """The body both forms share. Only the paged form adds a pagination key."""
        body: dict[str, object] = {
            "searchText": search_text or "*",
            "restrictToProject": self._project_id,
        }
        if organisms:
            body["restrictSearchToOrganisms"] = organisms
        if restrict_metadata_to_organisms:
            body["restrictMetadataToOrganisms"] = restrict_metadata_to_organisms
        if document_type_filter:
            doc_filter: dict[str, object] = {
                "documentType": document_type_filter.document_type,
            }
            if document_type_filter.found_only_in_fields:
                doc_filter["foundOnlyInFields"] = (
                    document_type_filter.found_only_in_fields
                )
            body["documentTypeFilter"] = doc_filter
        return body

    async def stream_records(
        self,
        search_text: str,
        *,
        document_type: str,
        organisms: list[str] | None = None,
        max_records: int,
    ) -> list[SiteSearchStreamRecord]:
        """Read the streaming form of the query, up to *max_records* records.

        The stream carries every match, so the bound is the caller's. The
        service requires a document type here and refuses a pagination key.
        """
        telemetry = SiteSearchRequestTelemetry(
            method="POST",
            path="/site-search",
            base_url=self._base_url,
        )
        start = time.monotonic()
        body = self._request_body(
            search_text,
            document_type_filter=DocumentTypeFilter(document_type=document_type),
            organisms=organisms,
        )
        records: list[SiteSearchStreamRecord] = []
        try:
            client = await self._get_client()
            async with client.stream(
                "POST",
                f"{self._base_url}/site-search",
                json=body,
                headers={"Accept": STREAM_MEDIA_TYPE},
            ) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if len(records) >= max_records:
                        break
                    record = SiteSearchStreamRecord.from_tabular_line(line)
                    if record is not None:
                        records.append(record)
        except httpx.HTTPError as exc:
            attrs = telemetry.metric_attrs(outcome="error")
            get_observer().on_site_search_request(time.monotonic() - start, attrs)
            raise VEuPathDBError(
                VEuPathDBErrorCode.WDK_ERROR,
                f"Site-search stream failed: {exc}",
            ) from exc
        attrs = telemetry.metric_attrs(outcome="ok", status_code=200)
        get_observer().on_site_search_request(time.monotonic() - start, attrs)
        return records

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
