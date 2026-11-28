import asyncio
import socket
import threading
import time
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
import pytest
from mitmproxy.tools.dump import DumpMaster

from veupathdb.testing import QA_SITES_FILE
from veupathdb.testing.wire import WireStore
from veupathdb.testing.wire.addon import WireAddon, site_hosts
from veupathdb.testing.wire.serve import proxy_master

HOST = "qa.plasmodb.org"
PATH = "/plasmo.qa/service/record-types"
START_SECONDS = 30.0


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


_seen: list[str] = []


class _Upstream(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        _seen.append(self.path)
        body = b'[{"urlSegment": "gene"}]'
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def upstream() -> Iterator[str]:
    _seen.clear()
    server = ThreadingHTTPServer(("127.0.0.1", 0), _Upstream)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()
        thread.join(timeout=10)


@pytest.fixture
def recording_proxy(tmp_path: Path, upstream: str) -> Iterator[str]:
    port = _free_port()
    addon = WireAddon("record", WireStore(tmp_path / "wire"), site_hosts(QA_SITES_FILE))
    held: list[tuple[asyncio.AbstractEventLoop, DumpMaster]] = []

    async def run() -> None:
        master = proxy_master(addon, "127.0.0.1", port, tmp_path / "ca", upstream)
        held.append((asyncio.get_running_loop(), master))
        await master.run()

    thread = threading.Thread(target=asyncio.run, args=(run(),), daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + START_SECONDS
    while True:
        try:
            if httpx.get(f"{url}/__wire/health").status_code == 200:
                break
        except httpx.TransportError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.2)
    try:
        yield url
    finally:
        loop, master = held[0]
        loop.call_soon_threadsafe(master.shutdown)
        thread.join(timeout=10)


def test_a_recording_proxy_reaches_the_site_through_its_upstream(
    recording_proxy: str,
) -> None:
    with httpx.Client(proxy=recording_proxy) as client:
        answered = client.get(f"http://{HOST}{PATH}")

    assert answered.status_code == 200
    assert answered.json() == [{"urlSegment": "gene"}]
    assert _seen == [f"http://{HOST}{PATH}"]


def test_a_replaying_proxy_refuses_an_upstream(tmp_path: Path) -> None:
    addon = WireAddon("replay", WireStore(tmp_path / "wire"), site_hosts(QA_SITES_FILE))

    with pytest.raises(ValueError, match="takes no upstream"):
        proxy_master(
            addon, "127.0.0.1", _free_port(), tmp_path / "ca", "http://127.0.0.1:1"
        )
