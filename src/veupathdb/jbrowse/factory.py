"""The per-site JBrowse clients."""

from __future__ import annotations

import threading

from veupathdb.jbrowse.client import JBrowseClient
from veupathdb.wdk.factory import get_site
from veupathdb.wdk.site_router import on_site_router_reset

_clients: dict[str, JBrowseClient] = {}
_lock = threading.Lock()

on_site_router_reset(_clients.clear)


def get_jbrowse_client(site_id: str) -> JBrowseClient:
    if site_id in _clients:
        return _clients[site_id]
    with _lock:
        if site_id not in _clients:
            _clients[site_id] = JBrowseClient(base_url=get_site(site_id).web_base_url)
        return _clients[site_id]


async def close_all_jbrowse_clients() -> None:
    for client in _clients.values():
        await client.close()
    _clients.clear()
