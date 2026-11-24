import json
import re
from datetime import UTC, datetime
from pathlib import Path

import httpx
import jwt
import pytest

from veupathdb.testing.wire import (
    FAKE_USER_ID,
    Cassette,
    CassetteHeader,
    Exchange,
    Played,
    WireStore,
)
from veupathdb.testing.wire.refresh import WdkSession, refresh

HOST = "qa.plasmodb.org"
SERVICE = "/plasmo.qa/service"
REAL_ID = 31337
EMAIL = "acct@example.org"
CASSETTE = "feature@plasmodb/a.spec.ts/one-1"
FAKE_STEPS = f"{SERVICE}/users/{FAKE_USER_ID}/steps"
REGISTERED = jwt.encode(
    {"sub": "1", "is_guest": False, "exp": 4102444800}, "k" * 32, algorithm="HS256"
)


class Upstream:
    def __init__(self) -> None:
        self.next_id = 5000
        self.deleted: list[str] = []
        self.sent: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        self.sent.append(f"{request.method} {path}")
        fixed = {
            f"{SERVICE}/login": httpx.Response(
                204, headers={"set-cookie": f"Authorization={REGISTERED}; Path=/"}
            ),
            f"{SERVICE}/users/current": httpx.Response(
                200, json={"id": REAL_ID, "email": EMAIL, "isGuest": False}
            ),
            SERVICE: httpx.Response(200, json={"buildNumber": 70}),
        }
        return fixed.get(path) or self._steps(request, path)

    def _steps(self, request: httpx.Request, path: str) -> httpx.Response:
        steps = f"{SERVICE}/users/{REAL_ID}/steps"
        if request.method == "POST" and path == steps:
            self.next_id += 1
            return httpx.Response(200, json={"id": self.next_id, "owner": EMAIL})
        found = re.fullmatch(rf"{steps}/(\d+)", path)
        if found and request.method == "GET":
            return httpx.Response(200, json={"id": int(found[1]), "estimatedSize": 12})
        if found and request.method == "DELETE":
            self.deleted.append(found[1])
            return httpx.Response(204)
        return httpx.Response(404, json={"path": path})


def _exchange(
    seq: int, method: str, path: str, epoch: int, store: WireStore, body: bytes
) -> Exchange:
    return Exchange(
        seq=seq,
        host=HOST,
        method=method,
        path=path,
        body='{"searchName": "GenesByTaxon"}' if method == "POST" else None,
        credential="registered",
        epoch=epoch,
        status=200 if body else 204,
        content_type="application/json",
        response=store.put_body(body) if body else None,
    )


def _write(store: WireStore, cassette: str, *exchanges: Exchange) -> None:
    store.write_cassette(
        Cassette(
            header=CassetteHeader(
                cassette=cassette,
                recorded_at=datetime(2026, 11, 1, tzinfo=UTC),
                builds={HOST: 69},
            ),
            exchanges=list(exchanges),
        )
    )


def _session(upstream: Upstream) -> WdkSession:
    return WdkSession(
        {HOST: f"https://{HOST}{SERVICE}"},
        httpx.AsyncClient(transport=httpx.MockTransport(upstream)),
    )


async def test_a_refreshed_cassette_replays_with_the_new_ids(tmp_path: Path) -> None:
    store = WireStore(tmp_path)
    _write(
        store,
        CASSETTE,
        _exchange(0, "POST", FAKE_STEPS, 0, store, b'{"id": 100}'),
        _exchange(
            1, "GET", f"{FAKE_STEPS}/100", 1, store, b'{"id": 100, "estimatedSize": 10}'
        ),
        _exchange(2, "DELETE", f"{FAKE_STEPS}/100", 1, store, b""),
    )
    upstream = Upstream()

    result = await refresh(tmp_path, _session(upstream), EMAIL, "pw", HOST)

    assert result.errors == []
    assert [row.counts for row in result.rows] == [
        [f"GET {FAKE_STEPS}/100 estimatedSize 10 -> 12"]
    ]
    assert upstream.deleted == ["5001"]
    refreshed = WireStore(tmp_path).read_cassette(CASSETTE)
    assert refreshed is not None
    assert [e.path for e in refreshed.exchanges] == [
        FAKE_STEPS,
        f"{FAKE_STEPS}/5001",
        f"{FAKE_STEPS}/5001",
    ]
    assert refreshed.header.builds == {HOST: 70}
    played = Played(refreshed)
    created = played.take(refreshed.exchanges[0].key(), write=True)
    assert created is not None
    assert created.response is not None
    new_id = json.loads(WireStore(tmp_path).read_body(created.response))["id"]
    assert new_id == 5001
    read = played.take(
        Exchange.model_validate(
            {**refreshed.exchanges[1].model_dump(), "path": f"{FAKE_STEPS}/{new_id}"}
        ).key(),
        write=False,
    )
    assert read is not None
    assert played.take(refreshed.exchanges[2].key(), write=True) is not None
    assert played.unsent_writes() == []
    body = json.loads(WireStore(tmp_path).read_body(created.response))
    assert body["owner"] == "e2e-account@strategist.test"


async def test_an_unmapped_id_keeps_the_old_cassette_and_sweeps(tmp_path: Path) -> None:
    store = WireStore(tmp_path)
    _write(
        store,
        CASSETTE,
        _exchange(0, "POST", FAKE_STEPS, 0, store, b'{"id": 100}'),
        _exchange(1, "GET", f"{FAKE_STEPS}/314", 1, store, b'{"id": 314}'),
    )
    before = (tmp_path / f"cassettes/{CASSETTE}.jsonl").read_text()
    upstream = Upstream()

    result = await refresh(tmp_path, _session(upstream), EMAIL, "pw", HOST)

    assert len(result.errors) == 1
    assert CASSETTE in result.errors[0]
    assert "314" in result.errors[0]
    assert (tmp_path / f"cassettes/{CASSETTE}.jsonl").read_text() == before
    assert upstream.deleted == ["5001"]
    assert f"GET {SERVICE}/users/{REAL_ID}/steps/314" not in upstream.sent


async def test_a_refused_sign_in_stops_the_refresh(tmp_path: Path) -> None:
    def refused(request: httpx.Request) -> httpx.Response:
        del request
        return httpx.Response(401)

    session = WdkSession(
        {HOST: f"https://{HOST}{SERVICE}"},
        httpx.AsyncClient(transport=httpx.MockTransport(refused)),
    )
    with pytest.raises(PermissionError, match="refused"):
        await refresh(tmp_path, session, EMAIL, "pw", HOST)
