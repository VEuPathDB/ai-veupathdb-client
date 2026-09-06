from __future__ import annotations

from veupathdb.eda.factory import (
    get_eda_analyses_client,
    get_eda_client,
)
from veupathdb.wdk.factory import get_site, list_sites


def test_the_eda_base_url_is_the_site_origin_plus_eda() -> None:
    site = get_site("plasmodb")
    assert site.base_url == "https://plasmodb.org/plasmo/service"
    assert site.eda_base_url == "https://plasmodb.org/eda"


def test_every_configured_site_derives_an_eda_base_url() -> None:
    for site in list_sites():
        assert site.eda_base_url.endswith("/eda")
        assert "/service" not in site.eda_base_url


def test_the_factory_builds_one_client_per_site() -> None:
    first = get_eda_client("plasmodb")
    again = get_eda_client("plasmodb")
    other = get_eda_client("toxodb")
    assert first is again
    assert first is not other
    assert first.base_url == "https://plasmodb.org/eda"


def test_the_analyses_client_carries_the_site_project_id() -> None:
    assert get_eda_analyses_client("plasmodb").project_id == "PlasmoDB"
    assert get_eda_analyses_client("toxodb").project_id == "ToxoDB"
