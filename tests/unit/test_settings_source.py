"""Where the client reads its settings, and where the bundled sites.yaml comes from."""

from __future__ import annotations

from collections.abc import Generator
from importlib.resources import files
from pathlib import Path

import pytest

from veupathdb.settings import (
    VEuPathDBSettings,
    get_veupathdb_settings,
    use_veupathdb_settings_source,
)
from veupathdb.wdk.site_router import load_sites_config

_ONE_SITE = """
sites:
  demodb:
    name: DemoDB
    display_name: DemoDB
    base_url: https://demodb.example/demo/service
    project_id: DemoDB
default_site: demodb
routing:
  portal_timeout: 11
  component_timeout: 7
"""


@pytest.fixture
def named_config(tmp_path: Path) -> Generator[Path]:
    path = tmp_path / "sites.yaml"
    path.write_text(_ONE_SITE)
    yield path
    load_sites_config.cache_clear()


def test_the_host_settings_serve_the_client() -> None:
    installed = VEuPathDBSettings(veupathdb_auth_token="a-service-token")
    use_veupathdb_settings_source(lambda: installed)

    assert get_veupathdb_settings() is installed


def test_the_bundled_sites_file_ships_inside_the_package() -> None:
    bundled = files("veupathdb") / "sites.yaml"

    assert bundled.is_file()
    assert "plasmodb" in bundled.read_text()


def test_no_path_selects_the_bundled_twelve_sites() -> None:
    config = load_sites_config(None)

    assert "plasmodb" in config.sites
    assert config.routing.portal_timeout == 120.0
    assert config.routing.component_timeout == 30.0


def test_a_named_path_replaces_the_bundled_list(named_config: Path) -> None:
    config = load_sites_config(str(named_config))

    assert set(config.sites) == {"demodb"}
    assert config.default_site == "demodb"
    assert config.routing.portal_timeout == 11.0


def test_a_blank_path_is_not_a_path(named_config: Path) -> None:
    """An unset environment variable arrives as an empty string, not as None."""
    del named_config

    assert "plasmodb" in load_sites_config("   ").sites
