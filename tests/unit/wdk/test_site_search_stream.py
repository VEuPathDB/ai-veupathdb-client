"""The streaming form of site-search: its line shape, its body, and its bound."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from veupathdb.errors import VEuPathDBError
from veupathdb.testing.wdk_fixtures import FIXTURE_DIR, RecordedWDKResponse
from veupathdb.wdk.site_search_client import (
    STREAM_MEDIA_TYPE,
    SiteSearchClient,
    SiteSearchStreamRecord,
)

STREAM_FIXTURE = FIXTURE_DIR / "site_search_stream_genes.json"

PAGED_CEILING = 50
"""``SearchRequest.MAX_RECORDS_IN_PAGED_RESPONSE`` upstream."""


def _recorded_stream() -> RecordedWDKResponse:
    return RecordedWDKResponse.model_validate_json(
        Path(STREAM_FIXTURE).read_text(encoding="utf-8")
    )


def _client_over(handler: httpx.MockTransport) -> SiteSearchClient:
    client = SiteSearchClient("https://plasmodb.org", "PlasmoDB")
    client._client = httpx.AsyncClient(transport=handler)
    return client


def test_a_stream_line_parses_into_the_typed_record() -> None:
    record = SiteSearchStreamRecord.from_tabular_line(
        '["PF3D7_0616000"]\t33.85314\tPlasmoDB'
    )

    assert record == SiteSearchStreamRecord(
        primary_key=["PF3D7_0616000"], score=33.85314, project="PlasmoDB"
    )


def test_a_line_whose_project_column_is_empty_still_parses() -> None:
    record = SiteSearchStreamRecord.from_tabular_line('["PF3D7_1133400"]\t0.7266922\t')

    assert record is not None
    assert (record.primary_key, record.score, record.project) == (
        ["PF3D7_1133400"],
        0.7266922,
        "",
    )


def test_a_line_with_no_columns_is_not_a_record() -> None:
    parsed = [
        SiteSearchStreamRecord.from_tabular_line(line)
        for line in ("", "   ", '["PF3D7_0616000"]\t1.0\t')
    ]

    assert parsed == [
        None,
        None,
        SiteSearchStreamRecord(primary_key=["PF3D7_0616000"], score=1.0),
    ]


def test_the_recorded_stream_reaches_past_what_one_page_holds() -> None:
    """The fixture is the same query the paged form caps at fifty records."""
    lines = _recorded_stream().raw_text().splitlines()
    records = [SiteSearchStreamRecord.from_tabular_line(line) for line in lines]

    assert len(records) == 352
    assert len(records) > PAGED_CEILING
    assert [r for r in records if r is None] == []
    assert [r.primary_key[0] for r in records if r][:3] == [
        "PF3D7_0616000",
        "PF3D7_0626800",
        "PF3D7_0922500",
    ]


def test_the_recorded_stream_is_ordered_by_descending_score() -> None:
    records = [
        record
        for line in _recorded_stream().raw_text().splitlines()
        if (record := SiteSearchStreamRecord.from_tabular_line(line)) is not None
    ]
    scores = [record.score for record in records]

    assert scores == sorted(scores, reverse=True)
    assert (scores[0], scores[-1]) == (33.85314, 0.7266922)


@pytest.mark.asyncio
async def test_the_stream_request_omits_pagination_and_names_the_document_type() -> (
    None
):
    """Site-search answers a stream request carrying a pagination key with a 500."""
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content)
        seen["accept"] = request.headers["accept"]
        return httpx.Response(200, text='["PF3D7_0616000"]\t1.0\tPlasmoDB\n')

    client = _client_over(httpx.MockTransport(handler))

    await client.stream_records(
        "kinase",
        document_type="gene",
        organisms=["Plasmodium falciparum 3D7"],
        max_records=10,
    )
    await client.close()

    assert seen["accept"] == STREAM_MEDIA_TYPE
    assert seen["body"] == {
        "searchText": "kinase",
        "restrictToProject": "PlasmoDB",
        "restrictSearchToOrganisms": ["Plasmodium falciparum 3D7"],
        "documentTypeFilter": {"documentType": "gene"},
    }


@pytest.mark.asyncio
async def test_the_stream_stops_at_the_requested_bound() -> None:
    body = "".join(f'["PF3D7_{i:06d}"]\t1.0\tPlasmoDB\n' for i in range(500))
    client = _client_over(
        httpx.MockTransport(lambda _request: httpx.Response(200, text=body))
    )

    records = await client.stream_records("kinase", document_type="gene", max_records=7)
    await client.close()

    assert [r.primary_key[0] for r in records] == [f"PF3D7_{i:06d}" for i in range(7)]


@pytest.mark.asyncio
async def test_a_refused_stream_surfaces_as_an_application_error() -> None:
    client = _client_over(
        httpx.MockTransport(lambda _request: httpx.Response(500, text=""))
    )

    with pytest.raises(VEuPathDBError, match="Site-search stream failed"):
        await client.stream_records("kinase", document_type="gene", max_records=10)
    await client.close()
