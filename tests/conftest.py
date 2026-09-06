"""The hermetic lane's shared state: the process-wide caches a test must not inherit."""

from collections.abc import Generator

import pytest

from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.wdk import auth_login
from veupathdb.wdk.site_router import load_sites_config


@pytest.fixture(autouse=True)
def _library_defaults() -> Generator[None]:
    """Read the bundled sites.yaml, carry no service token, cache no signing key."""
    settings = VEuPathDBSettings(veupathdb_sites_config=None, veupathdb_auth_token=None)
    use_veupathdb_settings_source(lambda: settings)
    load_sites_config.cache_clear()
    auth_login._signing_keys.clear()
    yield
    auth_login._signing_keys.clear()
    load_sites_config.cache_clear()
    use_veupathdb_settings_source(VEuPathDBSettings)
