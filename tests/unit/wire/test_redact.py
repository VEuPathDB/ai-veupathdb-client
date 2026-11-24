from datetime import UTC, datetime
from pathlib import Path

import pytest

from veupathdb.testing.wire import (
    ACCOUNT_EMAIL,
    FAKE_USER_ID,
    Cassette,
    CassetteHeader,
    Exchange,
    Identity,
    LeakError,
    Redactor,
    WireStore,
)

IDENTITY = Identity(
    user_id=376543210,
    email="Researcher.One@Example.org",
    first_name="Ada",
    last_name="Lovelace",
    organization="Analytical Engines",
)
JWT = "eyJhbGciOiJFUzUxMiJ9.eyJzdWIiOiIxIn0.c2lnbmF0dXJl"
SESSION = "9F3A7C1E55B0D2E4"
REDACTOR = Redactor(IDENTITY, secrets=[JWT, SESSION])

VARIANTS = [
    b'{"email": "Researcher.One@Example.org"}',
    b'{"email": "researcher.one@example.org"}',
    b'{"email": "RESEARCHER.ONE@EXAMPLE.ORG"}',
    b'{"email": "researcher.one\\u0040example.org"}',
    b"email=researcher.one%40example.org&x=1",
    b"email=Researcher.One%40Example.org",
    b'{"name": "Ada Lovelace"}',
    b'{"name": "ada lovelace"}',
    b'{"display": "Dr. LOVELACE, Ada (Analytical Engines)"}',
    b'{"org": "analytical engines"}',
    b'{"id": 376543210}',
    b'{"token": "' + JWT.encode() + b'"}',
    b'{"header": "Authorization: Bearer opaque-token-value"}',
    b'{"cookie": "JSESSIONID=' + SESSION.encode() + b'; Path=/"}',
    b'{"cookie": "Authorization=opaque-token-value"}',
]


@pytest.mark.parametrize("body", VARIANTS)
def test_redaction_removes_every_account_value(body: bytes) -> None:
    redacted = REDACTOR.body(body)

    assert REDACTOR.leaks(redacted) == []
    lowered = redacted.lower()
    for secret in (b"researcher", b"lovelace", b"analytical", b"376543210"):
        assert secret not in lowered
    assert b"opaque-token-value" not in redacted
    assert SESSION.encode() not in redacted


def test_the_placeholders_replace_the_account() -> None:
    body = b'{"id": 376543210, "email": "researcher.one@example.org"}'
    assert REDACTOR.body(body) == (
        f'{{"id": {FAKE_USER_ID}, "email": "{ACCOUNT_EMAIL}"}}'.encode()
    )


def test_the_path_names_the_fake_user() -> None:
    path = REDACTOR.path("/plasmo.qa/service/users/376543210/steps/12")
    assert path == f"/plasmo.qa/service/users/{FAKE_USER_ID}/steps/12"


def test_a_longer_number_that_holds_the_id_is_kept() -> None:
    body = b'{"stepId": 13765432101}'
    assert REDACTOR.body(body) == body


def test_a_name_inside_other_words_is_kept() -> None:
    body = b'{"description": "Adaptive genes"}'
    assert REDACTOR.body(body) == body


@pytest.mark.parametrize("body", VARIANTS)
def test_a_leak_names_what_it_found(body: bytes) -> None:
    assert REDACTOR.leaks(body) != []


def _cassette(body: str) -> Cassette:
    return Cassette(
        header=CassetteHeader(
            cassette="feature@plasmodb/a.spec.ts/one-1",
            recorded_at=datetime(2026, 11, 24, tzinfo=UTC),
        ),
        exchanges=[
            Exchange(
                seq=0,
                host="qa.plasmodb.org",
                method="POST",
                path="/plasmo.qa/service/users/900000001/steps",
                body=body,
                credential="registered",
                epoch=0,
                status=200,
            )
        ],
    )


def test_a_guarded_store_refuses_to_write_a_cassette_that_leaks(tmp_path: Path) -> None:
    store = WireStore(tmp_path, guard=REDACTOR)
    with pytest.raises(LeakError, match="email"):
        store.write_cassette(_cassette('{"to": "RESEARCHER.ONE@example.org"}'))
    assert list(tmp_path.rglob("*.jsonl")) == []


def test_a_guarded_store_refuses_to_write_a_body_that_leaks(tmp_path: Path) -> None:
    store = WireStore(tmp_path, guard=REDACTOR)
    with pytest.raises(LeakError, match="secret"):
        store.put_body(b'{"t": "' + SESSION.lower().encode() + b'"}')
    assert list(tmp_path.rglob("*.gz")) == []


def test_a_guarded_store_writes_a_clean_cassette(tmp_path: Path) -> None:
    store = WireStore(tmp_path, guard=REDACTOR)
    store.write_cassette(_cassette('{"searchName": "GenesByTaxon"}'))
    assert store.read_cassette("feature@plasmodb/a.spec.ts/one-1") is not None
