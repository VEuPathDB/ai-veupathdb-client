import asyncio
import socket
import ssl
import threading
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from mitmproxy.tools.dump import DumpMaster

from veupathdb.testing import QA_SITES_FILE
from veupathdb.testing.wire import Cassette, CassetteHeader, Exchange, WireStore
from veupathdb.testing.wire.addon import WireAddon, site_hosts
from veupathdb.testing.wire.serve import proxy_master

HOST = "qa.plasmodb.org"
RECORDED = "/plasmo.qa/service/record-types"
START_SECONDS = 30.0


def _free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@pytest.fixture
def proxy(tmp_path: Path) -> Iterator[tuple[str, ssl.SSLContext]]:
    store = WireStore(tmp_path / "wire")
    store.write_cassette(
        Cassette(
            header=CassetteHeader(cassette="stack", recorded_at=datetime.now(UTC)),
            exchanges=[
                Exchange(
                    seq=0,
                    host=HOST,
                    method="GET",
                    path=RECORDED,
                    credential="none",
                    epoch=0,
                    status=200,
                    content_type="application/json",
                    response=store.put_body(b'[{"urlSegment": "gene"}]'),
                )
            ],
        )
    )
    port = _free_port()
    confdir = tmp_path / "ca"
    addon = WireAddon("replay", store, site_hosts(QA_SITES_FILE))
    held: list[tuple[asyncio.AbstractEventLoop, DumpMaster]] = []

    async def run() -> None:
        master = proxy_master(addon, "127.0.0.1", port, confdir)
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
        yield url, ssl.create_default_context(cafile=confdir / "mitmproxy-ca-cert.pem")
    finally:
        loop, master = held[0]
        loop.call_soon_threadsafe(master.shutdown)
        thread.join(timeout=10)


def test_the_proxy_replays_a_recording_and_refuses_the_rest(
    proxy: tuple[str, ssl.SSLContext],
) -> None:
    url, trust = proxy
    with httpx.Client(proxy=url, verify=trust) as client:
        recorded = client.get(f"https://{HOST}{RECORDED}")
        unrecorded = client.get(f"https://{HOST}/plasmo.qa/service/never-recorded")

    assert recorded.status_code == 200
    assert recorded.json() == [{"urlSegment": "gene"}]
    assert unrecorded.status_code == 418
    assert unrecorded.headers["x-wire-miss"] == "1"
    assert unrecorded.json()["path"] == "/plasmo.qa/service/never-recorded"
