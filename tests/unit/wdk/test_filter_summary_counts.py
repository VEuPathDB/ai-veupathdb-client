"""What the summary counts of a filter parameter send and what they read."""

from __future__ import annotations

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.testing.wdk_fixtures import fixture_request, load_recorded
from veupathdb.wdk import WDKFilterSummaryCounts
from veupathdb.wdk.client import VEuPathDBClient

_FIXTURE = "filter_summary_counts_ngs_snps"


async def test_the_request_is_the_one_the_fixture_was_recorded_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = VEuPathDBClient("https://example.invalid/service")
    post = Recorder(reply=load_recorded(_FIXTURE).json_body())
    monkeypatch.setattr(client, "post", post)
    recorded = fixture_request(_FIXTURE)

    counts = await client.get_filter_summary_counts(
        "transcript",
        "GenesByNgsSnps",
        "variation_sample_meta",
        {
            "organismSinglePick": '["Plasmodium falciparum 3D7"]',
            "eda_sample_table_suffix": "s3be28bbe14_sample",
            "variation_sample_meta": '{"filters": []}',
        },
        filters=[],
    )

    assert (post.paths, post.body) == ([recorded.path], recorded.body)
    assert counts == WDKFilterSummaryCounts(
        filtered=538, unfiltered=538, native_filtered=538, native_unfiltered=538
    )
