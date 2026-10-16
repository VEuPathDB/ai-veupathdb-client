"""A search's column counted by value: one request, no step, the search's column
filters sent with it, and the site's counts read back."""

from __future__ import annotations

from typing import Any

import pytest

from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.wdk_models import WDKAttributeField, WDKSearchConfig

_REPLY = {
    "statistics": {
        "subsetSize": 379,
        "numVarValues": 379,
        "numDistinctValues": 58,
        "numDistinctEntityRecords": 379,
        "numMissingCases": 0,
    },
    "histogram": [
        {
            "value": 67,
            "binStart": "<i>Aedes aegypti</i> LVP_AGWG",
            "binEnd": "<i>Aedes aegypti</i> LVP_AGWG",
            "binLabel": "<i>Aedes aegypti</i> LVP_AGWG",
        },
        {
            "value": 40,
            "binStart": "<i>Anopheles gambiae</i> PEST",
            "binEnd": "<i>Anopheles gambiae</i> PEST",
            "binLabel": "<i>Anopheles gambiae</i> PEST",
        },
    ],
}


class _Sent:
    def __init__(self) -> None:
        self.paths: list[str] = []
        self.bodies: list[Any] = []

    async def __call__(self, path: str, json: Any = None, **_: object) -> Any:
        self.paths.append(path)
        self.bodies.append(json)
        return _REPLY


async def _unchanged(
    _rt: str, _search: str, parameters: dict[str, str]
) -> dict[str, str]:
    return parameters


async def test_the_column_is_counted_on_the_search_with_its_filters(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = VEuPathDBClient("https://qa.vectorbase.org/vectorbase.qa/service")
    sent = _Sent()
    monkeypatch.setattr(client, "post", sent)
    monkeypatch.setattr(client, "expand_tree_params_to_leaves", _unchanged)

    distribution = await client.run_search_column_report(
        "dataset",
        "AllDatasets",
        WDKSearchConfig(
            parameters={},
            column_filters={"newcategory": {"byValue": {"values": ["RNASeq"]}}},
        ),
        "organism_prefix",
    )

    assert sent.paths == [
        "/record-types/dataset/searches/AllDatasets/columns/organism_prefix/reports/byValue"
    ]
    assert sent.bodies == [
        {
            "searchConfig": {
                "parameters": {},
                "columnFilters": {"newcategory": {"byValue": {"values": ["RNASeq"]}}},
            },
            "reportConfig": {},
        }
    ]
    assert [(b.bin_label, b.value) for b in distribution.histogram] == [
        ("<i>Aedes aegypti</i> LVP_AGWG", 67),
        ("<i>Anopheles gambiae</i> PEST", 40),
    ]
    assert (
        distribution.statistics.subset_size,
        distribution.statistics.num_distinct_values,
    ) == (379, 58)


def test_an_attribute_names_the_column_tools_the_site_offers() -> None:
    field = WDKAttributeField.model_validate(
        {
            "name": "organism_prefix",
            "displayName": "Organism(s)",
            "tools": {"reports": ["byValue"], "filters": ["byValue"]},
        }
    )

    assert (field.tools.reports, field.tools.filters) == (["byValue"], ["byValue"])
    assert WDKAttributeField.model_validate({"name": "overview"}).tools.reports == []
