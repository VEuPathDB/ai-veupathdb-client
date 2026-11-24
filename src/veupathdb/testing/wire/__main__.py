from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from veupathdb.settings import DEFAULT_OAUTH_URL, user_agent_header
from veupathdb.testing.wire.addon import WireAddon, site_hosts
from veupathdb.testing.wire.drift import render_report
from veupathdb.testing.wire.merge import merge
from veupathdb.testing.wire.refresh import WdkSession, refresh
from veupathdb.testing.wire.serve import serve
from veupathdb.testing.wire.store import WireStore
from veupathdb.wdk.site_router import load_sites_config

_TIMEOUT_SECONDS = 300.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m veupathdb.testing.wire")
    commands = parser.add_subparsers(dest="command", required=True)
    serving = commands.add_parser("serve")
    serving.add_argument("--mode", choices=["replay", "record"], required=True)
    serving.add_argument("--wire", type=Path, required=True)
    serving.add_argument("--sites", type=Path, required=True)
    serving.add_argument("--host", required=True)
    serving.add_argument("--port", type=int, default=8080)
    serving.add_argument("--confdir", type=Path, required=True)
    serving.add_argument("--oauth-url", default=DEFAULT_OAUTH_URL)
    refreshing = commands.add_parser("refresh")
    refreshing.add_argument("wire", type=Path)
    refreshing.add_argument("--sites", type=Path, required=True)
    refreshing.add_argument("--report", type=Path, required=True)
    refreshing.add_argument("--login-site", default="plasmodb")
    merging = commands.add_parser("merge")
    merging.add_argument("source", type=Path)
    merging.add_argument("target", type=Path)
    return parser


async def _refresh(args: argparse.Namespace, email: str, password: str) -> int:
    config = load_sites_config(str(args.sites))
    services = {
        urlsplit(site.base_url).hostname or "": site.base_url
        for site in config.sites.values()
    }
    login = urlsplit(config.sites[args.login_site].base_url).hostname or ""
    async with httpx.AsyncClient(
        timeout=_TIMEOUT_SECONDS, headers=user_agent_header()
    ) as client:
        result = await refresh(
            args.wire, WdkSession(services, client), email, password, login
        )
    args.report.write_text(render_report(result.rows, result.builds, result.errors))
    sys.stdout.write(f"refresh report: {args.report}\n")
    return 1 if result.errors else 0


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    match args.command:
        case "serve":
            addon = WireAddon(
                args.mode,
                WireStore(args.wire),
                site_hosts(args.sites),
                oauth_url=args.oauth_url,
            )
            serve(addon, host=args.host, port=args.port, confdir=args.confdir)
        case "refresh":
            email = os.environ.get("WDK_TEST_EMAIL", "")
            password = os.environ.get("WDK_TEST_PASSWORD", "")
            if not email or not password:
                msg = "export WDK_TEST_EMAIL and WDK_TEST_PASSWORD to refresh"
                raise SystemExit(msg)
            code = asyncio.run(_refresh(args, email, password))
            if code:
                raise SystemExit(code)
        case _:
            merge(args.source, args.target)


if __name__ == "__main__":
    main()
