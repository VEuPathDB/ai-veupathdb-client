from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from veupathdb.testing.wire import (
    STACK,
    Cassette,
    CassetteHeader,
    Exchange,
    WireStore,
)

RECORDED_AT = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)


def _exchange(seq: int, response: str | None) -> Exchange:
    return Exchange(
        seq=seq,
        host="qa.plasmodb.org",
        method="GET",
        path="/plasmo.qa/service/record-types",
        credential="registered",
        epoch=0,
        status=200,
        content_type="application/json",
        response=response,
    )


def test_a_cassette_reads_back_as_written(tmp_path: Path) -> None:
    store = WireStore(tmp_path)
    body = store.put_body(b'["gene"]')
    cassette = Cassette(
        header=CassetteHeader(
            cassette="turns@plasmodb/uat/a.spec.ts/s1-3f2a",
            recorded_at=RECORDED_AT,
            builds={"qa.plasmodb.org": 69},
        ),
        exchanges=[_exchange(0, body), _exchange(1, body)],
    )
    store.write_cassette(cassette)

    assert store.read_cassette(cassette.header.cassette) == cassette
    assert (tmp_path / "cassettes/turns@plasmodb/uat/a.spec.ts/s1-3f2a.jsonl").is_file()
    assert store.cassette_ids() == ["turns@plasmodb/uat/a.spec.ts/s1-3f2a"]


def test_one_body_is_stored_once_by_its_hash(tmp_path: Path) -> None:
    store = WireStore(tmp_path)
    first = store.put_body(b'["gene"]')
    second = store.put_body(b'["gene"]')

    assert first == second
    assert list((tmp_path / "bodies").rglob("*.gz")) == [
        tmp_path / "bodies" / first[:2] / f"{first}.gz"
    ]
    assert store.read_body(first) == b'["gene"]'


def test_the_stack_has_its_own_file(tmp_path: Path) -> None:
    store = WireStore(tmp_path)
    store.write_cassette(
        Cassette(
            header=CassetteHeader(cassette=STACK, recorded_at=RECORDED_AT),
            exchanges=[_exchange(0, None)],
        )
    )
    assert (tmp_path / "stack.jsonl").is_file()
    assert store.cassette_ids() == []


def test_a_missing_cassette_reads_as_none(tmp_path: Path) -> None:
    assert WireStore(tmp_path).read_cassette("feature@plasmodb/a.spec.ts/x-1") is None


@pytest.mark.parametrize("cassette", ["../etc/passwd", "a/../../b", "/abs", "a b"])
def test_a_cassette_id_stays_inside_the_tree(cassette: str) -> None:
    with pytest.raises(ValidationError):
        CassetteHeader(cassette=cassette, recorded_at=RECORDED_AT)


def test_an_exchange_knows_its_key_and_whether_it_writes() -> None:
    read = _exchange(0, None)
    write = read.model_copy(
        update={"method": "POST", "path": "/plasmo.qa/service/users/1/steps"}
    )
    assert read.is_write() is False
    assert write.is_write() is True
    assert read.key() != write.key()


def test_the_manifest_counts_builds_and_dates_per_host(tmp_path: Path) -> None:
    store = WireStore(tmp_path)
    later = datetime(2026, 11, 30, tzinfo=UTC)
    for cassette, when, build in (
        ("feature@plasmodb/a.spec.ts/one-1", RECORDED_AT, 69),
        ("feature@plasmodb/a.spec.ts/two-2", later, 70),
    ):
        store.write_cassette(
            Cassette(
                header=CassetteHeader(
                    cassette=cassette,
                    recorded_at=when,
                    builds={"qa.plasmodb.org": build},
                )
            )
        )

    manifest = store.write_manifest()

    plasmo = manifest.hosts["qa.plasmodb.org"]
    assert manifest.cassettes == 2
    assert plasmo.builds == {69: 1, 70: 1}
    assert (plasmo.oldest, plasmo.newest) == (RECORDED_AT, later)
    assert store.read_manifest() == manifest


@pytest.mark.parametrize("sha", ["../../etc/passwd", "ab", "A" * 64, "g" * 64])
def test_a_response_names_a_body_by_its_hash_only(sha: str) -> None:
    with pytest.raises(ValidationError):
        _exchange(0, sha)


def test_a_body_read_takes_only_a_hash(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="hash"):
        WireStore(tmp_path).read_body("../../x")


@pytest.mark.parametrize("method", ["get", "BREW", "CONNECT"])
def test_an_exchange_takes_only_an_uppercase_verb(method: str) -> None:
    with pytest.raises(ValidationError):
        _exchange(0, None).model_copy(update={}).model_validate(
            {**_exchange(0, None).model_dump(), "method": method}
        )
