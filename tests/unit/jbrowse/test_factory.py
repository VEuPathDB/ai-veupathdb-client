from __future__ import annotations

from veupathdb.jbrowse.factory import close_all_jbrowse_clients, get_jbrowse_client


def test_the_factory_builds_one_client_per_site_at_its_web_base() -> None:
    first = get_jbrowse_client("plasmodb")
    again = get_jbrowse_client("plasmodb")
    other = get_jbrowse_client("toxodb")
    assert first is again
    assert first is not other
    assert first.base_url == "https://qa.plasmodb.org/plasmo.qa"


async def test_closing_every_client_builds_a_new_one_on_next_use() -> None:
    first = get_jbrowse_client("plasmodb")
    await close_all_jbrowse_clients()
    assert get_jbrowse_client("plasmodb") is not first
