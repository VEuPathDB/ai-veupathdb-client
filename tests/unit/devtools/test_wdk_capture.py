from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx

from veupathdb.devtools.wdk_capture import WDKExchange, is_wdk_host, wdk_record
from veupathdb.wdk.site_router import load_sites_config


def test_every_configured_site_host_is_a_wdk_host() -> None:
    hosts = [
        urlparse(site.base_url).hostname for site in load_sites_config().sites.values()
    ]
    assert "orthomcl.org" in hosts
    assert all(host is not None and is_wdk_host(host) for host in hosts)


def test_is_wdk_host_matches_veupath_sites() -> None:
    assert is_wdk_host("vectorbase.org")
    assert is_wdk_host("plasmodb.org")
    assert is_wdk_host("www.toxodb.org")
    assert not is_wdk_host("api.openai.com")
    assert not is_wdk_host("example.com")


def test_wdk_record_captures_request_and_response() -> None:
    request = httpx.Request(
        "POST",
        "https://vectorbase.org/vectorbase/service/record-types/transcript/searches/GenesByText",
        json={"searchConfig": {"parameters": {"text_expression": "obp"}}},
    )
    rec = wdk_record(
        request=request,
        status=200,
        request_body=request.content,
        response_body=b'{"recordCount": 42}',
        ms=123.4,
    )
    assert rec.method == "POST"
    assert rec.status == 200
    assert "GenesByText" in rec.url
    assert rec.request_json == {
        "searchConfig": {"parameters": {"text_expression": "obp"}}
    }
    assert rec.response_json == {"recordCount": 42}


def test_wdk_record_keeps_raw_when_not_json() -> None:
    request = httpx.Request("GET", "https://plasmodb.org/plasmo/service/x")
    rec = wdk_record(
        request=request,
        status=500,
        request_body=b"",
        response_body=b"<html>boom</html>",
        ms=5.0,
    )
    assert rec.response_json is None
    assert rec.response_text == "<html>boom</html>"


def test_exchange_filename_is_safe_and_ordered() -> None:
    request = httpx.Request(
        "POST", "https://vectorbase.org/x/service/searches/GenesByText"
    )
    rec = wdk_record(
        request=request, status=200, request_body=b"", response_body=b"{}", ms=1.0
    )
    name = rec.filename(7)
    assert name.startswith("07-")
    assert name.endswith(".json")
    assert "/" not in name


def test_exchange_roundtrips_to_disk(tmp_path: Path) -> None:
    request = httpx.Request("GET", "https://toxodb.org/toxo/service/x")
    rec = wdk_record(
        request=request,
        status=200,
        request_body=b"",
        response_body=b'{"ok":true}',
        ms=1.0,
    )
    path = tmp_path / rec.filename(1)
    path.write_text(rec.model_dump_json(indent=2))
    loaded = WDKExchange.model_validate_json(path.read_text())
    assert loaded.status == 200
    assert loaded.response_json == {"ok": True}
