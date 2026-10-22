"""The JBrowse track configuration a site serves for one organism."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import ConfigDict, Field, JsonValue

from veupathdb.model import CamelModel

TABIX_STORE_SUFFIX = "GFF3Tabix"
BIGWIG_STORE_SUFFIX = "BigWig"
TABIX_INDEX_SUFFIX = ".tbi"


def store_data_path(url: str) -> str:
    parts = urlsplit(url)
    data = parse_qs(parts.query).get("data", [])
    return data[0] if data else unquote(parts.path)


class SubTrack(CamelModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    url: str
    name: str = ""

    @property
    def data_path(self) -> str:
        return store_data_path(self.url)


class TrackConfig(CamelModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str = ""
    key: str = ""
    store_class: str = ""
    url_template: str = ""
    url_templates: list[SubTrack] = Field(default_factory=list)
    tbi_url_template: str = ""
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def data_path(self) -> str:
        return store_data_path(self.url_template)

    @property
    def index_path(self) -> str:
        if self.tbi_url_template:
            return store_data_path(self.tbi_url_template)
        return self.data_path + TABIX_INDEX_SUFFIX

    @property
    def reads_with_tabix(self) -> bool:
        return self.store_class.endswith(TABIX_STORE_SUFFIX)

    @property
    def reads_with_bigwig(self) -> bool:
        return self.store_class.endswith(BIGWIG_STORE_SUFFIX)

    def subtracks(self) -> list[SubTrack]:
        if self.url_templates:
            return list(self.url_templates)
        if self.url_template:
            return [SubTrack(url=self.url_template, name=self.key or self.label)]
        return []


class TrackList(CamelModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    tracks: list[TrackConfig] = Field(default_factory=list)
