from datetime import UTC, datetime

from veupathdb.testing.wire import STACK, Cassette, CassetteHeader, Exchange
from veupathdb.testing.wire.stack import merge_stack


def _stack(when: datetime, builds: dict[str, int], *paths: tuple[str, int]) -> Cassette:
    return Cassette(
        header=CassetteHeader(cassette=STACK, recorded_at=when, builds=builds),
        exchanges=[
            Exchange(
                seq=seq,
                host="qa.plasmodb.org",
                method="GET",
                path=path,
                credential="none",
                epoch=0,
                status=status,
            )
            for seq, (path, status) in enumerate(paths)
        ],
    )


def test_the_newer_stack_recording_of_a_key_wins() -> None:
    old = _stack(
        datetime(2026, 11, 1, tzinfo=UTC), {"a": 68, "b": 68}, ("/x", 200), ("/y", 200)
    )
    new = _stack(datetime(2026, 11, 24, tzinfo=UTC), {"a": 69}, ("/y", 500))

    merged = merge_stack(old, new)

    assert [(e.seq, e.path, e.status) for e in merged.exchanges] == [
        (0, "/x", 200),
        (1, "/y", 500),
    ]
    assert merged.header.builds == {"a": 69, "b": 68}
    assert merged.header.recorded_at == new.header.recorded_at


def test_a_first_stack_is_kept_as_it_is() -> None:
    new = _stack(datetime(2026, 11, 24, tzinfo=UTC), {}, ("/x", 200))
    assert merge_stack(None, new) == new
