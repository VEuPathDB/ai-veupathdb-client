"""How the hidden-default sweep reads search metadata, without a network."""

from __future__ import annotations

import httpx
import pytest
from tests.live.hidden_defaults import hidden_by_search

from veupathdb.wdk.probe import WDKProbe

pytestmark = pytest.mark.asyncio

_WITH_A_HIDDEN_DEFAULT = """
{"searchData": {"parameters": [
  {"name": "channel", "type": "string-param", "initialDisplayValue": "0",
   "isVisible": false},
  {"name": "organism", "type": "enum-param", "initialDisplayValue": "[]",
   "isVisible": true}
]}}
"""

_WITH_NO_HIDDEN_DEFAULT = """
{"searchData": {"parameters": [
  {"name": "organism", "type": "enum-param", "initialDisplayValue": "[]",
   "isVisible": true}
]}}
"""


def _document(name: str, text: str, status: int = 200) -> WDKProbe:
    return WDKProbe(
        method="GET",
        url=f"https://plasmodb.org/plasmo/service/{name}",
        status=status,
        contentType="application/json",
        text=text,
    )


async def test_a_search_with_a_hidden_required_default_is_kept() -> None:
    async def read(name: str) -> WDKProbe:
        return _document(
            name,
            _WITH_A_HIDDEN_DEFAULT
            if name == "GenesByRNASeq"
            else _WITH_NO_HIDDEN_DEFAULT,
        )

    sweep = await hidden_by_search(read, ["GenesByRNASeq", "GenesByTaxon"])

    assert list(sweep.hidden) == ["GenesByRNASeq"]
    assert [p.name for p in sweep.hidden["GenesByRNASeq"]] == ["channel", "organism"]
    assert sweep.unread == []


async def test_a_search_whose_metadata_never_arrives_is_named_not_raised() -> None:
    """One transport failure leaves the other searches measurable."""

    timed_out = httpx.ReadTimeout("the read did not complete")

    async def read(name: str) -> WDKProbe:
        if name == "GenesByTaxon":
            raise timed_out
        return _document(name, _WITH_A_HIDDEN_DEFAULT)

    sweep = await hidden_by_search(read, ["GenesByRNASeq", "GenesByTaxon"])

    assert sweep.unread == ["GenesByTaxon"]
    assert list(sweep.hidden) == ["GenesByRNASeq"]


async def test_a_search_that_answers_500_is_read_as_carrying_nothing() -> None:
    async def read(name: str) -> WDKProbe:
        return _document(name, "Internal Error", status=500)

    sweep = await hidden_by_search(read, ["GenesByICEMRHostResponse"])

    assert sweep.hidden == {}
    assert sweep.unread == []
