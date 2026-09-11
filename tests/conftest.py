"""The hermetic lane's shared state: the process-wide caches a test must not inherit."""

from collections.abc import Generator

import pytest

from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.wdk import forget_signing_keys


@pytest.fixture(autouse=True)
def _library_defaults() -> Generator[None]:
    """Read the bundled sites.yaml, carry no service token, cache no signing key.

    Installing the source drops the router and the sites config built from the
    previous one.
    """
    settings = VEuPathDBSettings(veupathdb_sites_config=None, veupathdb_auth_token=None)
    use_veupathdb_settings_source(lambda: settings)
    forget_signing_keys()
    yield
    forget_signing_keys()
    use_veupathdb_settings_source(VEuPathDBSettings)
