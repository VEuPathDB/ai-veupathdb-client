"""Integration entrypoints for WDK clients and services."""

import threading

from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.site_router import SiteInfo, get_site_router, on_site_router_reset
from veupathdb.wdk.strategy_api.api import StrategyAPI
from veupathdb.wdk.temporary_results import TemporaryResultsAPI
from veupathdb.wdk.vdi.client import VdiClient

_vdi_clients: dict[str, VdiClient] = {}
_vdi_lock = threading.Lock()

on_site_router_reset(_vdi_clients.clear)


def get_wdk_client(site_id: str) -> VEuPathDBClient:
    """Get a raw WDK client for a site.

    :param site_id: VEuPathDB site identifier.

    """
    router = get_site_router()
    return router.get_client(site_id)


def get_site(site_id: str) -> SiteInfo:
    """Get site metadata by ID.

    :param site_id: VEuPathDB site identifier.

    """
    router = get_site_router()
    return router.get_site(site_id)


def list_sites() -> list[SiteInfo]:
    """List all known sites."""
    router = get_site_router()
    return router.list_sites()


def get_strategy_api(site_id: str) -> StrategyAPI:
    """Get a Strategy API wrapper for a site.

    :param site_id: VEuPathDB site identifier.

    """
    return StrategyAPI(get_wdk_client(site_id))


def get_results_api(site_id: str) -> TemporaryResultsAPI:
    """Get a temporary results API wrapper for a site.

    :param site_id: VEuPathDB site identifier.

    """
    return TemporaryResultsAPI(get_wdk_client(site_id))


def get_vdi_client(site_id: str) -> VdiClient:
    """Get the user-dataset client for a site and create it on first use.

    :param site_id: VEuPathDB site identifier.

    """
    if site_id in _vdi_clients:
        return _vdi_clients[site_id]
    with _vdi_lock:
        if site_id not in _vdi_clients:
            _vdi_clients[site_id] = VdiClient(base_url=get_site(site_id).vdi_base_url)
        return _vdi_clients[site_id]


async def close_all_clients() -> None:
    """Close all cached WDK clients."""
    router = get_site_router()
    await router.close_all()
    for vdi_client in _vdi_clients.values():
        await vdi_client.close()
    _vdi_clients.clear()
