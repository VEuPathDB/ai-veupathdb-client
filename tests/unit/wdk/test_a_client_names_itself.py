from __future__ import annotations

from collections.abc import Generator

import pytest

from veupathdb.eda.client import EdaClient
from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.site_router import get_site_router

HOST_AGENT = "PathFinder/9.9.9 (+https://github.com/VEuPathDB/pathfinder-app)"


@pytest.fixture
def host_agent() -> Generator[None]:
    use_veupathdb_settings_source(
        lambda: VEuPathDBSettings(
            veupathdb_user_agent=HOST_AGENT,
            veupathdb_concurrent_searches_per_site=3,
        )
    )
    yield
    use_veupathdb_settings_source(VEuPathDBSettings)


def test_the_default_agent_names_the_library_and_its_version() -> None:
    agent = VEuPathDBSettings().veupathdb_user_agent

    assert agent.startswith("veupathdb-py/")
    assert agent != "veupathdb-py/"


@pytest.mark.usefixtures("host_agent")
async def test_a_wdk_request_carries_the_hosts_agent() -> None:
    client = VEuPathDBClient(base_url="https://example.invalid/service")

    built = await client._get_client()

    assert built.headers["user-agent"] == HOST_AGENT
    await client.close()


@pytest.mark.usefixtures("host_agent")
async def test_an_eda_request_carries_the_hosts_agent() -> None:
    client = EdaClient(base_url="https://example.invalid/eda")

    built = await client._http()

    assert built.headers["user-agent"] == HOST_AGENT
    await client.close()


@pytest.mark.usefixtures("host_agent")
def test_a_site_client_takes_the_hosts_search_cap() -> None:
    client = get_site_router().get_client("plasmodb")

    assert client.concurrent_searches == 3


def test_a_client_holds_far_fewer_connections_than_before() -> None:
    client = VEuPathDBClient(base_url="https://example.invalid/service")

    assert client.max_connections <= 100
