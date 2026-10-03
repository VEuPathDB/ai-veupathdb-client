"""What the ontology term summary of a filter parameter sends and what it reads."""

from __future__ import annotations

import pytest
from tests.unit.wdk._step_writes import Recorder

from veupathdb.domain.parameters.values import FilterTermClause
from veupathdb.testing.wdk_fixtures import fixture_request, load_recorded
from veupathdb.wdk.client import VEuPathDBClient

_FIXTURE = "ontology_term_summary_ngs_snps_sex"
_CONTEXT = {
    "organismSinglePick": '["Plasmodium falciparum 3D7"]',
    "eda_sample_table_suffix": "s3be28bbe14_sample",
    "variation_sample_meta": '{"filters":[]}',
}


def _client(monkeypatch: pytest.MonkeyPatch) -> tuple[VEuPathDBClient, Recorder]:
    client = VEuPathDBClient("https://example.invalid/service")
    post = Recorder(reply=load_recorded(_FIXTURE).json_body())
    monkeypatch.setattr(client, "post", post)
    return client, post


async def test_the_request_is_the_body_the_fixture_was_recorded_with(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, post = _client(monkeypatch)

    await client.get_ontology_term_summary(
        "transcript",
        "GenesByNgsSnps",
        "variation_sample_meta",
        "VAR_68bb04bd",
        _CONTEXT,
    )

    assert post.body == fixture_request(_FIXTURE).body


async def test_the_filters_travel_in_the_wire_form_of_a_clause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, post = _client(monkeypatch)
    country = FilterTermClause(field="VAR_8e68b3e5", value=["Cambodia"])

    await client.get_ontology_term_summary(
        "transcript",
        "GenesByNgsSnps",
        "variation_sample_meta",
        "VAR_68bb04bd",
        _CONTEXT,
        filters=[country],
    )

    assert post.body["filters"] == [
        {
            "field": "VAR_8e68b3e5",
            "type": "string",
            "isRange": False,
            "includeUnknown": False,
            "value": ["Cambodia"],
        }
    ]


async def test_each_value_of_the_term_is_read_with_its_two_counts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, _ = _client(monkeypatch)

    summary = await client.get_ontology_term_summary(
        "transcript",
        "GenesByNgsSnps",
        "variation_sample_meta",
        "VAR_68bb04bd",
        _CONTEXT,
    )

    assert [(v.value, v.count, v.filtered_count) for v in summary.value_counts] == [
        ("female", 6, 6),
        ("male", 6, 6),
    ]
    assert (summary.internals_count, summary.internals_filtered_count) == (12, 12)
