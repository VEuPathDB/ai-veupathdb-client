"""The hermetic lane's shared state: the process-wide caches a test must not inherit."""

from collections.abc import Generator

import pytest

from veupathdb.settings import VEuPathDBSettings, use_veupathdb_settings_source
from veupathdb.testing import QA_SITES_FILE
from veupathdb.wdk import forget_signing_keys


@pytest.fixture(autouse=True)
def _library_defaults(monkeypatch: pytest.MonkeyPatch) -> Generator[None]:
    """Read the QA site list, carry no service token, cache no signing key.

    The environment names the QA list too, so a test that builds its own
    settings reads it. Installing the source drops the router and the sites
    config built from the previous one.
    """
    monkeypatch.setenv("VEUPATHDB_SITES_CONFIG", str(QA_SITES_FILE))
    settings = VEuPathDBSettings(veupathdb_auth_token=None)
    use_veupathdb_settings_source(lambda: settings)
    forget_signing_keys()
    yield
    forget_signing_keys()
    use_veupathdb_settings_source(VEuPathDBSettings)
