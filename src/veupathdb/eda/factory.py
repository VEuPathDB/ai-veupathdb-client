"""Integration entrypoints for the per-site EDA clients."""

from __future__ import annotations

import threading

from veupathdb.eda.analyses import EdaAnalysesClient
from veupathdb.eda.client import EdaClient
from veupathdb.wdk.factory import get_site
from veupathdb.wdk.site_router import on_site_router_reset

_clients: dict[str, EdaClient] = {}
_lock = threading.Lock()

on_site_router_reset(_clients.clear)


def get_eda_client(site_id: str) -> EdaClient:
    """The EDA client for a site, created on first use."""
    if site_id in _clients:
        return _clients[site_id]
    with _lock:
        if site_id not in _clients:
            site = get_site(site_id)
            _clients[site_id] = EdaClient(base_url=site.eda_base_url)
        return _clients[site_id]


def get_eda_analyses_client(site_id: str) -> EdaAnalysesClient:
    """The analysis store for a site, keyed by that site's project id."""
    site = get_site(site_id)
    return EdaAnalysesClient(
        client=get_eda_client(site_id),
        project_id=site.project_id,
    )


async def close_all_eda_clients() -> None:
    """Close every cached EDA client."""
    for client in _clients.values():
        await client.close()
    _clients.clear()
