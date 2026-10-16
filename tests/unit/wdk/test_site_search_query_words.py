"""Site-search refuses a query of more than six words, so the client sends at most six."""

from __future__ import annotations

import json

import httpx
import pytest

from veupathdb.wdk.site_search_client import SiteSearchClient

WORD_CEILING = 6
"""``SearchRequest.MAX_TERMS_IN_QUERY`` upstream."""


async def _sent_text(query: str, *, stream: bool) -> str:
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(json.loads(request.content)["searchText"])
        if stream:
            return httpx.Response(200, text="")
        return httpx.Response(200, json={"searchResults": {"totalCount": 0}})

    client = SiteSearchClient("https://qa.vectorbase.org", "VectorBase")
    client._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    if stream:
        await client.stream_records(query, document_type="gene", max_records=5)
    else:
        await client.search(query)
    await client.close()
    return seen[0]


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_a_short_query_is_sent_as_written(stream: bool) -> None:
    assert await _sent_text("RNA-Seq datasets", stream=stream) == "RNA-Seq datasets"


@pytest.mark.asyncio
@pytest.mark.parametrize("stream", [False, True])
async def test_a_long_query_drops_its_filler_words_first(stream: bool) -> None:
    sent = await _sent_text(
        "RNA-Seq datasets associated with the Anopheles gambiae genome",
        stream=stream,
    )

    assert sent == "RNA-Seq datasets associated Anopheles gambiae genome"


@pytest.mark.asyncio
async def test_a_query_long_without_filler_keeps_its_first_six_words() -> None:
    sent = await _sent_text(
        "Anopheles gambiae species complex genome assembly RNA-Seq data volume",
        stream=False,
    )

    assert sent == "Anopheles gambiae species complex genome assembly"
    assert len(sent.split()) == WORD_CEILING


@pytest.mark.asyncio
async def test_a_query_of_filler_words_alone_keeps_six_of_them() -> None:
    sent = await _sent_text("what is in the one of the and for", stream=False)

    assert sent == "what is in the one of"
