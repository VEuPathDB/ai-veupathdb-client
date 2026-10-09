"""Where the client reads its settings, and the site list a deployment names."""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest

from veupathdb.settings import (
    DEFAULT_OAUTH_URL,
    VEuPathDBSettings,
    get_veupathdb_settings,
    use_veupathdb_settings_source,
    veupathdb_settings_source,
)
from veupathdb.wdk.site_router import load_sites_config, reset_site_router

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
    reset_site_router()


def test_the_host_settings_serve_the_client() -> None:
    installed = VEuPathDBSettings(veupathdb_auth_token="a-service-token")
    use_veupathdb_settings_source(lambda: installed)

    assert get_veupathdb_settings() is installed


def test_the_installed_source_is_read_back_and_restored() -> None:
    """A host that swaps the source puts back the callable that was there."""
    previous = veupathdb_settings_source()
    installed = VEuPathDBSettings(veupathdb_auth_token="a-service-token")
    use_veupathdb_settings_source(lambda: installed)
    use_veupathdb_settings_source(previous)

    assert veupathdb_settings_source() is previous
    assert get_veupathdb_settings() is not installed


def test_a_named_path_is_the_site_list(named_config: Path) -> None:
    config = load_sites_config(str(named_config))

    assert set(config.sites) == {"demodb"}
    assert config.default_site == "demodb"
    assert config.routing.portal_timeout == 11.0


def test_the_oauth_server_that_signs_bearer_tokens_has_a_default() -> None:
    """One OAuth server signs every site's token, and the client validates against it."""
    assert VEuPathDBSettings().veupathdb_oauth_url == DEFAULT_OAUTH_URL


def test_the_oauth_server_is_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VEUPATHDB_OAUTH_URL", "https://auth.example/oauth")

    assert VEuPathDBSettings().veupathdb_oauth_url == "https://auth.example/oauth"


def test_a_blank_oauth_url_reads_as_the_default(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``env_ignore_empty=True`` is what turns a blank variable into the default."""
    monkeypatch.setenv("VEUPATHDB_OAUTH_URL", "")

    assert VEuPathDBSettings().veupathdb_oauth_url == DEFAULT_OAUTH_URL
