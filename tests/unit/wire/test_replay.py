from datetime import UTC, datetime

from veupathdb.testing.wire import (
    Cassette,
    CassetteHeader,
    Exchange,
    Miss,
    Played,
    nearest_difference,
    render_misses,
)
from veupathdb.testing.wire.models import Method

HOST = "qa.plasmodb.org"
STEPS = "/plasmo.qa/service/users/900000001/steps"
STRATEGY = "/plasmo.qa/service/users/900000001/strategies/9"
CASSETTE = "turns@plasmodb/uat/a.spec.ts/s1-3f2a"


def _exchange(
    seq: int, method: Method, path: str, epoch: int, body: str = ""
) -> Exchange:
    return Exchange(
        seq=seq,
        host=HOST,
        method=method,
        path=path,
        body=body or None,
        credential="registered",
        epoch=epoch,
        status=200,
    )


def _played(*exchanges: Exchange) -> Played:
    header = CassetteHeader(cassette=CASSETTE, recorded_at=datetime.now(UTC))
    return Played(Cassette(header=header, exchanges=list(exchanges)))


def test_a_write_takes_its_recordings_in_order_and_raises_the_epoch() -> None:
    first = _exchange(0, "POST", STEPS, 0, '{"searchName": "a"}')
    second = _exchange(1, "POST", STEPS, 1, '{"searchName": "a"}')
    played = _played(first, second)

    assert played.take(first.key(), write=True) == first
    assert played.epoch == 1
    assert played.take(first.key(), write=True) == second
    assert played.take(first.key(), write=True) is None


def test_a_poll_repeats_the_last_read_of_its_epoch() -> None:
    before = _exchange(0, "GET", STRATEGY, 0)
    after = _exchange(2, "GET", STRATEGY, 1)
    write = _exchange(1, "DELETE", STEPS + "/7", 0)
    played = _played(before, write, after)

    assert played.take(before.key(), write=False) == before
    assert played.take(before.key(), write=False) == before
    played.take(write.key(), write=True)
    assert played.take(before.key(), write=False) == after
    assert played.take(before.key(), write=False) == after


def test_a_read_with_none_at_its_epoch_takes_the_last_before_it() -> None:
    read = _exchange(0, "GET", STRATEGY, 0)
    writes = [_exchange(i, "DELETE", f"{STEPS}/{i}", i - 1) for i in (1, 2)]
    played = _played(read, *writes)
    for write in writes:
        played.take(write.key(), write=True)

    assert played.take(read.key(), write=False) == read


def test_a_read_recorded_only_after_its_epoch_is_a_miss() -> None:
    late = _exchange(1, "GET", STRATEGY, 1)
    played = _played(_exchange(0, "DELETE", STEPS + "/1", 0), late)
    assert played.take(late.key(), write=False) is None


def test_concurrent_reads_of_two_keys_match_by_key() -> None:
    records = "/plasmo.qa/service/record-types/gene/records"
    one = _exchange(0, "POST", records, 0, '{"primaryKey": [{"value": "PF3D7_1"}]}')
    two = _exchange(1, "POST", records, 0, '{"primaryKey": [{"value": "PF3D7_2"}]}')
    played = _played(one, two)

    assert played.take(two.key(), write=False) == two
    assert played.take(one.key(), write=False) == one


def test_rewind_starts_the_cassette_again() -> None:
    write = _exchange(0, "POST", STEPS, 0, "{}")
    played = _played(write)
    played.take(write.key(), write=True)
    played.rewind()

    assert played.epoch == 0
    assert played.take(write.key(), write=True) == write


def test_a_write_never_sent_is_listed() -> None:
    sent = _exchange(0, "POST", STEPS, 0, '{"searchName": "a"}')
    skipped = _exchange(1, "DELETE", STEPS + "/7", 1)
    played = _played(sent, skipped)
    played.take(sent.key(), write=True)

    assert played.unsent_writes() == [skipped]


def test_the_nearest_recording_names_the_value_that_differs() -> None:
    recorded = _exchange(
        0,
        "POST",
        STEPS,
        0,
        '{"searchConfig": {"parameters": {"min_length": "50", "organism": "x"}}}',
    )
    played = _played(recorded)
    sent = b'{"searchConfig": {"parameters": {"min_length": "60", "organism": "x"}}}'

    nearest, differences = nearest_difference(
        played.cassette, "POST", HOST, STEPS, sent
    )

    assert nearest == f"POST {HOST} {STEPS}"
    assert differences == ['$.searchConfig.parameters.min_length: "50" -> "60"']


def test_the_report_lists_misses_and_unsent_writes() -> None:
    miss = Miss(
        cassette=CASSETTE,
        method="POST",
        host=HOST,
        path=STEPS,
        reason="unrecorded",
        nearest=f"POST {HOST} {STEPS}",
        differences=['$.a: "1" -> "2"'],
    )
    unsent = _exchange(1, "DELETE", STEPS + "/7", 1)

    report = render_misses(CASSETTE, [miss], [unsent])

    assert report.splitlines() == [
        f"WDK replay: 1 request has no recording, 1 recorded write was not sent ({CASSETTE}).",
        f"  POST {HOST} {STEPS}",
        '    nearest recording differs at $.a: "1" -> "2"',
        f"  recorded but not sent: DELETE {HOST} {STEPS}/7",
    ]
