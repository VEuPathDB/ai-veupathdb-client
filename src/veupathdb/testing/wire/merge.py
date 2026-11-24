from __future__ import annotations

from pathlib import Path

from veupathdb.testing.wire.models import STACK, Cassette
from veupathdb.testing.wire.stack import merge_stack
from veupathdb.testing.wire.store import WireStore


def _copy_bodies(cassette: Cassette, source: WireStore, target: WireStore) -> None:
    for exchange in cassette.exchanges:
        if exchange.response:
            target.put_body(source.read_body(exchange.response))


def merge(source_root: Path, target_root: Path) -> None:
    source, target = WireStore(source_root), WireStore(target_root)
    for incoming in source.cassettes():
        _copy_bodies(incoming, source, target)
        merged = incoming
        if incoming.header.cassette == STACK:
            merged = merge_stack(target.read_cassette(STACK), incoming)
        target.write_cassette(merged)
    target.prune_bodies()
    target.write_manifest()
