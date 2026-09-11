"""Routes requests to a VEuPathDB portal or component site and owns their clients."""

import threading
from collections.abc import Callable
from functools import lru_cache
from importlib.resources import files
from pathlib import Path
from urllib.parse import urlparse

import yaml
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator

from veupathdb.errors import SiteNotFoundError
from veupathdb.logging import get_logger
from veupathdb.model import CamelModel
from veupathdb.settings import get_veupathdb_settings, on_settings_source_change
from veupathdb.wdk.client import VEuPathDBClient
from veupathdb.wdk.site_search_client import SiteSearchClient

logger = get_logger(__name__)


class SiteConfig(BaseModel):
    """Validated configuration for a single VEuPathDB site."""

    name: str = ""
    display_name: str = ""
    base_url: str = ""
    project_id: str = ""
    is_portal: bool = False


class RoutingConfig(BaseModel):
    """Validated routing/timeout configuration."""

    portal_timeout: float = 120.0
    component_timeout: float = 30.0


class SitesConfig(BaseModel):
    """Top-level sites configuration parsed from YAML."""

    sites: dict[str, SiteConfig] = Field(default_factory=dict)
    default_site: str = "veupathdb"
    routing: RoutingConfig = Field(default_factory=RoutingConfig)


@lru_cache
def load_sites_config(config_path: str | None = None) -> SitesConfig:
    """Loads and validates the sites configuration from YAML. An empty path selects
    the sites.yaml bundled with this package."""
    named = config_path.strip() if config_path else ""
    source = files("veupathdb") / "sites.yaml" if not named else Path(named).resolve()
    logger.info("Loading sites config", path=str(source))
    raw = yaml.safe_load(source.read_text())
    if not isinstance(raw, dict):
        logger.warning("Sites config is not a dict, using defaults")
        return SitesConfig()
    config = SitesConfig.model_validate(raw)
    logger.info("Sites config loaded", num_sites=len(config.sites))
    return config


class SiteInfo(CamelModel):
    """VEuPathDB site information."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(validation_alias=AliasChoices("id", "site_id"))
    name: str
    display_name: str
    base_url: str
    project_id: str
    is_portal: bool

    @field_validator("base_url", mode="before")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        return v.rstrip("/") if isinstance(v, str) else v

    @classmethod
    def from_config(cls, site_id: str, cfg: SiteConfig) -> SiteInfo:
        """Builds a SiteInfo from a validated SiteConfig."""
        return cls(
            id=site_id,
            name=cfg.name,
            display_name=cfg.display_name,
            base_url=cfg.base_url,
            project_id=cfg.project_id,
            is_portal=cfg.is_portal,
        )

    @property
    def service_url(self) -> str:
        """Returns the WDK service URL, which the configured base URL already holds."""
        return self.base_url

    @property
    def web_base_url(self) -> str:
        """Returns the web UI base URL without the service suffix."""
        return self.base_url.removesuffix("/service")

    @property
    def site_origin(self) -> str:
        """Returns the site origin, which is the scheme and host with no path.
        Site search lives at the origin, not under the WDK service prefix.
        """
        parsed = urlparse(self.base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def eda_base_url(self) -> str:
        """Returns the EDA service URL, which lives at the site origin."""
        return f"{self.site_origin}/eda"

    @property
    def vdi_base_url(self) -> str:
        """Returns the user-dataset service URL, which lives at the site origin."""
        return f"{self.site_origin}/vdi"

    def dataset_url(self, vdi_id: str) -> str:
        """Builds the web UI URL of one published user dataset."""
        return f"{self.web_base_url}/app/workspace/datasets/{vdi_id}"

    def strategy_url(self, strategy_id: int, root_step_id: int | None = None) -> str:
        """Builds a strategy URL for the web UI."""
        if root_step_id is not None:
            return f"{self.web_base_url}/app/workspace/strategies/{strategy_id}/{root_step_id}"
        return f"{self.web_base_url}/app/workspace/strategies/{strategy_id}"


class SiteRouter:
    """Selects a VEuPathDB site and owns the client for each one."""

    def __init__(self) -> None:
        settings = get_veupathdb_settings()
        self._config = load_sites_config(settings.veupathdb_sites_config)
        self._sites: dict[str, SiteInfo] = {}
        self._clients: dict[str, VEuPathDBClient] = {}
        self._site_search_clients: dict[str, SiteSearchClient] = {}
        self._client_lock = threading.Lock()
        self._load_sites()

    def _load_sites(self) -> None:
        """Loads the site configurations from the validated config."""
        logger.info("Loading sites", count=len(self._config.sites))
        for site_id, site_cfg in self._config.sites.items():
            self._sites[site_id] = SiteInfo.from_config(site_id, site_cfg)
        logger.info("Sites loaded", site_ids=list(self._sites.keys()))

    def get_site(self, site_id: str) -> SiteInfo:
        """Returns the site with this identifier."""
        logger.debug(
            "Getting site", site_id=site_id, available=list(self._sites.keys())
        )
        if site_id not in self._sites:
            raise SiteNotFoundError(site_id, list(self._sites))
        return self._sites[site_id]

    def list_sites(self) -> list[SiteInfo]:
        """Returns every available site."""
        return list(self._sites.values())

    def get_client(self, site_id: str) -> VEuPathDBClient:
        """Returns the HTTP client for a site and creates it on first use."""
        if site_id in self._clients:
            return self._clients[site_id]
        with self._client_lock:
            if site_id not in self._clients:
                site = self.get_site(site_id)
                routing = self._config.routing
                timeout = (
                    routing.portal_timeout
                    if site.is_portal
                    else routing.component_timeout
                )
                self._clients[site_id] = VEuPathDBClient(
                    base_url=site.service_url,
                    timeout=float(timeout),
                )
            return self._clients[site_id]

    def get_site_search_client(self, site_id: str) -> SiteSearchClient:
        """Returns the site search client for a site and creates it on first use.
        Site search is a separate service that lives at the site origin URL.
        """
        if site_id in self._site_search_clients:
            return self._site_search_clients[site_id]
        with self._client_lock:
            if site_id not in self._site_search_clients:
                site = self.get_site(site_id)
                self._site_search_clients[site_id] = SiteSearchClient(
                    base_url=site.site_origin,
                    project_id=site.project_id,
                    timeout=float(self._config.routing.component_timeout),
                )
            return self._site_search_clients[site_id]

    async def close_all(self) -> None:
        """Closes every HTTP client."""
        for wdk_client in self._clients.values():
            await wdk_client.close()
        self._clients.clear()
        for ss_client in self._site_search_clients.values():
            await ss_client.close()
        self._site_search_clients.clear()


_router_holder: dict[str, SiteRouter] = {}
_router_lock = threading.Lock()
_per_site_caches: list[Callable[[], None]] = []


def on_site_router_reset(drop: Callable[[], None]) -> None:
    """Register a per-site client cache the reset drops with the router."""
    _per_site_caches.append(drop)


def reset_site_router() -> None:
    """Drop the router, the cached sites config and every per-site client cache.

    A client already handed out keeps working. Call ``close_all_clients`` and
    ``close_all_eda_clients`` first to release the sockets they hold.
    """
    _router_holder.clear()
    load_sites_config.cache_clear()
    for drop in _per_site_caches:
        drop()


on_settings_source_change(reset_site_router)


def get_site_router() -> SiteRouter:
    """Returns the process-wide site router."""
    if "v" in _router_holder:
        return _router_holder["v"]
    with _router_lock:
        if "v" not in _router_holder:
            _router_holder["v"] = SiteRouter()
        return _router_holder["v"]
