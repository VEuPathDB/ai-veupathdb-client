from __future__ import annotations

from veupathdb.testing.wire.models import Cassette


def merge_stack(old: Cassette | None, new: Cassette) -> Cassette:
    if old is None:
        return new
    newer = {exchange.key() for exchange in new.exchanges}
    kept = [e for e in old.exchanges if e.key() not in newer]
    exchanges = [
        exchange.model_copy(update={"seq": seq})
        for seq, exchange in enumerate([*kept, *new.exchanges])
    ]
    header = new.header.model_copy(
        update={"builds": {**old.header.builds, **new.header.builds}}
    )
    return Cassette(header=header, exchanges=exchanges)
