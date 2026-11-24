from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path
from typing import cast

from mitmproxy import options
from mitmproxy.tools.dump import DumpMaster

from veupathdb.testing.wire.addon import WireAddon, WireMode, site_hosts
from veupathdb.testing.wire.store import WireStore


def proxy_master(addon: WireAddon, host: str, port: int, confdir: Path) -> DumpMaster:
    opts = options.Options(listen_host=host, listen_port=port, confdir=str(confdir))
    master = DumpMaster(opts, with_termlog=True, with_dumper=False)
    if addon.mode == "replay":
        master.options.connection_strategy = "lazy"
        master.options.upstream_cert = False
    cast("Callable[[WireAddon], None]", master.addons.add)(addon)
    return master


async def _run(addon: WireAddon, host: str, port: int, confdir: Path) -> None:
    await proxy_master(addon, host, port, confdir).run()


def serve(
    mode: WireMode, wire: Path, sites: Path, *, host: str, port: int, confdir: Path
) -> None:
    addon = WireAddon(mode, WireStore(wire), site_hosts(sites))
    asyncio.run(_run(addon, host, port, confdir))
