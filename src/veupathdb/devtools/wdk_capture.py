"""Records every WDK httpx round trip of a run into one directory."""

from __future__ import annotations

import json
import re
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from itertools import count
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel

from veupathdb.settings import get_veupathdb_settings
from veupathdb.wdk.site_router import load_sites_config

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _wdk_hosts() -> frozenset[str]:
    """Every host the site registry declares."""
    config = load_sites_config(get_veupathdb_settings().veupathdb_sites_config)
    hosts = (urlparse(site.base_url).hostname for site in config.sites.values())
    return frozenset(host for host in hosts if host)


def is_wdk_host(host: str) -> bool:
    host = host.lower()
    return any(host == known or host.endswith("." + known) for known in _wdk_hosts())


def _maybe_json(body: bytes) -> tuple[dict[str, Any] | None, str | None]:
    text = body.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError, ValueError:
        return None, text
    return (parsed, None) if isinstance(parsed, dict) else (None, text)


class WDKExchange(BaseModel):
    method: str
    url: str
    status: int
    ms: float
    request_json: dict[str, Any] | None = None
    request_text: str | None = None
    response_json: dict[str, Any] | None = None
    response_text: str | None = None

    def filename(self, seq: int) -> str:
        tail = self.url.rsplit("/", 1)[-1].split("?")[0] or "root"
        return f"{seq:02d}-{self.method}-{_SAFE.sub('_', tail)}.json"


def wdk_record(
    *,
    request: httpx.Request,
    status: int,
    request_body: bytes,
    response_body: bytes,
    ms: float,
) -> WDKExchange:
    req_json, req_text = _maybe_json(request_body) if request_body else (None, None)
    resp_json, resp_text = _maybe_json(response_body) if response_body else (None, None)
    return WDKExchange(
        method=request.method,
        url=str(request.url),
        status=status,
        ms=ms,
        request_json=req_json,
        request_text=req_text,
        response_json=resp_json,
        response_text=resp_text,
    )


@asynccontextmanager
async def capture_wdk(run_dir: Path) -> AsyncIterator[None]:
    """Record every WDK httpx round-trip into ``<run_dir>/wdk/`` by injecting
    a response event hook into freshly-constructed ``httpx.AsyncClient``s.
    Scoped: the original ``__init__`` is restored on exit."""

    wdk_dir = run_dir / "wdk"
    wdk_dir.mkdir(parents=True, exist_ok=True)
    seq = count(1)
    original_init = httpx.AsyncClient.__init__

    async def on_response(response: httpx.Response) -> None:
        if not is_wdk_host(response.request.url.host):
            return
        started = response.request.extensions.get("_wdk_start", time.perf_counter())
        body = await response.aread()
        rec = wdk_record(
            request=response.request,
            status=response.status_code,
            request_body=response.request.content,
            response_body=body,
            ms=(time.perf_counter() - started) * 1000.0,
        )
        (wdk_dir / rec.filename(next(seq))).write_text(rec.model_dump_json(indent=2))

    def patched_init(self: httpx.AsyncClient, *args: Any, **kwargs: Any) -> None:
        hooks = kwargs.get("event_hooks") or {}
        responses = list(hooks.get("response", []))
        responses.append(on_response)
        hooks["response"] = responses
        kwargs["event_hooks"] = hooks
        original_init(self, *args, **kwargs)

    init_attr = "__init__"
    setattr(httpx.AsyncClient, init_attr, patched_init)
    try:
        yield
    finally:
        setattr(httpx.AsyncClient, init_attr, original_init)
