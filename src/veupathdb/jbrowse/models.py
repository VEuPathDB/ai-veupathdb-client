"""The JBrowse track configuration a site serves for one organism."""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlsplit

from pydantic import ConfigDict, Field, JsonValue

from veupathdb.model import CamelModel


class TrackConfig(CamelModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    label: str = ""
    key: str = ""
    store_class: str = ""
    url_template: str = ""
    metadata: dict[str, JsonValue] = Field(default_factory=dict)

    @property
    def data_path(self) -> str:
        parts = urlsplit(self.url_template)
        data = parse_qs(parts.query).get("data", [])
        return data[0] if data else unquote(parts.path)


class TrackList(CamelModel):
    model_config = ConfigDict(extra="ignore", frozen=True)

    tracks: list[TrackConfig] = Field(default_factory=list)
