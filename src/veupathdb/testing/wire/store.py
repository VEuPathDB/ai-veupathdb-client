from __future__ import annotations

import gzip
import hashlib
import re
from collections.abc import Iterable
from importlib.metadata import version
from pathlib import Path

from veupathdb.testing.wire.models import (
    STACK,
    Cassette,
    CassetteHeader,
    Exchange,
    HostRecordings,
    Manifest,
)
from veupathdb.testing.wire.redact import Redactor

_SUFFIX = ".jsonl"
_HASH = re.compile(r"[0-9a-f]{64}")
_MANIFEST = "manifest.json"


class WireStore:
    def __init__(self, root: Path, guard: Redactor | None = None) -> None:
        self.root = root
        self._guard = guard

    def _cassette_path(self, cassette: str) -> Path:
        if cassette == STACK:
            return self.root / f"{STACK}{_SUFFIX}"
        return self.root / "cassettes" / f"{cassette}{_SUFFIX}"

    def _body_path(self, sha: str) -> Path:
        if not _HASH.fullmatch(sha):
            msg = f"{sha!r} is not a body hash"
            raise ValueError(msg)
        return self.root / "bodies" / sha[:2] / f"{sha}.gz"

    def put_body(self, body: bytes) -> str:
        if self._guard is not None:
            self._guard.refuse_leaks(body, "A response body")
        sha = hashlib.sha256(body).hexdigest()
        path = self._body_path(sha)
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(gzip.compress(body, mtime=0))
        return sha

    def read_body(self, sha: str) -> bytes:
        return gzip.decompress(self._body_path(sha).read_bytes())

    def read_cassette(self, cassette: str) -> Cassette | None:
        path = self._cassette_path(cassette)
        if not path.is_file():
            return None
        header, *rows = path.read_text().splitlines()
        return Cassette(
            header=CassetteHeader.model_validate_json(header),
            exchanges=[Exchange.model_validate_json(row) for row in rows if row],
        )

    def write_cassette(self, cassette: Cassette) -> None:
        lines = [cassette.header.model_dump_json()]
        lines.extend(exchange.model_dump_json() for exchange in cassette.exchanges)
        text = "\n".join(lines) + "\n"
        if self._guard is not None:
            self._guard.refuse_leaks(text.encode(), cassette.header.cassette)
        path = self._cassette_path(cassette.header.cassette)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def cassette_ids(self) -> list[str]:
        root = self.root / "cassettes"
        return sorted(
            path.relative_to(root).as_posix().removesuffix(_SUFFIX)
            for path in root.rglob(f"*{_SUFFIX}")
        )

    def cassettes(self) -> Iterable[Cassette]:
        for cassette in [STACK, *self.cassette_ids()]:
            found = self.read_cassette(cassette)
            if found is not None:
                yield found

    def prune_bodies(self) -> None:
        held = {
            exchange.response
            for cassette in self.cassettes()
            for exchange in cassette.exchanges
            if exchange.response
        }
        for path in (self.root / "bodies").rglob("*.gz"):
            if path.stem not in held:
                path.unlink()

    def read_manifest(self) -> Manifest:
        path = self.root / _MANIFEST
        if not path.is_file():
            return Manifest()
        return Manifest.model_validate_json(path.read_text())

    def write_manifest(self) -> Manifest:
        hosts: dict[str, HostRecordings] = {}
        count = 0
        for cassette in self.cassettes():
            count += cassette.header.cassette != STACK
            when = cassette.header.recorded_at
            for host, build in cassette.header.builds.items():
                held = hosts.get(host)
                builds = dict(held.builds) if held else {}
                builds[build] = builds.get(build, 0) + 1
                hosts[host] = HostRecordings(
                    builds=builds,
                    oldest=min(when, held.oldest) if held else when,
                    newest=max(when, held.newest) if held else when,
                )
        manifest = Manifest(
            cassettes=count,
            hosts=dict(sorted(hosts.items())),
            libraries={"veupathdb-py": version("veupathdb-py")},
        )
        (self.root / _MANIFEST).write_text(manifest.model_dump_json(indent=2) + "\n")
        return manifest
