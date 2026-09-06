"""Where a site's VDI service lives, and where its datasets are read on the web."""

from __future__ import annotations

from veupathdb.wdk.factory import (
    get_site,
    get_vdi_client,
    list_sites,
)


def test_the_vdi_base_url_is_the_site_origin_plus_vdi() -> None:
    site = get_site("plasmodb")

    assert site.base_url == "https://plasmodb.org/plasmo/service"
    assert site.vdi_base_url == "https://plasmodb.org/vdi"


def test_every_configured_site_derives_a_vdi_base_url() -> None:
    for site in list_sites():
        assert site.vdi_base_url.endswith("/vdi")
        assert "/service" not in site.vdi_base_url


def test_the_dataset_page_sits_beside_the_strategy_pages() -> None:
    site = get_site("plasmodb")

    assert site.dataset_url("soV5JEQEcF00p") == (
        "https://plasmodb.org/plasmo/app/workspace/datasets/soV5JEQEcF00p"
    )


def test_the_factory_builds_one_client_per_site() -> None:
    first = get_vdi_client("plasmodb")
    again = get_vdi_client("plasmodb")
    other = get_vdi_client("toxodb")

    assert first is again
    assert first is not other
    assert first.base_url == "https://plasmodb.org/vdi"
