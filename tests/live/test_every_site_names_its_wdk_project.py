from __future__ import annotations

import httpx
import pytest

from veupathdb.testing import QA_SITES_FILE
from veupathdb.wdk.site_router import load_sites_config

pytestmark = [pytest.mark.live_wdk, pytest.mark.asyncio]

_SITES = load_sites_config(str(QA_SITES_FILE)).sites


@pytest.mark.parametrize("site_id", sorted(_SITES))
async def test_the_project_id_is_the_one_wdk_reports(site_id: str) -> None:
    site = _SITES[site_id]
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        response = await client.get(site.base_url)

    assert response.json()["projectId"] == site.project_id
