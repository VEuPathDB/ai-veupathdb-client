"""What a link into a configured site's web app shows, read from its route."""

from __future__ import annotations

import re
from typing import Annotated, Literal
from urllib.parse import parse_qsl, unquote, urlsplit

from pydantic import ConfigDict, Discriminator, Field

from veupathdb.model import CamelModel
from veupathdb.wdk.factory import list_sites

_PARAM_PREFIX = "param."
_TRAILING = ".,;:!?)]}>'\""
_SEARCH_ROUTE = re.compile(r"^/search/(?P<record_type>[^/]+)/(?P<search>[^/]+)$")
_RESULT_ROUTE = re.compile(r"^/search/(?P<record_type>[^/]+)/(?P<search>[^/]+)/result$")
_RECORD_ROUTE = re.compile(r"^/record/(?P<record_type>[^/]+)/(?P<key>.+)$")
_STRATEGY_ROUTE = re.compile(
    r"^/workspace/strategies/(?P<strategy>\d+)(?:/(?P<step>\d+))?$"
)
_IMPORT_ROUTE = re.compile(r"^/import/(?P<signature>[^/]+)$")


class _Link(CamelModel):
    model_config = ConfigDict(frozen=True)

    site_id: str


class SearchResultLink(_Link):
    """The result page of one search, run with the parameters the link carries."""

    kind: Literal["search_result"] = "search_result"
    record_type: str
    search_name: str
    parameters: dict[str, str] = Field(default_factory=dict)


class SearchFormLink(_Link):
    """The form of one search, filled with the parameters the link carries."""

    kind: Literal["search_form"] = "search_form"
    record_type: str
    search_name: str
    parameters: dict[str, str] = Field(default_factory=dict)


class RecordLink(_Link):
    """The page of one record."""

    kind: Literal["record"] = "record"
    record_type: str
    primary_key: list[str]


class StrategyLink(_Link):
    """One strategy in the workspace, and the step the link opens."""

    kind: Literal["strategy"] = "strategy"
    strategy_id: int
    step_id: int | None = None


class ImportLink(_Link):
    """A strategy shared by its signature."""

    kind: Literal["import"] = "import"
    signature: str


class OtherPageLink(_Link):
    """A page of the site that shows no search, record or strategy."""

    kind: Literal["other_page"] = "other_page"
    path: str


type SiteLink = Annotated[
    SearchResultLink
    | SearchFormLink
    | RecordLink
    | StrategyLink
    | ImportLink
    | OtherPageLink,
    Discriminator("kind"),
]


def _without_scheme(url: str) -> str:
    return re.sub(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", "", url)


def _app_roots() -> list[tuple[str, str]]:
    """Each configured site's web app root, with no scheme and a lowercase host."""
    roots = []
    for site in list_sites():
        host, _, path = _without_scheme(site.web_base_url).partition("/")
        roots.append((site.id, f"{host.lower()}/{path}/app"))
    return roots


def _parameters(query: str) -> dict[str, str]:
    return {
        key.removeprefix(_PARAM_PREFIX): value
        for key, value in parse_qsl(query, keep_blank_values=True)
        if key.startswith(_PARAM_PREFIX)
    }


def _route(site_id: str, path: str, query: str) -> SiteLink:
    if found := _RESULT_ROUTE.match(path):
        return SearchResultLink(
            site_id=site_id,
            record_type=unquote(found["record_type"]),
            search_name=unquote(found["search"]),
            parameters=_parameters(query),
        )
    if found := _SEARCH_ROUTE.match(path):
        return SearchFormLink(
            site_id=site_id,
            record_type=unquote(found["record_type"]),
            search_name=unquote(found["search"]),
            parameters=_parameters(query),
        )
    if found := _RECORD_ROUTE.match(path):
        return RecordLink(
            site_id=site_id,
            record_type=unquote(found["record_type"]),
            primary_key=[unquote(part) for part in found["key"].split("/") if part],
        )
    if found := _STRATEGY_ROUTE.match(path):
        return StrategyLink(
            site_id=site_id,
            strategy_id=int(found["strategy"]),
            step_id=int(found["step"]) if found["step"] else None,
        )
    if found := _IMPORT_ROUTE.match(path):
        return ImportLink(site_id=site_id, signature=unquote(found["signature"]))
    return OtherPageLink(site_id=site_id, path=path)


def parse_site_link(url: str) -> SiteLink | None:
    """What the link shows, or None when no configured site's web app holds it."""
    bare = _without_scheme(url.strip())
    host, _, rest = bare.partition("/")
    located = f"{host.lower()}/{rest}"
    for site_id, root in _app_roots():
        if located == root or located.startswith((f"{root}/", f"{root}?")):
            parts = urlsplit(located[len(root) :])
            path = parts.path.rstrip("/") or "/"
            return _route(site_id, path, parts.query)
    return None


def find_site_links(text: str) -> list[str]:
    """The links into configured sites' web apps that the text holds, in order."""
    found: list[str] = []
    for token in text.split():
        candidate = token.strip("(<[{'\"").rstrip(_TRAILING)
        if candidate not in found and parse_site_link(candidate) is not None:
            found.append(candidate)
    return found
