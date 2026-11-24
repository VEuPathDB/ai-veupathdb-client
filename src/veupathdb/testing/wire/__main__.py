from __future__ import annotations

import argparse
from pathlib import Path

from veupathdb.testing.wire.serve import serve


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m veupathdb.testing.wire")
    commands = parser.add_subparsers(dest="command", required=True)
    serving = commands.add_parser("serve")
    serving.add_argument("--mode", choices=["replay", "record"], required=True)
    serving.add_argument("--wire", type=Path, required=True)
    serving.add_argument("--sites", type=Path, required=True)
    serving.add_argument("--host", required=True)
    serving.add_argument("--port", type=int, default=8080)
    serving.add_argument("--confdir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == "serve":
        serve(
            args.mode,
            args.wire,
            args.sites,
            host=args.host,
            port=args.port,
            confdir=args.confdir,
        )


if __name__ == "__main__":
    main()
