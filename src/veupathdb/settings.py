"""The settings the client reads, and where it reads them from."""

from collections.abc import Callable
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class VEuPathDBSettings(BaseSettings):
    """What the client needs to reach a site.

    A host application extends this class with its own settings and installs
    the extended instance through ``use_veupathdb_settings_source``.
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        case_sensitive=False,
        env_ignore_empty=True,
        extra="ignore",
    )

    veupathdb_sites_config: str | None = Field(
        default=None,
        description="Optional path to a YAML file for site list and base URLs; defaults to bundled sites.yaml if unset.",
    )
    veupathdb_auth_token: str | None = Field(default=None, repr=False)


@lru_cache
def _default_settings() -> VEuPathDBSettings:
    return VEuPathDBSettings()


class _SettingsSource:
    """Where the client reads its settings. The host may replace it once."""

    def __init__(self) -> None:
        self._read: Callable[[], VEuPathDBSettings] = _default_settings

    def use(self, read: Callable[[], VEuPathDBSettings]) -> None:
        self._read = read

    def read(self) -> VEuPathDBSettings:
        return self._read()


_source = _SettingsSource()


def use_veupathdb_settings_source(read: Callable[[], VEuPathDBSettings]) -> None:
    """Read settings from the host application instead of the environment."""
    _source.use(read)


def get_veupathdb_settings() -> VEuPathDBSettings:
    """The settings in force for this process."""
    return _source.read()
