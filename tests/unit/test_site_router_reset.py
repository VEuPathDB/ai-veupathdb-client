"""Installing a settings source drops what was built from the previous one."""

from __future__ import annotations

from pathlib import Path

from veupathdb.eda.factory import get_eda_client
from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.wdk.factory import get_vdi_client, get_wdk_client, list_sites
from veupathdb.wdk.site_router import reset_site_router

_DEMO = """
sites:
  demodb:
    name: DemoDB
    display_name: DemoDB
    base_url: https://demodb.example/demo/service
    project_id: DemoDB
default_site: demodb
"""

_OTHER = """
sites:
  otherdb:
    name: OtherDB
    display_name: OtherDB
    base_url: https://otherdb.example/other/service
    project_id: OtherDB
default_site: otherdb
"""


def _install(path: Path, body: str) -> None:
    path.write_text(body)
    installed = VEuPathDBSettings(veupathdb_sites_config=str(path))
    use_veupathdb_settings_source(lambda: installed)


def test_a_source_installed_after_the_first_call_serves_its_own_site_list(
    tmp_path: Path,
) -> None:
    _install(tmp_path / "first.yaml", _DEMO)
    assert [site.id for site in list_sites()] == ["demodb"]

    _install(tmp_path / "second.yaml", _OTHER)

    assert [site.id for site in list_sites()] == ["otherdb"]


def test_the_reset_drops_the_wdk_eda_and_vdi_clients(tmp_path: Path) -> None:
    _install(tmp_path / "first.yaml", _DEMO)
    wdk = get_wdk_client("demodb")
    eda = get_eda_client("demodb")
    vdi = get_vdi_client("demodb")

    reset_site_router()

    assert get_wdk_client("demodb") is not wdk
    assert get_eda_client("demodb") is not eda
    assert get_vdi_client("demodb") is not vdi
