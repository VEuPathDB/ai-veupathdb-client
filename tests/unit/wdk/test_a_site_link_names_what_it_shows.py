from __future__ import annotations

import pytest

from veupathdb.wdk import (
    ImportLink,
    OtherPageLink,
    RecordLink,
    SearchFormLink,
    SearchResultLink,
    StrategyLink,
    find_site_links,
    parse_site_link,
)

PORTAL_APP = "https://qa.veupathdb.org/veupathdb.qa/app"
PLASMO_APP = "https://qa.plasmodb.org/plasmo.qa/app"


def test_a_result_link_names_its_search_and_carries_its_parameters() -> None:
    link = parse_site_link(
        f"{PLASMO_APP}/search/transcript/GenesByTaxon/result"
        "?param.organism=Plasmodium+falciparum+3D7&filterTerm=kinase"
    )

    assert link == SearchResultLink(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByTaxon",
        parameters={"organism": "Plasmodium falciparum 3D7"},
    )


def test_a_result_link_without_parameters_carries_none() -> None:
    link = parse_site_link(f"{PORTAL_APP}/search/organism/GenomeDataTypes/result")

    assert link == SearchResultLink(
        site_id="veupathdb",
        record_type="organism",
        search_name="GenomeDataTypes",
        parameters={},
    )


def test_a_form_link_names_its_search() -> None:
    link = parse_site_link(
        f"{PLASMO_APP}/search/transcript/GenesByTaxon?autoRun&param.organism=x"
    )

    assert link == SearchFormLink(
        site_id="plasmodb",
        record_type="transcript",
        search_name="GenesByTaxon",
        parameters={"organism": "x"},
    )


def test_a_record_link_names_every_part_of_its_key() -> None:
    link = parse_site_link(f"{PLASMO_APP}/record/gene/PF3D7_1133400")

    assert link == RecordLink(
        site_id="plasmodb", record_type="gene", primary_key=["PF3D7_1133400"]
    )


@pytest.mark.parametrize(
    ("path", "strategy_id", "step_id"),
    [
        ("/workspace/strategies/214670300", 214670300, None),
        ("/workspace/strategies/214670300/227351670", 214670300, 227351670),
    ],
)
def test_a_strategy_link_names_its_strategy_and_its_open_step(
    path: str, strategy_id: int, step_id: int | None
) -> None:
    assert parse_site_link(f"{PORTAL_APP}{path}") == StrategyLink(
        site_id="veupathdb", strategy_id=strategy_id, step_id=step_id
    )


def test_an_import_link_names_its_signature() -> None:
    assert parse_site_link(f"{PLASMO_APP}/import/4f2c9a8e1b7d") == ImportLink(
        site_id="plasmodb", signature="4f2c9a8e1b7d"
    )


@pytest.mark.parametrize(
    "path",
    ["/workspace/basket", "/user/profile", "/workspace/strategies/all", "/"],
)
def test_any_other_page_of_a_site_is_named_as_another_page(path: str) -> None:
    assert parse_site_link(f"{PLASMO_APP}{path}") == OtherPageLink(
        site_id="plasmodb", path=path
    )


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/plasmo.qa/app/search/transcript/GenesByTaxon",
        "https://qa.plasmodb.org/plasmo.qa/service/record-types",
        "https://qa.plasmodb.org/plasmo/app/search/transcript/GenesByTaxon",
    ],
)
def test_a_link_outside_every_configured_site_names_no_site(url: str) -> None:
    assert parse_site_link(url) is None


def test_a_link_without_its_scheme_names_its_site() -> None:
    link = parse_site_link(
        "qa.veupathdb.org/veupathdb.qa/app/search/organism/GenomeDataTypes/result"
    )

    assert link == SearchResultLink(
        site_id="veupathdb",
        record_type="organism",
        search_name="GenomeDataTypes",
        parameters={},
    )


def test_the_links_in_a_message_are_found_in_their_order() -> None:
    text = (
        "can you read this web page "
        f"({PORTAL_APP}/search/organism/GenomeDataTypes/result). "
        f"Also {PLASMO_APP}/record/gene/PF3D7_1133400, and "
        "https://example.org/elsewhere."
    )

    assert find_site_links(text) == [
        f"{PORTAL_APP}/search/organism/GenomeDataTypes/result",
        f"{PLASMO_APP}/record/gene/PF3D7_1133400",
    ]


def test_a_message_with_no_site_link_finds_none() -> None:
    assert find_site_links("list P. falciparum genomes and their BUSCO") == []
