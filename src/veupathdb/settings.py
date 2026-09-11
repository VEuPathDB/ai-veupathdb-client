"""The settings the client reads, where it reads them from, and what a change drops."""

from collections.abc import Callable
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_OAUTH_URL = "https://auth.veupathdb.org"
DEFAULT_INTERNAL_STRATEGY_NAME_PREFIX = "__internal__:"


class VEuPathDBSettings(BaseSettings):
    """What the client needs to reach a site.

    A host application extends this class with its own settings and installs
    the extended instance through ``use_veupathdb_settings_source``.

    ``env_ignore_empty=True`` is what makes a variable that is set but blank
    resolve to the field default, so no field needs a validator for that.
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
    veupathdb_oauth_url: str = Field(
        default=DEFAULT_OAUTH_URL,
        description="The OAuth server that signs VEuPathDB bearer tokens. One server serves every site.",
    )
    veupathdb_internal_strategy_name_prefix: str = Field(
        default=DEFAULT_INTERNAL_STRATEGY_NAME_PREFIX,
        description="Prefix that tags a helper strategy this deployment created. It is written into a real VEuPathDB account, so a deployment states its own.",
    )


@lru_cache
def _default_settings() -> VEuPathDBSettings:
    return VEuPathDBSettings()


class _SettingsSource:
    """Where the client reads its settings. The host may replace it once."""

    def __init__(self) -> None:
        self._read: Callable[[], VEuPathDBSettings] = _default_settings

    def use(self, read: Callable[[], VEuPathDBSettings]) -> None:
        self._read = read

    def source(self) -> Callable[[], VEuPathDBSettings]:
        return self._read

    def read(self) -> VEuPathDBSettings:
        return self._read()


_source = _SettingsSource()
_invalidators: list[Callable[[], None]] = []


def on_settings_source_change(invalidate: Callable[[], None]) -> None:
    """Register a cache built from settings. Installing a source drops it."""
    _invalidators.append(invalidate)


def use_veupathdb_settings_source(read: Callable[[], VEuPathDBSettings]) -> None:
    """Read settings from the host application instead of the environment.

    Every cache built from the previous source is dropped, so a source may be
    installed at any point in the process.
    """
    _source.use(read)
    for invalidate in _invalidators:
        invalidate()


def veupathdb_settings_source() -> Callable[[], VEuPathDBSettings]:
    """The callable this process reads settings through."""
    return _source.source()


def get_veupathdb_settings() -> VEuPathDBSettings:
    """The settings in force for this process."""
    return _source.read()
