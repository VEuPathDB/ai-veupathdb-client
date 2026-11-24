from datetime import UTC, datetime
from pathlib import Path

from veupathdb.testing.wire import STACK, Cassette, CassetteHeader, Exchange, WireStore
from veupathdb.testing.wire.merge import merge

WHEN = datetime(2026, 11, 24, tzinfo=UTC)


def _cassette(store: WireStore, cassette: str, path: str, body: bytes) -> None:
    store.write_cassette(
        Cassette(
            header=CassetteHeader(cassette=cassette, recorded_at=WHEN),
            exchanges=[
                Exchange(
                    seq=0,
                    host="qa.plasmodb.org",
                    method="GET",
                    path=path,
                    credential="registered",
                    epoch=0,
                    status=200,
                    response=store.put_body(body),
                )
            ],
        )
    )


def test_a_merge_replaces_cassettes_and_merges_the_stack(tmp_path: Path) -> None:
    source = WireStore(tmp_path / "source")
    target = WireStore(tmp_path / "target")
    _cassette(target, "f/a.spec.ts/one-1", "/old", b"old")
    _cassette(target, "f/a.spec.ts/two-2", "/kept", b"kept")
    _cassette(target, STACK, "/root", b"root-old")
    _cassette(source, "f/a.spec.ts/one-1", "/new", b"new")
    _cassette(source, STACK, "/sites", b"sites")

    merge(source.root, target.root)

    one = target.read_cassette("f/a.spec.ts/one-1")
    stack = target.read_cassette(STACK)
    assert one is not None
    assert stack is not None
    assert [e.path for e in one.exchanges] == ["/new"]
    assert [e.path for e in stack.exchanges] == ["/root", "/sites"]
    assert target.cassette_ids() == ["f/a.spec.ts/one-1", "f/a.spec.ts/two-2"]
    bodies = sorted(
        target.read_body(p.stem) for p in (target.root / "bodies").rglob("*.gz")
    )
    assert bodies == [b"kept", b"new", b"root-old", b"sites"]
    assert target.read_manifest().cassettes == 2
